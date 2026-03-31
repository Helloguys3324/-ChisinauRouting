#!/usr/bin/env python3
"""
Chișinău Routing Engine - Web Application Server

Beautiful 3D map interface with real-time trolleybus tracking.
Uses MapLibre GL JS for Google Maps-like experience.
"""

import os
import sys
import json
import time
import random
import math
import threading
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ingestion'))

# Try to import config, fall back to defaults if not available (for cloud deployment)
try:
    import psycopg2
    from config import settings
    HAS_DB = True
except ImportError:
    HAS_DB = False
    class MockSettings:
        class db:
            psycopg2_params = {}
    settings = MockSettings()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'chisinau-routing-secret-2024')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Simulated trolleybus data (will be populated from DB or simulator)
trolleybuses = {}
simulation_running = False
simulation_thread = None

# Chișinău trolleybus routes with realistic paths
ROUTES = {
    "1": {"name": "Botanica - Center", "color": "#e74c3c"},
    "2": {"name": "Ciocana - Buiucani", "color": "#3498db"},
    "3": {"name": "Riscani - Botanica", "color": "#2ecc71"},
    "5": {"name": "Telecentru - Center", "color": "#9b59b6"},
    "8": {"name": "Airport - Center", "color": "#f39c12"},
    "10": {"name": "Sculeni - Center", "color": "#1abc9c"},
    "22": {"name": "Buiucani - Botanica", "color": "#e91e63"},
    "24": {"name": "Ciocana - Riscani", "color": "#00bcd4"},
}

# Real trolleybus routes following actual streets in Chisinau
# Format: (lat, lng) - coordinates along the route
ROUTE_PATHS = {
    # Route 1: Botanica (str. Dacia) - Center (Stefan cel Mare)
    "1": [
        (46.9847, 28.8576), (46.9889, 28.8543), (46.9931, 28.8512),
        (46.9973, 28.8479), (47.0015, 28.8446), (47.0057, 28.8413),
        (47.0099, 28.8380), (47.0141, 28.8347), (47.0183, 28.8314),
        (47.0225, 28.8281), (47.0245, 28.8322)  # Stefan cel Mare
    ],
    # Route 2: Ciocana - Buiucani via center
    "2": [
        (47.0367, 28.8978), (47.0345, 28.8923), (47.0323, 28.8867),
        (47.0301, 28.8812), (47.0279, 28.8756), (47.0257, 28.8701),
        (47.0245, 28.8322),  # Center
        (47.0267, 28.8267), (47.0289, 28.8212), (47.0311, 28.8156),
        (47.0378, 28.8189), (47.0445, 28.8223)  # Buiucani
    ],
    # Route 3: Riscani - Botanica
    "3": [
        (47.0489, 28.8278), (47.0456, 28.8312), (47.0423, 28.8345),
        (47.0390, 28.8378), (47.0357, 28.8412), (47.0324, 28.8445),
        (47.0245, 28.8322),  # Center
        (47.0183, 28.8389), (47.0121, 28.8456), (47.0059, 28.8523),
        (46.9997, 28.8590), (46.9935, 28.8557)  # Botanica
    ],
    # Route 5: Telecentru - Center
    "5": [
        (47.0012, 28.8189), (47.0034, 28.8223), (47.0056, 28.8256),
        (47.0078, 28.8289), (47.0100, 28.8322), (47.0122, 28.8356),
        (47.0144, 28.8389), (47.0166, 28.8322), (47.0188, 28.8356),
        (47.0210, 28.8322), (47.0245, 28.8322)  # Center
    ],
    # Route 8: Airport - Center (via Dacia)
    "8": [
        (46.9277, 28.9312), (46.9345, 28.9234), (46.9412, 28.9156),
        (46.9479, 28.9078), (46.9546, 28.9001), (46.9613, 28.8923),
        (46.9680, 28.8845), (46.9747, 28.8767), (46.9814, 28.8689),
        (46.9881, 28.8612), (46.9948, 28.8534), (47.0015, 28.8456),
        (47.0082, 28.8378), (47.0149, 28.8345), (47.0245, 28.8322)
    ],
    # Route 10: Sculeni - Center
    "10": [
        (47.0623, 28.8089), (47.0578, 28.8134), (47.0534, 28.8178),
        (47.0489, 28.8223), (47.0445, 28.8267), (47.0401, 28.8312),
        (47.0356, 28.8356), (47.0312, 28.8322), (47.0267, 28.8322),
        (47.0245, 28.8322)  # Center
    ],
    # Route 22: Buiucani - Botanica
    "22": [
        (47.0512, 28.8189), (47.0467, 28.8234), (47.0423, 28.8278),
        (47.0378, 28.8322), (47.0334, 28.8367), (47.0289, 28.8412),
        (47.0245, 28.8322),  # Center
        (47.0200, 28.8389), (47.0156, 28.8456), (47.0111, 28.8523),
        (47.0067, 28.8567), (47.0022, 28.8534), (46.9978, 28.8501)
    ],
    # Route 24: Ciocana - Riscani
    "24": [
        (47.0345, 28.8956), (47.0323, 28.8889), (47.0301, 28.8823),
        (47.0279, 28.8756), (47.0257, 28.8689), (47.0245, 28.8322),  # Center
        (47.0267, 28.8389), (47.0289, 28.8345), (47.0312, 28.8301),
        (47.0356, 28.8278), (47.0401, 28.8256), (47.0445, 28.8278)
    ],
}


