"""
TomTom Traffic Flow API Worker

This worker:
1. Polls TomTom Traffic Flow API every 5 minutes for predefined locations
2. Retrieves current speed vs. free-flow speed for monitored road segments
3. Stores traffic data in TimescaleDB hypertable
4. Designed to monitor critical intersections/bottlenecks in Chișinău

The TomTom API provides real-time traffic data that complements the 
historical patterns derived from trolleybus telemetry.

Usage:
    python tomtom_worker.py
    
    # Run once for testing
    python tomtom_worker.py --once
    
    # Test with mock data (no API key needed)
    python tomtom_worker.py --mock

Prerequisites:
    Set TOMTOM_API_KEY in .env file or environment variable
    Get a free key at: https://developer.tomtom.com
"""

import argparse
import sys
import signal
import time
import logging
import random
from datetime import datetime, timezone
from typing import List, Dict, Optional
from dataclasses import dataclass

import requests
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
class TrafficFlowData:
    """Represents traffic flow data for a monitored location."""
    location_id: str
    location_name: str
    latitude: float
    longitude: float
    current_speed: float          # km/h
    free_flow_speed: float        # km/h
    current_travel_time: int      # seconds
    free_flow_travel_time: int    # seconds
    confidence: float             # 0-1
    road_closure: bool
    timestamp: datetime
    
    @property
    def congestion_ratio(self) -> float:
        """Calculate congestion as ratio: 1.0 = free flow, <1.0 = congested."""
        if self.free_flow_speed > 0:
            return self.current_speed / self.free_flow_speed
        return 1.0
    
    def to_db_tuple(self) -> tuple:
        """Convert to tuple for database insertion."""
        return (
            self.timestamp,
            self.location_id,
            self.location_name,
            self.latitude,
            self.longitude,
            self.longitude,  # For ST_MakePoint(lon, lat)
            self.latitude,
            self.current_speed,
            self.free_flow_speed,
            self.current_travel_time,
            self.free_flow_travel_time,
            self.confidence,
            self.road_closure
        )


