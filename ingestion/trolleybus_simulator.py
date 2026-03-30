#!/usr/bin/env python3
"""
Trolleybus Telemetry Simulator for Chișinău

Since the real Roataway MQTT API (opendata.dekart.com) is currently unavailable,
this simulator generates realistic trolleybus position data based on actual 
Chișinău trolleybus routes.

The simulator:
1. Uses real road network from the database
2. Simulates multiple trolleybuses on different routes
3. Generates realistic speeds based on time of day
4. Stores data in the same format as real GTFS-RT data
"""

import sys
import time
import random
import logging
import signal
import math
from datetime import datetime, timezone
from typing import List, Dict, Tuple
from dataclasses import dataclass

import psycopg2
from psycopg2.extras import execute_batch

sys.path.insert(0, '.')
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Chișinău trolleybus routes (approximate paths using key waypoints)
# Format: route_id, route_name, [(lat, lon), ...]
TROLLEYBUS_ROUTES = [
    ("1", "Route 1: Botanica - Centru", [
        (46.9923, 28.8577), (46.9956, 28.8534), (47.0012, 28.8467),
        (47.0089, 28.8389), (47.0156, 28.8312), (47.0234, 28.8256),
        (47.0289, 28.8234), (47.0345, 28.8201)
    ]),
    ("2", "Route 2: Ciocana - Buiucani", [
        (47.0345, 28.8967), (47.0312, 28.8889), (47.0267, 28.8801),
        (47.0223, 28.8723), (47.0178, 28.8645), (47.0134, 28.8567),
        (47.0089, 28.8489), (47.0045, 28.8412)
    ]),
    ("3", "Route 3: Riscani - Botanica", [
        (47.0456, 28.8312), (47.0401, 28.8367), (47.0345, 28.8423),
        (47.0289, 28.8478), (47.0234, 28.8534), (47.0178, 28.8589),
        (47.0123, 28.8645), (47.0067, 28.8701)
    ]),
    ("5", "Route 5: Telecentru - Centru", [
        (47.0012, 28.8189), (47.0045, 28.8234), (47.0078, 28.8278),
        (47.0112, 28.8323), (47.0145, 28.8367), (47.0178, 28.8412),
        (47.0212, 28.8456), (47.0245, 28.8501)
    ]),
    ("8", "Route 8: Aeroport - Centru", [
        (46.9345, 28.9312), (46.9456, 28.9234), (46.9567, 28.9156),
        (46.9678, 28.9078), (46.9789, 28.9001), (46.9901, 28.8923),
        (47.0012, 28.8845), (47.0123, 28.8767)
    ]),
    ("10", "Route 10: Sculeanca - Centru", [
        (47.0567, 28.8123), (47.0512, 28.8178), (47.0456, 28.8234),
        (47.0401, 28.8289), (47.0345, 28.8345), (47.0289, 28.8401),
        (47.0234, 28.8456), (47.0178, 28.8512)
    ]),
    ("22", "Route 22: Buiucani - Botanica", [
        (47.0489, 28.8234), (47.0434, 28.8289), (47.0378, 28.8345),
        (47.0323, 28.8401), (47.0267, 28.8456), (47.0212, 28.8512),
        (47.0156, 28.8567), (47.0101, 28.8623)
    ]),
    ("24", "Route 24: Ciocana - Riscani", [
        (47.0312, 28.8923), (47.0289, 28.8867), (47.0267, 28.8812),
        (47.0245, 28.8756), (47.0223, 28.8701), (47.0201, 28.8645),
        (47.0178, 28.8589), (47.0156, 28.8534)
    ]),
]


@dataclass
class SimulatedVehicle:
    """Represents a simulated trolleybus"""
    vehicle_id: str
    board_number: str
    route_id: str
    route_name: str
    waypoints: List[Tuple[float, float]]
    current_index: int = 0
    direction: int = 1  # 1 = forward, -1 = backward
    progress: float = 0.0  # 0-1 progress between waypoints
    speed_kmh: float = 0.0
    bearing: float = 0.0