def get_db_connection():
    """Get database connection."""
    if not HAS_DB:
        return None
    try:
        import psycopg2
        conn = psycopg2.connect(**settings.db.psycopg2_params, connect_timeout=5)
        conn.set_session(autocommit=True)
        return conn
    except:
        return None


def init_trolleybuses():
    """Initialize simulated trolleybuses."""
    global trolleybuses
    trolleybuses = {}
    
    bus_id = 1
    for route_id, route_info in ROUTES.items():
        # Create 2-4 buses per route
        num_buses = random.randint(2, 4)
        path = ROUTE_PATHS.get(route_id, [])
        
        for i in range(num_buses):
            tid = f"TB{bus_id:03d}"
            start_idx = random.randint(0, max(0, len(path) - 2))
            
            trolleybuses[tid] = {
                "id": tid,
                "route": route_id,
                "routeName": route_info["name"],
                "color": route_info["color"],
                "lat": path[start_idx][0] if path else 47.0245,
                "lng": path[start_idx][1] if path else 28.8323,
                "speed": random.uniform(15, 35),
                "bearing": random.uniform(0, 360),
                "pathIndex": start_idx,
                "pathProgress": random.random(),
                "direction": random.choice([1, -1]),
                "passengers": random.randint(5, 45),
                "lastUpdate": datetime.now(timezone.utc).isoformat()
            }
            bus_id += 1
    
    return len(trolleybuses)


def update_trolleybus_positions():
    """Update all trolleybus positions (simulation)."""
    global trolleybuses
    
    for tid, bus in trolleybuses.items():
        route_id = bus["route"]
        path = ROUTE_PATHS.get(route_id, [])
        
        if not path:
            continue
        
        # Update speed with some variation
        hour = datetime.now().hour
        # Rush hour factor
        if 7 <= hour <= 9 or 17 <= hour <= 19:
            speed_factor = random.uniform(0.4, 0.7)
        elif hour >= 22 or hour <= 6:
            speed_factor = random.uniform(0.8, 1.0)
        else:
            speed_factor = random.uniform(0.6, 0.9)
        
        bus["speed"] = random.uniform(15, 40) * speed_factor
        
        # Occasionally stop (bus stops, traffic lights)
        if random.random() < 0.08:
            bus["speed"] = 0
        
        # Update position along path
        progress_delta = (bus["speed"] * 1000 / 3600) * 2 / 500  # 2 seconds, 500m between points
        bus["pathProgress"] += progress_delta
        
        if bus["pathProgress"] >= 1.0:
            bus["pathProgress"] = 0
            bus["pathIndex"] += bus["direction"]
            
            # Reverse at ends
            if bus["pathIndex"] >= len(path) - 1:
                bus["direction"] = -1
                bus["pathIndex"] = len(path) - 1
            elif bus["pathIndex"] <= 0:
                bus["direction"] = 1
                bus["pathIndex"] = 0
        
        # Interpolate position
        idx = bus["pathIndex"]
        next_idx = min(max(idx + bus["direction"], 0), len(path) - 1)
        
        lat1, lon1 = path[idx]
        lat2, lon2 = path[next_idx]
        
        bus["lat"] = lat1 + (lat2 - lat1) * bus["pathProgress"]
        bus["lng"] = lon1 + (lon2 - lon1) * bus["pathProgress"]
        
        # Calculate bearing
        if lat2 != lat1 or lon2 != lon1:
            bus["bearing"] = math.degrees(math.atan2(lon2 - lon1, lat2 - lat1))
            if bus["bearing"] < 0:
                bus["bearing"] += 360
        
        # Update passengers randomly
        if random.random() < 0.1:
            bus["passengers"] = max(0, min(60, bus["passengers"] + random.randint(-5, 5)))
        
        bus["lastUpdate"] = datetime.now(timezone.utc).isoformat()


