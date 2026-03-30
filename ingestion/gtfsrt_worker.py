"""
GTFS-RT Telemetry Worker for Roataway Trolleybus Data

This worker:
1. Polls the Roataway GTFS-RT vehicle positions endpoint every 30 seconds
2. Parses the protobuf response using gtfs-realtime-bindings
3. Stores vehicle positions in TimescaleDB hypertable
4. Automatically creates PostGIS geometries for spatial queries

The Roataway project (https://github.com/roataway) provides real-time 
positions of trolleybuses in Chișinău, acting as "floating car data" 
for traffic analysis.

Usage:
    python gtfsrt_worker.py
    
    # Run in background
    python gtfsrt_worker.py --daemon
"""

import argparse
import sys
import signal
import time
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

import requests
import psycopg2
from psycopg2.extras import execute_batch

# GTFS-RT protobuf bindings
try:
    from google.transit import gtfs_realtime_pb2
    GTFS_RT_AVAILABLE = True
except ImportError:
    GTFS_RT_AVAILABLE = False
    logging.warning("gtfs-realtime-bindings not installed. Using JSON fallback.")

from config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class VehiclePosition:
    """Represents a single vehicle position observation."""
    vehicle_id: str
    route_id: Optional[str]
    trip_id: Optional[str]
    latitude: float
    longitude: float
    timestamp: datetime
    speed_kmh: Optional[float] = None
    bearing: Optional[float] = None
    
    def to_db_tuple(self) -> tuple:
        """Convert to tuple for database insertion."""
        return (
            self.timestamp,
            self.vehicle_id,
            self.route_id,
            self.trip_id,
            self.latitude,
            self.longitude,
            self.speed_kmh,
            self.bearing
        )


