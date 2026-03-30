"""
OSM Road Network Extractor for Chișinău

This script:
1. Downloads the drivable road network for Chișinău using OSMnx
2. Processes nodes and edges with proper attributes
3. Calculates base travel times (time = distance / max_speed)
4. Inserts data into PostgreSQL with PostGIS geometries

Usage:
    python osm_extractor.py [--clear]
    
    --clear: Drop existing nodes/edges and reload fresh data
"""

import argparse
import sys
import logging
from typing import Tuple, Optional
from datetime import datetime

import osmnx as ox
import networkx as nx
import psycopg2
from psycopg2.extras import execute_batch
from shapely.geometry import Point, LineString
from shapely import wkb

from config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_speed_for_highway(highway_type: str, maxspeed: Optional[str] = None) -> int:
    """
    Determine the speed limit for an edge.
    
    Priority:
    1. Explicit maxspeed tag from OSM (if parseable)
    2. Default speed for highway type
    3. Fallback to 30 km/h
    
    Args:
        highway_type: OSM highway tag value
        maxspeed: OSM maxspeed tag value (may be string like "50", "50 mph", etc.)
    
    Returns:
        Speed in km/h
    """
    # Try to parse explicit maxspeed
    if maxspeed:
        try:
            # Handle various formats: "50", "50 km/h", "30 mph"
            speed_str = str(maxspeed).lower().strip()
            
            # Remove units
            for unit in ['km/h', 'kmh', 'kph', 'mph']:
                speed_str = speed_str.replace(unit, '').strip()
            
            speed = int(float(speed_str))
            
            # Convert mph to km/h if needed
            if 'mph' in str(maxspeed).lower():
                speed = int(speed * 1.60934)
            
            # Sanity check
            if 5 <= speed <= 150:
                return speed
        except (ValueError, TypeError):
            pass
    
    # Use default for highway type
    if isinstance(highway_type, list):
        highway_type = highway_type[0]  # Take first if list
    
    return settings.osm.default_speeds.get(highway_type, 30)


def download_network() -> nx.MultiDiGraph:
    """
    Download the road network for Chișinău using OSMnx.
    
    Returns:
        NetworkX MultiDiGraph with nodes and edges
    """
    logger.info(f"Downloading road network for: {settings.osm.place_name}")
    
    # Configure osmnx
    ox.settings.log_console = settings.debug
    ox.settings.use_cache = True
    ox.settings.cache_folder = './osm_cache'
    
    try:
        # Try geocoding by place name first
        G = ox.graph_from_place(
            settings.osm.place_name,
            network_type=settings.osm.network_type,
            simplify=True,
            retain_all=False,
            truncate_by_edge=True
        )
        logger.info(f"Downloaded network by place name: {settings.osm.place_name}")
        
    except Exception as e:
        logger.warning(f"Place name geocoding failed: {e}")
        logger.info("Falling back to bounding box...")
        
        # Fall back to explicit bounding box
        G = ox.graph_from_bbox(
            bbox=(
                settings.osm.bbox_north,
                settings.osm.bbox_south,
                settings.osm.bbox_east,
                settings.osm.bbox_west
            ),
            network_type=settings.osm.network_type,
            simplify=True,
            retain_all=False,
            truncate_by_edge=True
        )
        logger.info("Downloaded network by bounding box")
    
    # Add edge geometries if not present
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)
    
    logger.info(f"Network stats: {len(G.nodes)} nodes, {len(G.edges)} edges")
    
    return G


