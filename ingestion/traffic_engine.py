"""
Traffic Analysis Engine

This module:
1. Performs map-matching: snaps trolleybus GPS points to OSM edges
2. Calculates observed speeds between consecutive position updates
3. Aggregates speeds into hourly profiles per edge
4. Updates edge_speed_profiles table for routing weight lookups

The engine processes recent telemetry data and builds historical 
speed patterns that the routing core uses for time-varying weights.

Usage:
    python traffic_engine.py
    
    # Process last N hours of unmatched telemetry
    python traffic_engine.py --hours 24
    
    # Rebuild all speed profiles from scratch
    python traffic_engine.py --rebuild-profiles
"""

import argparse
import sys
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import math

import psycopg2
from psycopg2.extras import execute_batch

from config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class TelemetryPoint:
    """A single telemetry observation."""
    id: int  # Row ID for updating
    vehicle_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    speed_kmh: Optional[float]
    matched_edge_id: Optional[int]


@dataclass
class EdgeMatch:
    """Result of map-matching a point to an edge."""
    edge_id: int
    distance_m: float
    fraction: float  # Position along edge (0-1)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate great-circle distance between two points in meters.
    
    Args:
        lat1, lon1: First point coordinates
        lat2, lon2: Second point coordinates
        
    Returns:
        Distance in meters
    """
    R = 6371000  # Earth radius in meters
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_phi / 2) ** 2 + 
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


class TrafficEngine:
    """
    Engine for processing telemetry and computing traffic patterns.
    """
    
    def __init__(self):
        self.conn = None
        self.stats = {
            'points_processed': 0,
            'points_matched': 0,
            'speeds_calculated': 0,
            'profiles_updated': 0
        }
    
    def connect_db(self):
        """Establish database connection."""
        logger.info(f"Connecting to database: {settings.db.host}:{settings.db.port}")
        self.conn = psycopg2.connect(**settings.db.psycopg2_params)
        logger.info("Database connection established")
    
    def map_match_point(self, latitude: float, longitude: float) -> Optional[EdgeMatch]:
        """
        Find the nearest edge to a GPS point using PostGIS.
        
        Uses the find_nearest_edge() function defined in init.sql.
        
        Args:
            latitude: GPS latitude
            longitude: GPS longitude
            
        Returns:
            EdgeMatch or None if no edge within threshold
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT edge_id, distance_m, fraction
                    FROM find_nearest_edge(%s, %s, %s)
                    LIMIT 1
                """, (latitude, longitude, settings.traffic.max_match_distance_m))
                
                row = cur.fetchone()
                if row:
                    return EdgeMatch(
                        edge_id=row[0],
                        distance_m=row[1],
                        fraction=row[2]
                    )
                return None
                
        except Exception as e:
            logger.error(f"Map matching error: {e}")
            return None
    
    def process_unmatched_telemetry(self, hours: int = 1) -> int:
        """
        Map-match recent telemetry points that haven't been processed.
        
        Args:
            hours: Process telemetry from the last N hours
            
        Returns:
            Number of points matched
        """
        logger.info(f"Processing unmatched telemetry from last {hours} hours...")
        
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        # Fetch unmatched points
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT ctid, vehicle_id, time, latitude, longitude, speed_kmh
                FROM trolleybus_telemetry
                WHERE matched_edge_id IS NULL
                  AND time > %s
                ORDER BY vehicle_id, time
                LIMIT 50000
            """, (cutoff,))
            
            rows = cur.fetchall()
        
        if not rows:
            logger.info("No unmatched telemetry found")
            return 0
        
        logger.info(f"Found {len(rows)} unmatched points to process")
        
        # Process in batches
        matched_count = 0
        updates = []
        
        for row in rows:
            ctid, vehicle_id, timestamp, lat, lon, speed = row
            self.stats['points_processed'] += 1
            
            match = self.map_match_point(lat, lon)
            
            if match:
                updates.append((match.edge_id, ctid))
                matched_count += 1
                self.stats['points_matched'] += 1
            
            # Batch updates
            if len(updates) >= 500:
                self._apply_match_updates(updates)
                updates = []
        
        # Final batch
        if updates:
            self._apply_match_updates(updates)
        
        logger.info(f"Matched {matched_count}/{len(rows)} points")
        return matched_count
    
    def _apply_match_updates(self, updates: List[Tuple[int, str]]):
        """Apply batch of map-match updates."""
        with self.conn.cursor() as cur:
            # Use UPDATE with ctid for efficiency
            for edge_id, ctid in updates:
                cur.execute("""
                    UPDATE trolleybus_telemetry
                    SET matched_edge_id = %s
                    WHERE ctid = %s
                """, (edge_id, ctid))
            self.conn.commit()
    
    def calculate_segment_speeds(self, hours: int = 24) -> Dict[int, List[Tuple[int, int, float]]]:
        """
        Calculate observed speeds from consecutive vehicle positions.
        
        For each vehicle, computes speed between adjacent time points
        and associates it with the matched edge.
        
        Args:
            hours: Analyze telemetry from the last N hours
            
        Returns:
            Dict mapping edge_id -> list of (day_of_week, hour, speed_kmh)
        """
        logger.info(f"Calculating segment speeds from last {hours} hours...")
        
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        # Fetch matched telemetry grouped by vehicle
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT vehicle_id, time, latitude, longitude, 
                       matched_edge_id, speed_kmh
                FROM trolleybus_telemetry
                WHERE matched_edge_id IS NOT NULL
                  AND time > %s
                ORDER BY vehicle_id, time
            """, (cutoff,))
            
            rows = cur.fetchall()
        
        if not rows:
            logger.info("No matched telemetry found for speed calculation")
            return {}
        
        logger.info(f"Analyzing {len(rows)} matched points...")
        
        # Group by vehicle and calculate speeds
        edge_speeds = defaultdict(list)  # edge_id -> [(dow, hour, speed)]
        
        current_vehicle = None
        prev_point = None
        
        for row in rows:
            vehicle_id, timestamp, lat, lon, edge_id, reported_speed = row
            
            # Reset on new vehicle
            if vehicle_id != current_vehicle:
                current_vehicle = vehicle_id
                prev_point = (timestamp, lat, lon, edge_id, reported_speed)
                continue
            
            prev_time, prev_lat, prev_lon, prev_edge, prev_speed = prev_point
            
            # Calculate time difference
            time_diff = (timestamp - prev_time).total_seconds()
            
            # Skip if too long (vehicle stopped or data gap)
            if time_diff > 120:  # More than 2 minutes
                prev_point = (timestamp, lat, lon, edge_id, reported_speed)
                continue
            
            # Skip if too short (GPS noise)
            if time_diff < 5:
                continue
            
            # Calculate distance
            distance = haversine_distance(prev_lat, prev_lon, lat, lon)
            
            # Calculate speed (m/s to km/h)
            if time_diff > 0:
                calculated_speed = (distance / time_diff) * 3.6
            else:
                calculated_speed = 0
            
            # Use reported speed if available and reasonable
            if reported_speed and settings.traffic.min_speed_kmh <= reported_speed <= settings.traffic.max_speed_kmh:
                speed = reported_speed
            elif settings.traffic.min_speed_kmh <= calculated_speed <= settings.traffic.max_speed_kmh:
                speed = calculated_speed
            else:
                prev_point = (timestamp, lat, lon, edge_id, reported_speed)
                continue
            
            # Assign to edge (use current edge or previous if same)
            target_edge = edge_id if edge_id else prev_edge
            
            if target_edge:
                # Extract day of week (0=Monday) and hour
                dow = timestamp.weekday()
                hour = timestamp.hour
                
                edge_speeds[target_edge].append((dow, hour, speed))
                self.stats['speeds_calculated'] += 1
            
            prev_point = (timestamp, lat, lon, edge_id, reported_speed)
        
        logger.info(f"Calculated speeds for {len(edge_speeds)} edges")
        return dict(edge_speeds)
    
    def update_speed_profiles(self, edge_speeds: Dict[int, List[Tuple[int, int, float]]]):
        """
        Update edge_speed_profiles table with aggregated speed data.
        
        Computes statistics (avg, min, max, std) for each edge+time slot
        and upserts into the profiles table.
        
        Args:
            edge_speeds: Dict from calculate_segment_speeds()
        """
        if not edge_speeds:
            logger.info("No speed data to update profiles")
            return
        
        logger.info("Updating speed profiles...")
        
        # Aggregate by (edge_id, dow, hour)
        aggregated = defaultdict(list)
        
        for edge_id, observations in edge_speeds.items():
            for dow, hour, speed in observations:
                aggregated[(edge_id, dow, hour)].append(speed)
        
        # Calculate statistics and prepare upserts
        upserts = []
        
        for (edge_id, dow, hour), speeds in aggregated.items():
            if len(speeds) < 2:  # Need at least 2 samples
                continue
            
            avg_speed = sum(speeds) / len(speeds)
            min_speed = min(speeds)
            max_speed = max(speeds)
            
            # Calculate standard deviation
            variance = sum((s - avg_speed) ** 2 for s in speeds) / len(speeds)
            std_dev = math.sqrt(variance)
            
            # Get edge length to calculate travel time
            with self.conn.cursor() as cur:
                cur.execute("SELECT length_m FROM edges WHERE id = %s", (edge_id,))
                row = cur.fetchone()
                if row:
                    length_m = row[0]
                    # time = distance / speed
                    avg_time = (length_m / (avg_speed / 3.6)) if avg_speed > 0 else None
                else:
                    avg_time = None
            
            upserts.append((
                edge_id, dow, hour,
                round(avg_speed, 1),
                round(min_speed, 1),
                round(max_speed, 1),
                round(std_dev, 2),
                len(speeds),
                round(avg_time, 1) if avg_time else None
            ))
        
        # Batch upsert
        if upserts:
            with self.conn.cursor() as cur:
                execute_batch(cur, """
                    INSERT INTO edge_speed_profiles (
                        edge_id, day_of_week, hour_of_day,
                        avg_speed_kmh, min_speed_kmh, max_speed_kmh,
                        std_dev, sample_count, avg_time_sec
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (edge_id, day_of_week, hour_of_day)
                    DO UPDATE SET
                        avg_speed_kmh = (
                            edge_speed_profiles.avg_speed_kmh * edge_speed_profiles.sample_count + 
                            EXCLUDED.avg_speed_kmh * EXCLUDED.sample_count
                        ) / (edge_speed_profiles.sample_count + EXCLUDED.sample_count),
                        min_speed_kmh = LEAST(edge_speed_profiles.min_speed_kmh, EXCLUDED.min_speed_kmh),
                        max_speed_kmh = GREATEST(edge_speed_profiles.max_speed_kmh, EXCLUDED.max_speed_kmh),
                        sample_count = edge_speed_profiles.sample_count + EXCLUDED.sample_count,
                        avg_time_sec = EXCLUDED.avg_time_sec,
                        last_updated = NOW()
                """, upserts)
                self.conn.commit()
            
            self.stats['profiles_updated'] = len(upserts)
            logger.info(f"Updated {len(upserts)} speed profile entries")
    
    def rebuild_all_profiles(self):
        """
        Rebuild all speed profiles from scratch using all available telemetry.
        
        Warning: This can be slow for large datasets.
        """
        logger.warning("Rebuilding all speed profiles from scratch...")
        
        with self.conn.cursor() as cur:
            # Clear existing profiles
            cur.execute("DELETE FROM edge_speed_profiles")
            self.conn.commit()
        
        # Process all available data (last 30 days)
        self.process_unmatched_telemetry(hours=24*30)
        edge_speeds = self.calculate_segment_speeds(hours=24*30)
        self.update_speed_profiles(edge_speeds)
        
        logger.info("Profile rebuild complete")
    
    def run_full_analysis(self, hours: int = 24):
        """
        Run complete traffic analysis pipeline.
        
        1. Map-match unprocessed telemetry
        2. Calculate segment speeds
        3. Update speed profiles
        
        Args:
            hours: Hours of data to analyze
        """
        logger.info("="*60)
        logger.info("Traffic Analysis Engine - Starting Full Analysis")
        logger.info("="*60)
        
        start_time = datetime.now()
        
        # Step 1: Map matching
        logger.info("STEP 1: Map Matching")
        matched = self.process_unmatched_telemetry(hours)
        
        # Step 2: Speed calculation
        logger.info("\nSTEP 2: Speed Calculation")
        edge_speeds = self.calculate_segment_speeds(hours)
        
        # Step 3: Profile updates
        logger.info("\nSTEP 3: Profile Updates")
        self.update_speed_profiles(edge_speeds)
        
        elapsed = datetime.now() - start_time
        self._print_stats(elapsed)
    
    def _print_stats(self, elapsed):
        """Print analysis statistics."""
        print("\n" + "="*60)
        print("TRAFFIC ANALYSIS COMPLETE")
        print("="*60)
        print(f"Points processed:    {self.stats['points_processed']:,}")
        print(f"Points matched:      {self.stats['points_matched']:,}")
        print(f"Speeds calculated:   {self.stats['speeds_calculated']:,}")
        print(f"Profiles updated:    {self.stats['profiles_updated']:,}")
        print(f"Elapsed time:        {elapsed.total_seconds():.1f} seconds")
        print("="*60 + "\n")


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(
        description='Traffic analysis engine for telemetry processing'
    )
    parser.add_argument(
        '--hours',
        type=int,
        default=24,
        help='Hours of telemetry to analyze (default: 24)'
    )
    parser.add_argument(
        '--rebuild-profiles',
        action='store_true',
        help='Rebuild all speed profiles from scratch'
    )
    parser.add_argument(
        '--match-only',
        action='store_true',
        help='Only perform map matching, skip profile updates'
    )
    args = parser.parse_args()
    
    engine = TrafficEngine()
    engine.connect_db()
    
    try:
        if args.rebuild_profiles:
            engine.rebuild_all_profiles()
        elif args.match_only:
            engine.process_unmatched_telemetry(args.hours)
        else:
            engine.run_full_analysis(args.hours)
    finally:
        if engine.conn:
            engine.conn.close()


if __name__ == '__main__':
    main()