class GTFSRTWorker:
    """
    Worker that fetches and stores GTFS-RT vehicle positions from Roataway.
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ChisinauRoutingEngine/1.0',
            'Accept': 'application/x-protobuf, application/json'
        })
        self.running = False
        self.conn = None
        self.stats = {
            'total_fetches': 0,
            'successful_fetches': 0,
            'total_positions': 0,
            'last_fetch': None
        }
    
    def connect_db(self):
        """Establish database connection."""
        logger.info(f"Connecting to database: {settings.db.host}:{settings.db.port}")
        self.conn = psycopg2.connect(**settings.db.psycopg2_params)
        self.conn.set_session(autocommit=True)
        logger.info("Database connection established")
    
    def fetch_gtfs_rt_protobuf(self) -> List[VehiclePosition]:
        """
        Fetch vehicle positions from GTFS-RT protobuf endpoint.
        
        Returns:
            List of VehiclePosition objects
        """
        if not GTFS_RT_AVAILABLE:
            return self.fetch_json_fallback()
        
        try:
            response = self.session.get(
                settings.roataway.vehicle_positions_url,
                timeout=settings.roataway.timeout_seconds
            )
            response.raise_for_status()
            
            # Parse protobuf
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)
            
            positions = []
            feed_timestamp = datetime.fromtimestamp(
                feed.header.timestamp, 
                tz=timezone.utc
            ) if feed.header.timestamp else datetime.now(timezone.utc)
            
            for entity in feed.entity:
                if not entity.HasField('vehicle'):
                    continue
                
                vehicle = entity.vehicle
                pos = vehicle.position
                
                # Skip invalid positions
                if not (-90 <= pos.latitude <= 90 and -180 <= pos.longitude <= 180):
                    continue
                
                # Get timestamp
                if vehicle.timestamp:
                    ts = datetime.fromtimestamp(vehicle.timestamp, tz=timezone.utc)
                else:
                    ts = feed_timestamp
                
                # Get speed (convert m/s to km/h if present)
                speed_kmh = None
                if pos.HasField('speed') and pos.speed >= 0:
                    speed_kmh = pos.speed * 3.6  # m/s to km/h
                
                # Get bearing
                bearing = None
                if pos.HasField('bearing'):
                    bearing = pos.bearing
                
                positions.append(VehiclePosition(
                    vehicle_id=vehicle.vehicle.id or entity.id,
                    route_id=vehicle.trip.route_id if vehicle.HasField('trip') else None,
                    trip_id=vehicle.trip.trip_id if vehicle.HasField('trip') else None,
                    latitude=pos.latitude,
                    longitude=pos.longitude,
                    timestamp=ts,
                    speed_kmh=speed_kmh,
                    bearing=bearing
                ))
            
            return positions
            
        except Exception as e:
            logger.error(f"Error fetching GTFS-RT protobuf: {e}")
            # Try JSON fallback
            return self.fetch_json_fallback()
    
    def fetch_json_fallback(self) -> List[VehiclePosition]:
        """
        Fallback: Fetch vehicle positions from JSON API.
        
        Returns:
            List of VehiclePosition objects
        """
        try:
            response = self.session.get(
                settings.roataway.json_api_url,
                timeout=settings.roataway.timeout_seconds
            )
            response.raise_for_status()
            
            data = response.json()
            positions = []
            now = datetime.now(timezone.utc)
            
            # Handle various JSON structures
            vehicles = data if isinstance(data, list) else data.get('vehicles', data.get('data', []))
            
            for v in vehicles:
                try:
                    # Try different field names
                    lat = v.get('latitude') or v.get('lat') or v.get('position', {}).get('latitude')
                    lon = v.get('longitude') or v.get('lon') or v.get('lng') or v.get('position', {}).get('longitude')
                    
                    if lat is None or lon is None:
                        continue
                    
                    # Parse timestamp if available
                    ts_str = v.get('timestamp') or v.get('last_seen') or v.get('updated_at')
                    if ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                        except:
                            ts = now
                    else:
                        ts = now
                    
                    positions.append(VehiclePosition(
                        vehicle_id=str(v.get('id') or v.get('vehicle_id') or v.get('board')),
                        route_id=str(v.get('route_id') or v.get('route') or ''),
                        trip_id=v.get('trip_id'),
                        latitude=float(lat),
                        longitude=float(lon),
                        timestamp=ts,
                        speed_kmh=v.get('speed'),
                        bearing=v.get('bearing') or v.get('direction')
                    ))
                except (KeyError, ValueError, TypeError) as e:
                    logger.debug(f"Skipping malformed vehicle record: {e}")
                    continue
            
            return positions
            
        except Exception as e:
            logger.error(f"Error fetching JSON API: {e}")
            return []
    
    def store_positions(self, positions: List[VehiclePosition]):
        """
        Store vehicle positions in the database.
        
        Args:
            positions: List of VehiclePosition objects
        """
        if not positions:
            return
        
        insert_sql = """
            INSERT INTO trolleybus_telemetry (
                time, vehicle_id, route_id, trip_id,
                latitude, longitude, geom,
                speed_kmh, bearing
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                %s, %s
            )
        """
        
        try:
            with self.conn.cursor() as cur:
                records = []
                for pos in positions:
                    records.append((
                        pos.timestamp,
                        pos.vehicle_id,
                        pos.route_id,
                        pos.trip_id,
                        pos.latitude,
                        pos.longitude,
                        pos.longitude,  # For ST_MakePoint(lon, lat)
                        pos.latitude,
                        pos.speed_kmh,
                        pos.bearing
                    ))
                
                execute_batch(cur, insert_sql, records)
                # No commit needed - using autocommit mode
                
            self.stats['total_positions'] += len(positions)
            logger.debug(f"Stored {len(positions)} positions")
            
        except psycopg2.Error as e:
            logger.error(f"Database error storing positions: {e}")
            # Try to reconnect (no rollback needed in autocommit mode)
            try:
                self.conn.close()
                self.connect_db()
            except:
                pass
    
    def fetch_and_store(self):
        """Execute one fetch-and-store cycle."""
        self.stats['total_fetches'] += 1
        
        try:
            # Fetch positions
            positions = self.fetch_gtfs_rt_protobuf()
            
            if positions:
                self.store_positions(positions)
                self.stats['successful_fetches'] += 1
                self.stats['last_fetch'] = datetime.now()
                
                logger.info(
                    f"Fetched {len(positions)} vehicle positions | "
                    f"Total: {self.stats['total_positions']:,} | "
                    f"Success rate: {100*self.stats['successful_fetches']/self.stats['total_fetches']:.1f}%"
                )
            else:
                logger.warning("No vehicle positions received")
                
        except Exception as e:
            logger.error(f"Fetch cycle failed: {e}")
    
    def run(self):
        """
        Main run loop - polls GTFS-RT endpoint at configured interval.
        """
        logger.info("="*60)
        logger.info("Roataway GTFS-RT Telemetry Worker Starting")
        logger.info("="*60)
        logger.info(f"Protobuf URL: {settings.roataway.vehicle_positions_url}")
        logger.info(f"JSON Fallback: {settings.roataway.json_api_url}")
        logger.info(f"Poll interval: {settings.roataway.poll_interval_seconds} seconds")
        logger.info("="*60)
        
        # Connect to database
        self.connect_db()
        
        # Setup signal handlers for graceful shutdown
        self.running = True
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Initial fetch
        self.fetch_and_store()
        
        # Main loop
        while self.running:
            try:
                time.sleep(settings.roataway.poll_interval_seconds)
                if self.running:
                    self.fetch_and_store()
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(5)  # Brief pause before retrying
        
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
        """Print final statistics on shutdown."""
        print("\n" + "="*60)
        print("GTFS-RT WORKER FINAL STATISTICS")
        print("="*60)
        print(f"Total fetch attempts:  {self.stats['total_fetches']}")
        print(f"Successful fetches:    {self.stats['successful_fetches']}")
        print(f"Total positions stored: {self.stats['total_positions']:,}")
        if self.stats['last_fetch']:
            print(f"Last successful fetch: {self.stats['last_fetch']}")
        print("="*60 + "\n")


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(
        description='GTFS-RT telemetry worker for Roataway trolleybus data'
    )
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run as daemon (suppress non-error output)'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Fetch once and exit (for testing)'
    )
    args = parser.parse_args()
    
    if args.daemon:
        logging.getLogger().setLevel(logging.WARNING)
    
    worker = GTFSRTWorker()
    
    if args.once:
        worker.connect_db()
        worker.fetch_and_store()
        worker.conn.close()
    else:
        worker.run()


if __name__ == '__main__':
    main()