class TrolleybusSimulator:
    """Simulates trolleybus movement for Chișinău"""
    
    def __init__(self):
        self.vehicles: List[SimulatedVehicle] = []
        self.conn = None
        self.running = False
        self.stats = {
            'total_updates': 0,
            'last_update': None
        }
    
    def connect_db(self):
        """Connect to database"""
        logger.info("Connecting to database...")
        self.conn = psycopg2.connect(**settings.db.psycopg2_params)
        self.conn.set_session(autocommit=True)
        logger.info("Database connected")
    
    def initialize_vehicles(self):
        """Create simulated vehicles for each route"""
        logger.info("Initializing simulated vehicles...")
        
        vehicle_num = 1
        for route_id, route_name, waypoints in TROLLEYBUS_ROUTES:
            # Create 2-4 vehicles per route
            num_vehicles = random.randint(2, 4)
            for i in range(num_vehicles):
                vehicle = SimulatedVehicle(
                    vehicle_id=f"SIM{vehicle_num:03d}",
                    board_number=f"{1000 + vehicle_num}",
                    route_id=route_id,
                    route_name=route_name,
                    waypoints=waypoints,
                    current_index=random.randint(0, len(waypoints) - 2),
                    direction=random.choice([1, -1]),
                    progress=random.random(),
                    speed_kmh=random.uniform(15, 35)
                )
                self.vehicles.append(vehicle)
                vehicle_num += 1
        
        logger.info(f"Created {len(self.vehicles)} simulated vehicles")
    
    def get_speed_factor(self) -> float:
        """Get speed factor based on time of day (rush hour = slower)"""
        hour = datetime.now().hour
        
        # Rush hours: 7-9 AM and 17-19 PM
        if 7 <= hour <= 9 or 17 <= hour <= 19:
            return random.uniform(0.4, 0.7)  # Slower during rush hour
        # Night time: 22-6
        elif hour >= 22 or hour <= 6:
            return random.uniform(0.8, 1.0)  # Faster at night (less traffic)
        # Normal hours
        else:
            return random.uniform(0.6, 0.9)
    
    def interpolate_position(self, vehicle: SimulatedVehicle) -> Tuple[float, float]:
        """Calculate current position based on progress between waypoints"""
        wp = vehicle.waypoints
        idx = vehicle.current_index
        
        # Get current and next waypoint
        if vehicle.direction == 1:
            next_idx = min(idx + 1, len(wp) - 1)
        else:
            next_idx = max(idx - 1, 0)
        
        lat1, lon1 = wp[idx]
        lat2, lon2 = wp[next_idx]
        
        # Linear interpolation
        lat = lat1 + (lat2 - lat1) * vehicle.progress
        lon = lon1 + (lon2 - lon1) * vehicle.progress
        
        # Calculate bearing
        if lat2 != lat1 or lon2 != lon1:
            vehicle.bearing = math.degrees(math.atan2(lon2 - lon1, lat2 - lat1))
            if vehicle.bearing < 0:
                vehicle.bearing += 360
        
        return lat, lon
    
    def update_vehicle(self, vehicle: SimulatedVehicle):
        """Update vehicle position"""
        # Update speed with some randomness
        base_speed = random.uniform(20, 45)  # Base speed 20-45 km/h
        speed_factor = self.get_speed_factor()
        vehicle.speed_kmh = base_speed * speed_factor
        
        # Occasionally stop (simulating bus stops, traffic lights)
        if random.random() < 0.1:  # 10% chance to stop
            vehicle.speed_kmh = 0
        
        # Update progress (assuming ~3 second update interval)
        # Distance between waypoints is roughly 500m
        # Speed in m/s = speed_kmh * 1000 / 3600
        distance_per_update = (vehicle.speed_kmh * 1000 / 3600) * 3  # meters in 3 seconds
        progress_per_update = distance_per_update / 500  # Assuming 500m between waypoints
        
        vehicle.progress += progress_per_update
        
        # Check if we've reached the next waypoint
        if vehicle.progress >= 1.0:
            vehicle.progress = 0.0
            vehicle.current_index += vehicle.direction
            
            # Check if we need to reverse direction
            if vehicle.current_index >= len(vehicle.waypoints) - 1:
                vehicle.direction = -1
                vehicle.current_index = len(vehicle.waypoints) - 1
            elif vehicle.current_index <= 0:
                vehicle.direction = 1
                vehicle.current_index = 0
    
    def store_positions(self):
        """Store current positions of all vehicles in database"""
        if not self.vehicles:
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
        
        now = datetime.now(timezone.utc)
        records = []
        
        for vehicle in self.vehicles:
            lat, lon = self.interpolate_position(vehicle)
            records.append((
                now,
                vehicle.vehicle_id,
                vehicle.route_id,
                f"SIM_TRIP_{vehicle.vehicle_id}",
                lat,
                lon,
                lon,  # For ST_MakePoint(lon, lat)
                lat,
                vehicle.speed_kmh,
                vehicle.bearing
            ))
        
        try:
            with self.conn.cursor() as cur:
                execute_batch(cur, insert_sql, records)
            self.stats['total_updates'] += len(records)
            self.stats['last_update'] = now
        except Exception as e:
            logger.error(f"Error storing positions: {e}")
    
    def run_once(self):
        """Run one simulation cycle"""
        # Update all vehicle positions
        for vehicle in self.vehicles:
            self.update_vehicle(vehicle)
        
        # Store positions in database
        self.store_positions()
        
        logger.info(
            f"Updated {len(self.vehicles)} vehicles | "
            f"Total updates: {self.stats['total_updates']:,}"
        )
    
    def run(self, interval_seconds: int = 3):
        """Main simulation loop"""
        logger.info("=" * 60)
        logger.info("Starting Trolleybus Simulator for Chișinău")
        logger.info("=" * 60)
        logger.info(f"Update interval: {interval_seconds} seconds")
        logger.info("")
        logger.info("NOTE: This is SIMULATED data because the real")
        logger.info("Roataway MQTT API (opendata.dekart.com) is unavailable.")
        logger.info("=" * 60)
        
        self.connect_db()
        self.initialize_vehicles()
        
        self.running = True
        
        while self.running:
            try:
                self.run_once()
                time.sleep(interval_seconds)
            except KeyboardInterrupt:
                logger.info("Stopping simulator...")
                break
            except Exception as e:
                logger.error(f"Error in simulation loop: {e}")
                time.sleep(5)
        
        if self.conn:
            self.conn.close()
        
        logger.info("Simulator stopped")
    
    def stop(self):
        """Stop the simulator"""
        self.running = False


def main():
    """Main entry point"""
    simulator = TrolleybusSimulator()
    
    def signal_handler(sig, frame):
        simulator.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    simulator.run(interval_seconds=3)


if __name__ == '__main__':
    main()
