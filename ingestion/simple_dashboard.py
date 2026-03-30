#!/usr/bin/env python3
"""
Simple Dashboard (without workers) - for testing DB connection
"""
import os
import sys
import time
import psycopg2
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import settings


def fetch_data():
    """Fetch basic statistics from database"""
    try:
        conn = psycopg2.connect(**settings.db.psycopg2_params, connect_timeout=5)
        conn.set_session(autocommit=True)
        cur = conn.cursor()
        
        # Get road network stats
        cur.execute('SELECT COUNT(*) FROM nodes')
        nodes = cur.fetchone()[0]
        
        cur.execute('SELECT COUNT(*) FROM edges')
        edges = cur.fetchone()[0]
        
        cur.execute('SELECT SUM(length_m) FROM edges')
        total_length = cur.fetchone()[0] or 0
        
        # Get traffic data count (last 30 minutes)
        cur.execute("SELECT COUNT(*) FROM tomtom_traffic WHERE time > NOW() - INTERVAL '30 minutes'")
        traffic_30min = cur.fetchone()[0]
        
        # Get total traffic records
        cur.execute("SELECT COUNT(*) FROM tomtom_traffic")
        traffic_total = cur.fetchone()[0]
        
        conn.close()
        return {
            'nodes': nodes,
            'edges': edges,
            'length_km': total_length / 1000,
            'traffic_30min': traffic_30min,
            'traffic_total': traffic_total,
            'status': 'OK'
        }
    except Exception as e:
        return {
            'status': 'ERROR',
            'error': str(e)
        }


def clear_screen():
    """Clear console screen"""
    os.system('cls' if os.name == 'nt' else 'clear')


def render_dashboard(data):
    """Render dashboard output"""
    clear_screen()
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    print()
    print("=" * 70)
    print("     CHISINAU ROUTING ENGINE - LIVE DASHBOARD (SIMPLE)     ")
    print("=" * 70)
    print(f"  {now}                         Press Ctrl+C to exit")
    print("=" * 70)
    print()
    
    if data['status'] == 'OK':
        print("  [OK] Database connected")
        print()
        print("  ROAD NETWORK:")
        print(f"    Nodes:        {data['nodes']:,}")
        print(f"    Edges:        {data['edges']:,}")
        print(f"    Total length: {data['length_km']:.1f} km")
        print()
        print("  TRAFFIC DATA:")
        print(f"    Last 30 min:  {data['traffic_30min']} records")
        print(f"    Total stored: {data['traffic_total']} records")
        print()
        print("  WORKERS: [DISABLED]")
        print("    GTFS-RT:      Not running (test mode)")
        print("    TomTom:       Not running (test mode)")
    else:
        print("  [ERROR] Cannot connect to database!")
        print(f"  Error: {data.get('error', 'Unknown error')}")
        print()
        print("  Make sure PostgreSQL is running:")
        print("    D:\\PostgreSQL\\start_postgres.bat")
    
    print()
    print("=" * 70)
    print("  Refreshing every 5 seconds...")
    print("=" * 70)


def main():
    """Main loop"""
    print()
    print("Starting simple dashboard...")
    print("This version does NOT start workers (GTFS-RT, TomTom)")
    print("It only displays data from the database.")
    print()
    
    try:
        while True:
            data = fetch_data()
            render_dashboard(data)
            time.sleep(5)
    except KeyboardInterrupt:
        print()
        print()
        print("Dashboard stopped by user.")
        print()


if __name__ == '__main__':
    main()