def simulation_loop():
    """Background thread for trolleybus simulation."""
    global simulation_running
    
    while simulation_running:
        update_trolleybus_positions()
        
        # Emit updates via WebSocket
        socketio.emit('trolleybus_update', {
            "trolleybuses": list(trolleybuses.values()),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        time.sleep(2)  # Update every 2 seconds


# ============== ROUTES ==============

@app.route('/')
def index():
    """Main map page."""
    return render_template('index.html')


@app.route('/api/trolleybuses')
def get_trolleybuses():
    """Get all trolleybus positions."""
    return jsonify({
        "success": True,
        "data": list(trolleybuses.values()),
        "count": len(trolleybuses),
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


@app.route('/api/routes')
def get_routes():
    """Get all routes with paths."""
    routes_data = []
    for route_id, info in ROUTES.items():
        path = ROUTE_PATHS.get(route_id, [])
        # Count vehicles on this route
        vehicle_count = sum(1 for t in trolleybuses.values() if str(t.get('route')) == route_id)
        routes_data.append({
            "id": int(route_id),
            "name": info["name"],
            "color": info["color"],
            "vehicleCount": vehicle_count,
            "path": [[p[1], p[0]] for p in path]  # [lng, lat] for GeoJSON
        })
    return jsonify({"success": True, "data": routes_data})


@app.route('/api/stats')
def get_stats():
    """Get system statistics."""
    conn = get_db_connection()
    road_network = {
        "nodes": 0,
        "edges": 0,
        "totalLengthKm": 0
    }
    
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM nodes")
            road_network["nodes"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM edges")
            road_network["edges"] = cur.fetchone()[0]
            cur.execute("SELECT ROUND(SUM(length_m)::numeric/1000, 1) FROM edges")
            road_network["totalLengthKm"] = float(cur.fetchone()[0] or 0)
            conn.close()
        except:
            pass
    
    stats = {
        "totalVehicles": len(trolleybuses),
        "activeVehicles": len(trolleybuses),
        "totalRoutes": len(ROUTES),
        "roadNetwork": road_network
    }
    
    return jsonify({"success": True, "data": stats})


@app.route('/api/traffic')
def get_traffic():
    """Get traffic data - from TomTom or simulated."""
    import requests
    
    # TomTom API key from environment variable (NEVER hardcode!)
    TOMTOM_KEY = os.environ.get('TOMTOM_API_KEY', '')
    
    # Key intersections in Chisinau - positioned on actual roads
    traffic_points = [
        {"name": "Stefan cel Mare / Puskin", "lat": 47.0227, "lng": 28.8305},
        {"name": "Stefan cel Mare / Ismail", "lat": 47.0262, "lng": 28.8352},
        {"name": "Dacia / Decebal", "lat": 47.0145, "lng": 28.8445},
        {"name": "Bd. Moscova / Ciocana", "lat": 47.0312, "lng": 28.8856},
        {"name": "Bd. Dacia / Botanica", "lat": 46.9923, "lng": 28.8512},
        {"name": "Bd. Renaşterii / Rîscani", "lat": 47.0445, "lng": 28.8278},
        {"name": "Str. Calea Ieşilor", "lat": 47.0489, "lng": 28.8156},
        {"name": "Bd. Ştefan cel Mare / Gara", "lat": 47.0156, "lng": 28.8278},
    ]
    
    traffic_data = []
    
    for point in traffic_points:
        try:
            # Try TomTom Flow API (only if key is set)
            if TOMTOM_KEY:
                url = f"https://api.tomtom.com/traffic/services/4/flowSegmentData/relative0/10/json"
                params = {
                    "key": TOMTOM_KEY,
                    "point": f"{point['lat']},{point['lng']}"
                }
                resp = requests.get(url, params=params, timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    flow = data.get("flowSegmentData", {})
                    speed = flow.get("currentSpeed", 50)
                    freeflow = flow.get("freeFlowSpeed", 50)
                    confidence = flow.get("confidence", 1)
                else:
                    raise Exception("API failed")
            else:
                raise Exception("No API key")
        except:
            # Simulate traffic if API not available
            hour = datetime.now().hour
            if 7 <= hour <= 9 or 17 <= hour <= 19:
                speed = random.randint(15, 35)  # Rush hour
            else:
                speed = random.randint(35, 60)  # Normal
            freeflow = 50
            confidence = 0.8
        
        traffic_data.append({
            "name": point["name"],
            "lat": point["lat"],
            "lng": point["lng"],
            "speed": speed,
            "freeFlowSpeed": freeflow,
            "confidence": confidence
        })
    
    return jsonify({"success": True, "data": traffic_data})


@app.route('/api/route/<start_lat>/<start_lng>/<end_lat>/<end_lng>')
def calculate_route(start_lat, start_lng, end_lat, end_lng):
    """Calculate route between two points using OSRM with different transport modes."""
    import requests
    
    try:
        start_lat = float(start_lat)
        start_lng = float(start_lng)
        end_lat = float(end_lat)
        end_lng = float(end_lng)
        
        # Get transport mode from query params (driving, foot, cycling, transit)
        mode = request.args.get('mode', 'driving')
        
        # Map modes to OSRM profiles
        osrm_profiles = {
            'driving': 'driving',
            'car': 'driving',
            'foot': 'foot',
            'walk': 'foot',
            'cycling': 'bike',
            'bike': 'bike',
            'transit': 'driving'  # OSRM doesn't support transit, use driving as fallback
        }
        profile = osrm_profiles.get(mode, 'driving')
        
        # Use OSRM public demo server
        osrm_url = f"https://router.project-osrm.org/route/v1/{profile}/{start_lng},{start_lat};{end_lng},{end_lat}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "true",
            "annotations": "true"
        }
        
        response = requests.get(osrm_url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == "Ok" and data.get("routes"):
                route = data["routes"][0]
                geometry = route["geometry"]["coordinates"]
                
                # Adjust duration based on mode
                duration = route["duration"] / 60  # minutes
                if mode in ['foot', 'walk']:
                    # Walking is about 5 km/h average
                    duration = (route["distance"] / 1000) / 5 * 60
                elif mode in ['cycling', 'bike']:
                    # Cycling is about 15 km/h average
                    duration = (route["distance"] / 1000) / 15 * 60
                
                steps = []
                for leg in route.get("legs", []):
                    for step in leg.get("steps", []):
                        steps.append({
                            "instruction": step.get("maneuver", {}).get("type", "continue"),
                            "name": step.get("name", ""),
                            "distance": step.get("distance", 0),
                            "duration": step.get("duration", 0)
                        })
                
                return jsonify({
                    "success": True,
                    "mode": mode,
                    "route": {
                        "distance": route["distance"] / 1000,
                        "duration": duration,
                        "path": geometry,
                        "steps": steps
                    }
                })
        
        # Fallback
        return jsonify({
            "success": True,
            "route": {
                "distance": 0,
                "duration": 0,
                "path": [[start_lng, start_lat], [end_lng, end_lat]],
                "steps": []
            },
            "warning": "Could not calculate route"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============== GRAPH ALGORITHMS API ==============

@app.route('/api/algorithms/dijkstra', methods=['POST'])
def api_dijkstra():
    """
    Dijkstra's Algorithm - Find shortest path between two points.
    
    POST body: {
        "start": {"lat": 47.0245, "lng": 28.8322},
        "end": {"lat": 47.0367, "lng": 28.8978},
        "nodes": [...],  # optional: custom nodes
        "edges": [...]   # optional: custom edges
    }
    """
    from algorithms import Graph, dijkstra_shortest_path_with_details, build_chisinau_graph
    
    data = request.get_json()
    
    if not data or 'start' not in data or 'end' not in data:
        return jsonify({"success": False, "error": "Missing start or end point"}), 400
    
    try:
        # Use provided graph or default Chișinău graph
        if 'nodes' in data and 'edges' in data:
            graph = build_graph_from_data(data['nodes'], data['edges'])
        else:
            graph = build_chisinau_graph()
        
        # Find nearest nodes to start/end coordinates
        start_node = find_nearest_node(graph, data['start']['lat'], data['start']['lng'])
        end_node = find_nearest_node(graph, data['end']['lat'], data['end']['lng'])
        
        if start_node is None or end_node is None:
            return jsonify({"success": False, "error": "Could not find nodes near coordinates"}), 400
        
        # Run Dijkstra
        result = dijkstra_shortest_path_with_details(graph, start_node, end_node)
        
        return jsonify({
            "success": result["found"],
            "algorithm": "dijkstra",
            "route": {
                "distance": result["distance_km"],
                "duration": result["duration_minutes"],
                "path": result["coordinates"],
                "steps": result["steps"]
            }
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/algorithms/kruskal', methods=['POST'])
def api_kruskal():
    """
    Kruskal's Algorithm - Find Minimum Spanning Tree.
    
    POST body: {
        "points": [{"lat": 47.0245, "lng": 28.8322}, ...],  # points to connect
    }
    
    Returns MST connecting all provided points with minimum total distance.
    """
    from algorithms import Graph, kruskal_mst, build_chisinau_graph
    
    data = request.get_json()
    
    if not data:
        # If no points provided, return MST of entire graph
        graph = build_chisinau_graph()
        mst_edges, total_weight = kruskal_mst(graph)
        
        return jsonify({
            "success": True,
            "algorithm": "kruskal",
            "mst": {
                "total_distance_km": total_weight / 1000,
                "edges": [
                    {
                        "from": {"lat": graph.nodes[e.u].lat, "lng": graph.nodes[e.u].lng},
                        "to": {"lat": graph.nodes[e.v].lat, "lng": graph.nodes[e.v].lng},
                        "distance": e.weight,
                        "name": e.name
                    }
                    for e in mst_edges
                ]
            }
        })
    
    try:
        graph = build_chisinau_graph()
        
        # Find nearest nodes for each provided point
        point_nodes = []
        for p in data.get('points', []):
            node = find_nearest_node(graph, p['lat'], p['lng'])
            if node is not None:
                point_nodes.append(node)
        
        if len(point_nodes) < 2:
            return jsonify({"success": False, "error": "Need at least 2 valid points"}), 400
        
        # Build subgraph and run Kruskal
        from algorithms import kruskal_mst_path
        mst_edges, total_weight = kruskal_mst_path(graph, point_nodes)
        
        return jsonify({
            "success": True,
            "algorithm": "kruskal",
            "mst": {
                "total_distance_km": total_weight / 1000,
                "edges": [
                    {
                        "from": e.u,
                        "to": e.v,
                        "distance": e.weight,
                        "name": e.name
                    }
                    for e in mst_edges
                ]
            }
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/algorithms/astar', methods=['POST'])
def api_astar():
    """
    A* Algorithm - Shortest path with heuristic (faster than Dijkstra).
    """
    from algorithms import Graph, astar_shortest_path, build_chisinau_graph
    
    data = request.get_json()
    
    if not data or 'start' not in data or 'end' not in data:
        return jsonify({"success": False, "error": "Missing start or end point"}), 400
    
    try:
        graph = build_chisinau_graph()
        
        start_node = find_nearest_node(graph, data['start']['lat'], data['start']['lng'])
        end_node = find_nearest_node(graph, data['end']['lat'], data['end']['lng'])
        
        if start_node is None or end_node is None:
            return jsonify({"success": False, "error": "Could not find nodes"}), 400
        
        path, distance = astar_shortest_path(graph, start_node, end_node)
        
        if not path:
            return jsonify({"success": False, "error": "No path found"}), 404
        
        coordinates = [[graph.nodes[n].lng, graph.nodes[n].lat] for n in path]
        
        return jsonify({
            "success": True,
            "algorithm": "astar",
            "route": {
                "distance": distance / 1000,
                "duration": (distance / 1000) / 40 * 60,  # 40 km/h average
                "path": coordinates
            }
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def find_nearest_node(graph, lat: float, lng: float) -> int:
    """Find the nearest graph node to given coordinates."""
    min_dist = float('inf')
    nearest = None
    
    for node_id, node in graph.nodes.items():
        dist = graph.haversine_distance(lat, lng, node.lat, node.lng)
        if dist < min_dist:
            min_dist = dist
            nearest = node_id
    
    return nearest


def build_graph_from_data(nodes, edges):
    """Build graph from provided node/edge data."""
    from algorithms import Graph
    
    graph = Graph()
    for n in nodes:
        graph.add_node(n['id'], n['lat'], n['lng'], n.get('name', ''))
    for e in edges:
        graph.add_edge(e['from'], e['to'], e['weight'], e.get('name', ''))
    return graph


@app.route('/api/geocode/reverse/<lat>/<lng>')
def reverse_geocode(lat, lng):
    """Convert coordinates to address using Nominatim."""
    import requests
    
    try:
        lat = float(lat)
        lng = float(lng)
        
        # Use Nominatim for reverse geocoding
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat,
            "lon": lng,
            "format": "json",
            "addressdetails": 1,
            "zoom": 18
        }
        headers = {
            "User-Agent": "ChisinauRouting/1.0"
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            address = data.get("address", {})
            
            return jsonify({
                "success": True,
                "address": {
                    "full": data.get("display_name", ""),
                    "street": address.get("road", address.get("pedestrian", "")),
                    "house_number": address.get("house_number", ""),
                    "city": address.get("city", address.get("town", address.get("village", ""))),
                    "district": address.get("suburb", address.get("neighbourhood", "")),
                    "country": address.get("country", "")
                },
                "lat": lat,
                "lng": lng
            })
        
        return jsonify({
            "success": False,
            "error": "Geocoding failed"
        }), 500
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/geocode/search')
def search_address():
    """Search for a location by address or place name."""
    import requests
    
    query = request.args.get('q', '')
    if not query:
        return jsonify({"success": False, "error": "No query provided"}), 400
    
    try:
        # Use Nominatim for geocoding, biased towards Chisinau/Moldova
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "addressdetails": 1,
            "limit": 10,
            "viewbox": "28.7,47.1,29.0,46.9",  # Chisinau bounding box
            "bounded": 0  # Allow results outside viewbox but prefer inside
        }
        headers = {
            "User-Agent": "ChisinauRouting/1.0"
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            results = response.json()
            
            locations = []
            for r in results:
                address = r.get("address", {})
                locations.append({
                    "name": r.get("display_name", ""),
                    "lat": float(r.get("lat", 0)),
                    "lng": float(r.get("lon", 0)),
                    "type": r.get("type", ""),
                    "street": address.get("road", ""),
                    "city": address.get("city", address.get("town", address.get("village", ""))),
                    "country": address.get("country", "")
                })
            
            return jsonify({
                "success": True,
                "results": locations
            })
        
        return jsonify({"success": False, "error": "Search failed"}), 500
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============== ALGORITHM VISUALIZATION API ==============

# Cache for database graph (don't reload every request)
_db_graph_cache = {}


def load_graph_from_db(max_edges=500):
    """Load graph from PostgreSQL database."""
    global _db_graph_cache
    
    cache_key = f"db_{max_edges}"
    if cache_key in _db_graph_cache:
        return _db_graph_cache[cache_key]
    
    if not HAS_DB:
        return None
    
    from algorithms import Graph
    
    try:
        conn = psycopg2.connect(**settings.db.psycopg2_params)
        cur = conn.cursor()
        
        # Get nodes with geometry
        cur.execute("""
            SELECT id, ST_Y(geom) as lat, ST_X(geom) as lng 
            FROM nodes 
            LIMIT 5000
        """)
        nodes_data = cur.fetchall()
        
        # Get edges with weights
        cur.execute("""
            SELECT source_node, target_node, length_m, COALESCE(name, highway_type, 'Road')
            FROM edges
            ORDER BY length_m ASC
            LIMIT %s
        """, (max_edges,))
        edges_data = cur.fetchall()
        
        conn.close()
        
        if not nodes_data or not edges_data:
            return None
        
        # Build graph
        graph = Graph()
        
        # Add nodes
        node_ids = set()
        for edge in edges_data:
            node_ids.add(edge[0])
            node_ids.add(edge[1])
        
        for node_id, lat, lng in nodes_data:
            if node_id in node_ids:
                graph.add_node(node_id, lat, lng, f"Node {node_id}")
        
        # Add edges
        for source, target, length, name in edges_data:
            if source in graph.nodes and target in graph.nodes:
                graph.add_edge(source, target, length, name or "Road", bidirectional=True)
        
        _db_graph_cache[cache_key] = graph
        
        return graph
        
    except Exception as e:
        print(f"DB Graph load error: {e}")
        return None


def get_graph(use_db=True, max_edges=500):
    """Get graph - try DB first, fall back to built-in."""
    from algorithms import build_chisinau_graph
    
    if use_db:
        db_graph = load_graph_from_db(max_edges)
        if db_graph and len(db_graph.nodes) > 0:
            return db_graph, "database"
    
    return build_chisinau_graph(), "builtin"


@app.route('/api/algorithms/graph')
def api_get_graph():
    """Get the Chișinău graph nodes and edges for visualization."""
    use_db = request.args.get('source', 'auto') != 'builtin'
    max_edges = min(int(request.args.get('max_edges', 500)), 2000)
    
    graph, source = get_graph(use_db, max_edges)
    
    nodes = []
    for node_id, node in graph.nodes.items():
        nodes.append({
            "id": node_id,
            "lat": node.lat,
            "lng": node.lng,
            "name": node.name
        })
    
    edges = []
    for edge in graph.edges:
        edges.append({
            "from": {
                "id": edge.u,
                "lat": graph.nodes[edge.u].lat,
                "lng": graph.nodes[edge.u].lng
            },
            "to": {
                "id": edge.v,
                "lat": graph.nodes[edge.v].lat,
                "lng": graph.nodes[edge.v].lng
            },
            "weight": edge.weight,
            "name": edge.name
        })
    
    return jsonify({
        "success": True,
        "source": source,
        "nodes": nodes,
        "edges": edges,
        "total_nodes": len(nodes),
        "total_edges": len(edges)
    })


@app.route('/api/algorithms/kruskal/steps', methods=['POST'])
def api_kruskal_steps():
    """Get step-by-step visualization of Kruskal's algorithm."""
    from algorithms import kruskal_mst_steps
    
    data = request.get_json() or {}
    use_db = data.get('source', 'auto') != 'builtin'
    max_edges = min(data.get('max_edges', 200), 500)  # Limit for animation
    
    try:
        graph, source = get_graph(use_db, max_edges)
        
        # If start/end points provided, filter to nearby subgraph
        if 'start' in data and 'end' in data:
            start_node = find_nearest_node(graph, data['start']['lat'], data['start']['lng'])
            end_node = find_nearest_node(graph, data['end']['lat'], data['end']['lng'])
            # For Kruskal we still use full graph but mark start/end
        
        steps = kruskal_mst_steps(graph)
        
        # Get all graph data for visualization
        nodes = [{"id": n.id, "lat": n.lat, "lng": n.lng, "name": n.name} for n in graph.nodes.values()]
        edges = [{"from": {"lat": graph.nodes[e.u].lat, "lng": graph.nodes[e.u].lng},
                  "to": {"lat": graph.nodes[e.v].lat, "lng": graph.nodes[e.v].lng},
                  "weight": e.weight, "name": e.name} for e in graph.edges]
        
        return jsonify({
            "success": True,
            "algorithm": "kruskal",
            "source": source,
            "nodes": nodes,
            "edges": edges,
            "steps": steps,
            "total_steps": len(steps)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/algorithms/dijkstra/steps', methods=['POST'])
def api_dijkstra_steps():
    """Get step-by-step visualization of Dijkstra's algorithm."""
    from algorithms import dijkstra_steps
    
    data = request.get_json() or {}
    use_db = data.get('source', 'auto') != 'builtin'
    max_edges = min(data.get('max_edges', 300), 1000)
    
    try:
        graph, source = get_graph(use_db, max_edges)
        
        # Get start and end nodes
        if 'start' in data and 'end' in data:
            start_node = find_nearest_node(graph, data['start']['lat'], data['start']['lng'])
            end_node = find_nearest_node(graph, data['end']['lat'], data['end']['lng'])
        else:
            # Default: first and last node
            node_ids = list(graph.nodes.keys())
            start_node = node_ids[0] if node_ids else None
            end_node = node_ids[-1] if len(node_ids) > 1 else node_ids[0] if node_ids else None
        
        if start_node is None or end_node is None:
            return jsonify({"success": False, "error": "Could not find nodes"}), 400
        
        steps = dijkstra_steps(graph, start_node, end_node)
        
        # Get all graph data for visualization
        nodes = [{"id": n.id, "lat": n.lat, "lng": n.lng, "name": n.name} for n in graph.nodes.values()]
        edges = [{"from": {"lat": graph.nodes[e.u].lat, "lng": graph.nodes[e.u].lng},
                  "to": {"lat": graph.nodes[e.v].lat, "lng": graph.nodes[e.v].lng},
                  "weight": e.weight, "name": e.name} for e in graph.edges]
        
        return jsonify({
            "success": True,
            "algorithm": "dijkstra",
            "source": source,
            "nodes": nodes,
            "edges": edges,
            "steps": steps,
            "total_steps": len(steps),
            "start_node": {"id": start_node, "name": graph.nodes[start_node].name},
            "end_node": {"id": end_node, "name": graph.nodes[end_node].name}
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============== WEBSOCKET ==============

@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection."""
    emit('connected', {
        "message": "Connected to Chișinău Routing Engine",
        "trolleybuses": len(trolleybuses)
    })


@socketio.on('start_simulation')
def handle_start_simulation():
    """Start the trolleybus simulation."""
    global simulation_running, simulation_thread
    
    if not simulation_running:
        init_trolleybuses()
        simulation_running = True
        simulation_thread = threading.Thread(target=simulation_loop, daemon=True)
        simulation_thread.start()
        emit('simulation_started', {"count": len(trolleybuses)})


@socketio.on('stop_simulation')
def handle_stop_simulation():
    """Stop the trolleybus simulation."""
    global simulation_running
    simulation_running = False
    emit('simulation_stopped', {})


# ============== MAIN ==============

if __name__ == '__main__':
    print()
    print("=" * 60)
    print("  CHIȘINĂU ROUTING ENGINE - WEB APPLICATION")
    print("=" * 60)
    print()
    print("  Starting server...")
    print()
    
    # Initialize trolleybuses
    count = init_trolleybuses()
    print(f"  [OK] Initialized {count} simulated trolleybuses")
    
    # Start simulation
    simulation_running = True
    simulation_thread = threading.Thread(target=simulation_loop, daemon=True)
    simulation_thread.start()
    print("  [OK] Simulation started")
    
    print()
    print("  Open in browser: http://localhost:5000")
    print()
    print("=" * 60)
    print()
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