def process_network(G: nx.MultiDiGraph) -> Tuple[list, list]:
    """
    Process the OSMnx graph into node and edge records for database insertion.
    
    Args:
        G: NetworkX MultiDiGraph from OSMnx
    
    Returns:
        Tuple of (nodes_list, edges_list)
    """
    logger.info("Processing network data...")
    
    nodes = []
    edges = []
    
    # Process nodes
    for node_id, data in G.nodes(data=True):
        nodes.append({
            'id': int(node_id),
            'lat': data['y'],
            'lon': data['x']
        })
    
    logger.info(f"Processed {len(nodes)} nodes")
    
    # Process edges
    edge_count = 0
    for u, v, key, data in G.edges(keys=True, data=True):
        # Get edge geometry
        if 'geometry' in data:
            geom = data['geometry']
        else:
            # Create straight line if no geometry
            u_data = G.nodes[u]
            v_data = G.nodes[v]
            geom = LineString([
                (u_data['x'], u_data['y']),
                (v_data['x'], v_data['y'])
            ])
        
        # Get highway type
        highway = data.get('highway', 'unclassified')
        if isinstance(highway, list):
            highway = highway[0]
        
        # Get length in meters
        length_m = data.get('length', geom.length * 111320)  # Approximate if not available
        
        # Get speed
        maxspeed = data.get('maxspeed')
        speed_kmh = get_speed_for_highway(highway, maxspeed)
        
        # Calculate base travel time (seconds)
        # time = distance / speed
        # Convert: m / (km/h) = m / (km/h * 1000/3600) = m / (m/s) = seconds
        speed_ms = speed_kmh * 1000 / 3600  # Convert km/h to m/s
        base_time_sec = length_m / speed_ms if speed_ms > 0 else length_m / 8.33  # Fallback 30 km/h
        
        # Get other attributes
        name = data.get('name', '')
        if isinstance(name, list):
            name = ', '.join(str(n) for n in name)
        
        oneway = data.get('oneway', False)
        osm_way_id = data.get('osmid', 0)
        if isinstance(osm_way_id, list):
            osm_way_id = osm_way_id[0]
        
        edges.append({
            'osm_way_id': int(osm_way_id) if osm_way_id else None,
            'source_node': int(u),
            'target_node': int(v),
            'geometry': geom,
            'highway_type': highway,
            'name': name[:255] if name else None,
            'oneway': bool(oneway),
            'length_m': float(round(length_m, 2)),
            'max_speed_kmh': int(speed_kmh),
            'base_time_sec': float(round(base_time_sec, 2))
        })
        edge_count += 1
    
    logger.info(f"Processed {edge_count} edges")
    
    return nodes, edges


def insert_nodes(conn, nodes: list, batch_size: int = 1000):
    """
    Insert nodes into the database.
    
    Args:
        conn: psycopg2 connection
        nodes: List of node dictionaries
        batch_size: Number of records per batch
    """
    logger.info(f"Inserting {len(nodes)} nodes...")
    
    insert_sql = """
        INSERT INTO nodes (id, geom)
        VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
        ON CONFLICT (id) DO UPDATE SET
            geom = EXCLUDED.geom
    """
    
    with conn.cursor() as cur:
        batch = []
        for node in nodes:
            batch.append((node['id'], node['lon'], node['lat']))
            
            if len(batch) >= batch_size:
                execute_batch(cur, insert_sql, batch)
                batch = []
        
        if batch:
            execute_batch(cur, insert_sql, batch)
        
        conn.commit()
    
    logger.info("Nodes inserted successfully")


def insert_edges(conn, edges: list, batch_size: int = 500):
    """
    Insert edges into the database.
    
    Args:
        conn: psycopg2 connection
        edges: List of edge dictionaries
        batch_size: Number of records per batch
    """
    logger.info(f"Inserting {len(edges)} edges...")
    
    insert_sql = """
        INSERT INTO edges (
            osm_way_id, source_node, target_node, geom,
            highway_type, name, oneway,
            length_m, max_speed_kmh, base_time_sec
        )
        VALUES (
            %s, %s, %s, ST_SetSRID(ST_GeomFromText(%s), 4326),
            %s, %s, %s,
            %s, %s, %s
        )
    """
    
    with conn.cursor() as cur:
        batch = []
        for edge in edges:
            # Convert geometry to WKT
            geom_wkt = edge['geometry'].wkt
            
            batch.append((
                edge['osm_way_id'],
                edge['source_node'],
                edge['target_node'],
                geom_wkt,
                edge['highway_type'],
                edge['name'],
                edge['oneway'],
                edge['length_m'],
                edge['max_speed_kmh'],
                edge['base_time_sec']
            ))
            
            if len(batch) >= batch_size:
                execute_batch(cur, insert_sql, batch)
                conn.commit()
                logger.info(f"  Inserted batch of {len(batch)} edges...")
                batch = []
        
        if batch:
            execute_batch(cur, insert_sql, batch)
            conn.commit()
    
    logger.info("Edges inserted successfully")


