#!/usr/bin/env python3
"""Final test to verify dashboard with simulated data"""
import sys
sys.path.insert(0, '.')
import importlib
import dashboard
importlib.reload(dashboard)

print('Testing fetch_statistics() with simulated data...')
data = dashboard.fetch_statistics()
if data:
    print('[OK] Data fetched successfully!')
    print()
    print(f'  Nodes: {data["nodes"]:,}')
    print(f'  Edges: {data["edges"]:,}')
    print(f'  Total km: {data["total_km"]}')
    print()
    print(f'  Trolleybus telemetry (total): {data["total_telemetry"]}')
    print(f'  Trolleybus telemetry (5 min): {data["recent_telemetry"]}')
    print(f'  Active vehicles: {len(data["vehicles"])}')
    print()
    print(f'  TomTom records (30 min): {data["tomtom_count"]}')
    
    if data['vehicles']:
        print()
        print('  Sample vehicles:')
        for vid, vdata in list(data['vehicles'].items())[:3]:
            speed = vdata['speed'] or 0
            print(f'    {vid}: Route {vdata["route"]}, Speed {speed:.0f} km/h')
else:
    print('[ERROR] No data returned!')
