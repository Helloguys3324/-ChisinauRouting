#!/usr/bin/env python3
"""
Chisinau Routing Engine - Live Dashboard
=========================================
One-click launcher for all system components with live statistics display.

Run: python dashboard.py
"""

import os
import sys
import time
import signal
import subprocess
import threading
import psycopg2
from datetime import datetime, timedelta
from collections import defaultdict

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings

# ANSI colors for terminal
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

# Global state
running = True
workers = []
db_conn = None  # Persistent database connection
stats = {
    'trolleybuses': {},
    'last_telemetry': None,
    'telemetry_count': 0,
    'tomtom_count': 0,
    'last_tomtom': None,
    'errors': []
}


def clear_screen():
    """Clear terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def get_db_connection():
    """Get or create persistent database connection."""
    global db_conn
    
    # Test existing connection
    if db_conn is not None:
        try:
            # Quick test query
            with db_conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return db_conn
        except:
            # Connection dead, close and reconnect
            try:
                db_conn.close()
            except:
                pass
            db_conn = None
    
    # Create new connection
    try:
        db_conn = psycopg2.connect(**settings.db.psycopg2_params, connect_timeout=10)
        db_conn.set_session(autocommit=True)  # Autocommit to avoid transactions
        return db_conn
    except Exception as e:
        stats['errors'].append(f"DB Error: {str(e)[:80]}")
        return None


def close_db_connection():
    """Close persistent database connection."""
    global db_conn
    if db_conn:
        try:
            db_conn.close()
        except:
            pass
        db_conn = None


def fetch_statistics():
    """Fetch current statistics from database."""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as cur:
            # Node/edge counts
            cur.execute("SELECT COUNT(*) FROM nodes")
            nodes = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM edges")
            edges = cur.fetchone()[0]
            
            cur.execute("SELECT ROUND(SUM(length_m)::numeric/1000, 1) FROM edges")
            total_km = cur.fetchone()[0] or 0
            
            # Recent telemetry
            cur.execute("""
                SELECT COUNT(*), MAX(time)
                FROM trolleybus_telemetry 
                WHERE time > NOW() - INTERVAL '5 minutes'
            """)
            row = cur.fetchone()
            recent_telemetry = row[0]
            last_telemetry = row[1]
            
            # Active vehicles in last 5 min
            cur.execute("""
                SELECT vehicle_id, route_id, latitude, longitude, speed_kmh, time
                FROM trolleybus_telemetry
                WHERE time > NOW() - INTERVAL '5 minutes'
                ORDER BY time DESC
            """)
            vehicles = {}
            for row in cur.fetchall():
                vid = row[0]
                if vid not in vehicles:
                    vehicles[vid] = {
                        'route': row[1],
                        'lat': row[2],
                        'lon': row[3],
                        'speed': row[4],
                        'time': row[5]
                    }
            
            # TomTom data
            cur.execute("""
                SELECT COUNT(*), MAX(time)
                FROM tomtom_traffic
                WHERE time > NOW() - INTERVAL '30 minutes'
            """)
            row = cur.fetchone()
            tomtom_count = row[0]
            last_tomtom = row[1]
            
            # Total telemetry records
            cur.execute("SELECT COUNT(*) FROM trolleybus_telemetry")
            total_telemetry = cur.fetchone()[0]
            
            return {
                'nodes': nodes,
                'edges': edges,
                'total_km': total_km,
                'recent_telemetry': recent_telemetry,
                'last_telemetry': last_telemetry,
                'vehicles': vehicles,
                'tomtom_count': tomtom_count,
                'last_tomtom': last_tomtom,
                'total_telemetry': total_telemetry
            }
    except Exception as e:
        stats['errors'].append(str(e))
        return None
    # Don't close connection - reuse it!


def format_time_ago(dt):
    """Format datetime as 'X seconds/minutes ago'."""
    if not dt:
        return "Never"
    
    # Handle timezone-naive comparison
    now = datetime.now()
    if dt.tzinfo:
        from datetime import timezone
        now = datetime.now(timezone.utc)
    
    diff = now - dt
    seconds = int(diff.total_seconds())
    
    if seconds < 60:
        return f"{seconds}s ago"
    elif seconds < 3600:
        return f"{seconds // 60}m ago"
    else:
        return f"{seconds // 3600}h ago"


def draw_dashboard(data):
    """Draw the dashboard to terminal."""
    clear_screen()
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"{Colors.BOLD}{Colors.CYAN}")
    print("=" * 70)
    print("     CHISINAU ROUTING ENGINE - LIVE DASHBOARD")
    print("=" * 70)
    print(f"  {now}                        Press Ctrl+C to exit")
    print("=" * 70)
    print(f"{Colors.END}")
    print()
    
    if not data:
        print(f"{Colors.RED}WARNING: Cannot connect to database!{Colors.END}")
        print(f"  Make sure PostgreSQL is running on localhost:5432")
        return
    
    # Graph Statistics
    print(f"{Colors.BOLD}{Colors.GREEN}ROAD NETWORK{Colors.END}")
    print(f"   Nodes: {data['nodes']:,}    Edges: {data['edges']:,}    Total: {data['total_km']} km")
    print()
    
    # Telemetry Status
    print(f"{Colors.BOLD}{Colors.YELLOW}TROLLEYBUS TELEMETRY{Colors.END}")
    print(f"   Total records: {data['total_telemetry']:,}")
    print(f"   Last 5 min:    {data['recent_telemetry']} records")
    print(f"   Last update:   {format_time_ago(data['last_telemetry'])}")
    print()
    
    # Active Vehicles
    vehicles = data.get('vehicles', {})
    if vehicles:
        print(f"{Colors.BOLD}{Colors.BLUE}ACTIVE VEHICLES ({len(vehicles)}){Colors.END}")
        print(f"   {'ID':<10} {'Route':<10} {'Speed':<8} {'Position':<25} {'Updated'}")
        print(f"   {'-'*10} {'-'*10} {'-'*8} {'-'*25} {'-'*12}")
        
        # Show up to 10 vehicles
        for i, (vid, v) in enumerate(list(vehicles.items())[:10]):
            speed_str = f"{v['speed']:.1f} km/h" if v['speed'] else "N/A"
            pos = f"({v['lat']:.4f}, {v['lon']:.4f})"
            updated = format_time_ago(v['time'])
            print(f"   {vid:<10} {v['route']:<10} {speed_str:<8} {pos:<25} {updated}")
        
        if len(vehicles) > 10:
            print(f"   ... and {len(vehicles) - 10} more vehicles")
    else:
        print(f"{Colors.YELLOW}   No active vehicles in last 5 minutes{Colors.END}")
        print(f"   (Waiting for GTFS-RT data from Roataway...)")
    print()
    
    # TomTom Status
    print(f"{Colors.BOLD}{Colors.CYAN}TOMTOM TRAFFIC{Colors.END}")
    print(f"   Records (30 min): {data['tomtom_count']}")
    print(f"   Last update:      {format_time_ago(data['last_tomtom'])}")
    print()
    
    # Worker Status
    print(f"{Colors.BOLD}WORKERS{Colors.END}")
    for w in workers:
        status = "[Running]" if w['process'].poll() is None else "[Stopped]"
        print(f"   {w['name']}: {status}")
    print()
    
    # Errors
    if stats['errors']:
        print(f"{Colors.RED}ERRORS:{Colors.END}")
        for err in stats['errors'][-3:]:
            print(f"   {err[:70]}")


def start_worker(name: str, script: str):
    """Start a worker subprocess."""
    python_exe = os.path.join(os.path.dirname(__file__), 'venv', 'Scripts', 'python.exe')
    script_path = os.path.join(os.path.dirname(__file__), script)
    
    if not os.path.exists(python_exe):
        python_exe = sys.executable
    
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    
    try:
        proc = subprocess.Popen(
            [python_exe, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(__file__),
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        workers.append({'name': name, 'process': proc})
        return True
    except Exception as e:
        stats['errors'].append(f"Failed to start {name}: {e}")
        return False


def stop_all_workers():
    """Stop all worker processes."""
    for w in workers:
        try:
            w['process'].terminate()
            w['process'].wait(timeout=5)
        except:
            try:
                w['process'].kill()
            except:
                pass


def signal_handler(sig, frame):
    """Handle Ctrl+C."""
    global running
    running = False
    print(f"\n{Colors.YELLOW}Shutting down...{Colors.END}")


def main():
    global running
    
    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, signal_handler)
    
    clear_screen()
    print(f"{Colors.BOLD}{Colors.CYAN}")
    print("=" * 66)
    print("    STARTING CHISINAU ROUTING ENGINE...")
    print("=" * 66)
    print(f"{Colors.END}")
    
    # Check database connection
    print("Checking database connection...")
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(1, max_retries + 1):
        conn = get_db_connection()
        if conn:
            conn.close()
            print(f"{Colors.GREEN}[OK] Database connected{Colors.END}")
            break
        else:
            if attempt < max_retries:
                print(f"{Colors.YELLOW}   Attempt {attempt}/{max_retries} failed, retrying in {retry_delay}s...{Colors.END}")
                if stats['errors']:
                    print(f"   Error: {stats['errors'][-1]}")
                time.sleep(retry_delay)
            else:
                print(f"{Colors.RED}[ERROR] Cannot connect to database after {max_retries} attempts!{Colors.END}")
                print(f"\n   Connection details:")
                print(f"   Host: {settings.db.host}")
                print(f"   Port: {settings.db.port}")
                print(f"   Database: {settings.db.name}")
                print(f"   User: {settings.db.user}")
                if stats['errors']:
                    print(f"\n   Last error: {stats['errors'][-1]}")
                print(f"\n   Troubleshooting:")
                print(f"   1. Check PostgreSQL is running: D:\\PostgreSQL\\start_postgres.bat")
                print(f"   2. Check log: D:\\PostgreSQL\\postgresql.log")
                print(f"   3. Try manual connection: D:\\ChisinauRouting\\routing.bat psql")
                input("\nPress Enter to exit...")
                return
    
    # Start workers
    print("\nStarting workers...")
    
    # Use simulator instead of real GTFS-RT worker (Roataway API is down)
    print("  Starting Trolleybus Simulator (Roataway API unavailable)...")
    start_worker("Trolleybus Simulator", "trolleybus_simulator.py")
    
    print("  Starting TomTom worker (traffic data)...")
    start_worker("TomTom Worker", "tomtom_worker.py")
    
    print(f"\n{Colors.GREEN}[OK] All workers started{Colors.END}")
    print(f"\nRefreshing dashboard every 5 seconds...")
    print(f"Press Ctrl+C to stop and exit.\n")
    time.sleep(2)
    
    # Main dashboard loop
    try:
        while running:
            data = fetch_statistics()
            draw_dashboard(data)
            
            # Sleep with interrupt check
            for _ in range(50):  # 5 seconds in 0.1s chunks
                if not running:
                    break
                time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        print(f"\n{Colors.YELLOW}Stopping workers...{Colors.END}")
        stop_all_workers()
        print(f"{Colors.GREEN}[OK] All workers stopped{Colors.END}")
        close_db_connection()
        print(f"{Colors.GREEN}[OK] Shutdown complete{Colors.END}")


if __name__ == '__main__':
    main()