def clear_existing_data(conn):
    """Remove existing nodes and edges from the database."""
    logger.warning("Clearing existing graph data...")
    
    with conn.cursor() as cur:
        # Clear dependent tables first
        cur.execute("DELETE FROM edge_speed_profiles")
        cur.execute("UPDATE trolleybus_telemetry SET matched_edge_id = NULL")
        
        # Clear main tables
        cur.execute("DELETE FROM edges")
        cur.execute("DELETE FROM nodes")
        
        conn.commit()
    
    logger.info("Existing data cleared")


def print_statistics(conn):
    """Print database statistics after import."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM nodes")
        node_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM edges")
        edge_count = cur.fetchone()[0]
        
        cur.execute("""
            SELECT highway_type, COUNT(*), 
                   ROUND(AVG(length_m)::numeric, 1) as avg_length,
                   ROUND(AVG(max_speed_kmh)::numeric, 1) as avg_speed
            FROM edges 
            GROUP BY highway_type 
            ORDER BY COUNT(*) DESC
            LIMIT 10
        """)
        highway_stats = cur.fetchall()
        
        cur.execute("SELECT SUM(length_m) / 1000 FROM edges")
        total_km = cur.fetchone()[0]
    
    print("\n" + "="*60)
    print("OSM IMPORT STATISTICS")
    print("="*60)
    print(f"Total Nodes:     {node_count:,}")
    print(f"Total Edges:     {edge_count:,}")
    print(f"Total Road Length: {total_km:,.1f} km")
    print("\nEdges by Highway Type:")
    print("-"*60)
    print(f"{'Type':<20} {'Count':>10} {'Avg Length (m)':>15} {'Avg Speed':>12}")
    print("-"*60)
    for row in highway_stats:
        print(f"{row[0]:<20} {row[1]:>10,} {row[2]:>15} {row[3]:>12}")
    print("="*60 + "\n")


def main():
    """Main entry point for OSM extraction."""
    parser = argparse.ArgumentParser(
        description='Extract OSM road network for Chișinău and import to PostgreSQL'
    )
    parser.add_argument(
        '--clear',
        action='store_true',
        help='Clear existing data before import'
    )
    args = parser.parse_args()
    
    start_time = datetime.now()
    logger.info("="*60)
    logger.info("Chișinău OSM Road Network Extractor")
    logger.info("="*60)
    
    # Connect to database
    logger.info(f"Connecting to database: {settings.db.host}:{settings.db.port}/{settings.db.name}")
    
    try:
        conn = psycopg2.connect(**settings.db.psycopg2_params)
        logger.info("Database connection successful")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        logger.error("Make sure PostgreSQL is running and the database exists.")
        logger.error("See database/setup_instructions.md for setup guide.")
        sys.exit(1)
    
    try:
        # Clear existing data if requested
        if args.clear:
            clear_existing_data(conn)
        
        # Download network
        G = download_network()
        
        # Process into records
        nodes, edges = process_network(G)
        
        # Insert into database
        insert_nodes(conn, nodes)
        insert_edges(conn, edges)
        
        # Print statistics
        print_statistics(conn)
        
        elapsed = datetime.now() - start_time
        logger.info(f"Import completed in {elapsed.total_seconds():.1f} seconds")
        
    except Exception as e:
        logger.error(f"Import failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
