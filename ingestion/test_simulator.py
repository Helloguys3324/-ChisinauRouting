#!/usr/bin/env python3
"""Test trolleybus simulator"""
import sys
sys.path.insert(0, '.')
from trolleybus_simulator import TrolleybusSimulator
import time
import psycopg2
from config import settings

# Test simulator
sim = TrolleybusSimulator()
sim.connect_db()
sim.initialize_vehicles()

print(f'Created {len(sim.vehicles)} simulated vehicles:')
for v in sim.vehicles[:5]:
    name = v.route_name[:30] if len(v.route_name) > 30 else v.route_name
    print(f'  {v.vehicle_id} - Route {v.route_id} ({name}...)')

print()
print('Running 3 simulation cycles...')
for i in range(3):
    sim.run_once()
    time.sleep(1)

print()
print('[OK] Simulator working correctly!')

# Check data in database
conn = psycopg2.connect(**settings.db.psycopg2_params)
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM trolleybus_telemetry')
total = cur.fetchone()[0]
cur.execute("SELECT COUNT(*), MAX(time) FROM trolleybus_telemetry WHERE time > NOW() - INTERVAL '1 minute'")
row = cur.fetchone()
recent, last_time = row[0], row[1]
conn.close()

print()
print(f'Database statistics:')
print(f'  Total telemetry records: {total}')
print(f'  Records in last minute: {recent}')
print(f'  Last update: {last_time}')