class TomTomWorker:
    """
    Worker that fetches and stores TomTom Traffic Flow data.
    """
    
    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ChisinauRoutingEngine/1.0'
        })
        self.running = False
        self.conn = None
        self.monitored_locations: List[Dict] = []
        self.stats = {
            'total_fetches': 0,
            'successful_fetches': 0,
            'api_errors': 0,
            'last_fetch': None
        }
    
    def connect_db(self):
        """Establish database connection."""
        logger.info(f"Connecting to database: {settings.db.host}:{settings.db.port}")
        self.conn = psycopg2.connect(**settings.db.psycopg2_params)
        self.conn.set_session(autocommit=True)
        logger.info("Database connection established")
    
    def load_monitored_locations(self):
        """Load monitored locations from database."""
        logger.info("Loading monitored locations...")
        
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, latitude, longitude, radius_m, tomtom_segment_id
                FROM monitored_locations
                WHERE is_active = TRUE
            """)
            
            rows = cur.fetchall()
            self.monitored_locations = [
                {
                    'id': row[0],
                    'name': row[1],
                    'latitude': row[2],
                    'longitude': row[3],
                    'radius_m': row[4],
                    'tomtom_segment_id': row[5]
                }
                for row in rows
            ]
        
        logger.info(f"Loaded {len(self.monitored_locations)} monitored locations")
    
    def fetch_traffic_for_location(self, location: Dict) -> Optional[TrafficFlowData]:
        """
        Fetch traffic flow data for a single location from TomTom API.
        
        API Documentation:
        https://developer.tomtom.com/traffic-api/documentation/traffic-flow/flow-segment-data
        
        Args:
            location: Dictionary with id, name, latitude, longitude
            
        Returns:
            TrafficFlowData or None if fetch failed
        """
        if self.use_mock:
            return self._generate_mock_data(location)
        
        if not settings.tomtom.is_configured:
            logger.warning("TomTom API key not configured, using mock data")
            return self._generate_mock_data(location)
        
        try:
            # Build API URL
            # Format: /flowSegmentData/{style}/{zoom}/{point}?key={key}
            point = f"{location['latitude']},{location['longitude']}"
            url = (
                f"{settings.tomtom.base_url}"
                f"/absolute/{settings.tomtom.zoom}/{point}"
                f".json"
            )
            
            params = {
                'key': settings.tomtom.api_key,
                'unit': settings.tomtom.unit,
                'thickness': settings.tomtom.thickness
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            flow = data.get('flowSegmentData', {})
            
            return TrafficFlowData(
                location_id=location['id'],
                location_name=location['name'],
                latitude=location['latitude'],
                longitude=location['longitude'],
                current_speed=flow.get('currentSpeed', 0),
                free_flow_speed=flow.get('freeFlowSpeed', 0),
                current_travel_time=flow.get('currentTravelTime', 0),
                free_flow_travel_time=flow.get('freeFlowTravelTime', 0),
                confidence=flow.get('confidence', 0) / 100,  # API returns 0-100
                road_closure=flow.get('roadClosure', False),
                timestamp=datetime.now(timezone.utc)
            )
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                logger.error("TomTom API key invalid or quota exceeded")
            elif e.response.status_code == 429:
                logger.warning("TomTom API rate limit hit, backing off")
                time.sleep(60)
            elif e.response.status_code == 400:
                # Point not covered by TomTom - use mock data
                logger.debug(f"Location not covered by TomTom: {location['name']}, using simulated data")
                return self._generate_mock_data(location)
            else:
                logger.error(f"TomTom API error: {e}")
            self.stats['api_errors'] += 1
            return None
            
        except Exception as e:
            logger.error(f"Error fetching traffic for {location['name']}: {e}")
            return None
    
    def _generate_mock_data(self, location: Dict) -> TrafficFlowData:
        """
        Generate realistic mock traffic data for testing.
        
        Simulates typical traffic patterns:
        - Rush hours: slower speeds
        - Night: near free-flow speeds
        - Random variations
        """
        now = datetime.now()
        hour = now.hour
        
        # Base free-flow speed for urban Chișinău
        free_flow = random.uniform(40, 55)
        
        # Time-based congestion factor
        if 7 <= hour <= 9 or 17 <= hour <= 19:
            # Rush hour: 50-80% of free flow
            congestion = random.uniform(0.5, 0.8)
        elif 10 <= hour <= 16:
            # Daytime: 70-95% of free flow
            congestion = random.uniform(0.7, 0.95)
        elif 22 <= hour or hour <= 5:
            # Night: 90-100% of free flow
            congestion = random.uniform(0.9, 1.0)
        else:
            # Transition hours
            congestion = random.uniform(0.6, 0.9)
        
        current_speed = free_flow * congestion
        
        # Calculate travel times (assuming 500m segment)
        segment_length = 500  # meters
        free_flow_time = int(segment_length / (free_flow / 3.6))  # seconds
        current_time = int(segment_length / (current_speed / 3.6)) if current_speed > 0 else free_flow_time * 3
        
        return TrafficFlowData(
            location_id=location['id'],
            location_name=location['name'],
            latitude=location['latitude'],
            longitude=location['longitude'],
            current_speed=round(current_speed, 1),
            free_flow_speed=round(free_flow, 1),
            current_travel_time=current_time,
            free_flow_travel_time=free_flow_time,
            confidence=random.uniform(0.7, 1.0),
            road_closure=False,
            timestamp=datetime.now(timezone.utc)
        )
    
    def fetch_all_locations(self) -> List[TrafficFlowData]:
        """
        Fetch traffic data for all monitored locations.
        
        Returns:
            List of TrafficFlowData objects
        """
        results = []
        
        for location in self.monitored_locations:
            data = self.fetch_traffic_for_location(location)
            if data:
                results.append(data)
            
            # Brief pause between API calls to avoid rate limiting
            if not self.use_mock and len(self.monitored_locations) > 1:
                time.sleep(0.5)
        
        return results
    
    def store_traffic_data(self, traffic_data: List[TrafficFlowData]):
        """
        Store traffic flow data in the database.
        
        Args:
            traffic_data: List of TrafficFlowData objects
        """
        if not traffic_data:
            return
        
        insert_sql = """
            INSERT INTO tomtom_traffic (
                time, location_id, location_name,
                latitude, longitude, geom,
                current_speed, free_flow_speed,
                current_travel_time, free_flow_travel_time,
                confidence, road_closure
            )
            VALUES (
                %s, %s, %s,
                %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                %s, %s,
                %s, %s,
                %s, %s
            )
        """
        
        try:
            with self.conn.cursor() as cur:
                records = [d.to_db_tuple() for d in traffic_data]
                execute_batch(cur, insert_sql, records)
                # No commit needed - using autocommit mode
            
            logger.debug(f"Stored {len(traffic_data)} traffic records")
            
        except psycopg2.Error as e:
            logger.error(f"Database error storing traffic data: {e}")
    
    def fetch_and_store(self):
        """Execute one fetch-and-store cycle."""
        self.stats['total_fetches'] += 1
        
        try:
            traffic_data = self.fetch_all_locations()
            
            if traffic_data:
                self.store_traffic_data(traffic_data)
                self.stats['successful_fetches'] += 1
                self.stats['last_fetch'] = datetime.now()
                
                # Log summary
                avg_congestion = sum(d.congestion_ratio for d in traffic_data) / len(traffic_data)
                worst = min(traffic_data, key=lambda d: d.congestion_ratio)
                
                logger.info(
                    f"Traffic update: {len(traffic_data)} locations | "
                    f"Avg flow: {avg_congestion*100:.0f}% | "
                    f"Worst: {worst.location_name} ({worst.congestion_ratio*100:.0f}%)"
                )
            else:
                logger.warning("No traffic data received")
                
        except Exception as e:
            logger.error(f"Fetch cycle failed: {e}")
    
    def run(self):
        """
        Main run loop - polls TomTom API at configured interval.
        """
        logger.info("="*60)
        logger.info("TomTom Traffic Flow Worker Starting")
        logger.info("="*60)
        
        if self.use_mock:
            logger.info("MODE: Using mock data (no API calls)")
        elif settings.tomtom.is_configured:
            logger.info("MODE: Live TomTom API")
        else:
            logger.info("MODE: API key not configured, will use mock data")
        
        logger.info(f"Poll interval: {settings.tomtom.poll_interval_seconds} seconds")
        logger.info("="*60)
        
        # Connect to database and load locations
        self.connect_db()
        self.load_monitored_locations()
        
        if not self.monitored_locations:
            logger.error("No monitored locations found in database. Add locations to monitored_locations table.")
            return
        
        # Setup signal handlers
        self.running = True
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Initial fetch
        self.fetch_and_store()
        
        # Main loop
        while self.running:
            try:
                time.sleep(settings.tomtom.poll_interval_seconds)
                if self.running:
                    self.fetch_and_store()
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(10)
        
        # Cleanup
        logger.info("Shutting down...")
        if self.conn:
            self.conn.close()
        
        self._print_final_stats()
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self.running = False
    
    def _print_final_stats(self):
        """Print final statistics."""
        print("\n" + "="*60)
        print("TOMTOM WORKER FINAL STATISTICS")
        print("="*60)
        print(f"Total fetch cycles:    {self.stats['total_fetches']}")
        print(f"Successful cycles:     {self.stats['successful_fetches']}")
        print(f"API errors:            {self.stats['api_errors']}")
        print(f"Monitored locations:   {len(self.monitored_locations)}")
        if self.stats['last_fetch']:
            print(f"Last successful fetch: {self.stats['last_fetch']}")
        print("="*60 + "\n")


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(
        description='TomTom Traffic Flow API worker'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Fetch once and exit (for testing)'
    )
    parser.add_argument(
        '--mock',
        action='store_true',
        help='Use mock data instead of real API (for testing)'
    )
    args = parser.parse_args()
    
    worker = TomTomWorker(use_mock=args.mock)
    
    if args.once:
        worker.connect_db()
        worker.load_monitored_locations()
        worker.fetch_and_store()
        worker.conn.close()
    else:
        worker.run()


if __name__ == '__main__':
    main()
