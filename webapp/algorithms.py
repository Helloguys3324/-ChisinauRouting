"""
Graph Algorithms for Chișinău Routing Engine
- Kruskal's Algorithm: Minimum Spanning Tree (MST)
- Dijkstra's Algorithm: Shortest Path
"""

import heapq
from typing import Dict, List, Tuple, Set, Optional
from dataclasses import dataclass
import math


@dataclass
class Edge:
    """Represents an edge in the graph."""
    u: int  # Source node
    v: int  # Destination node
    weight: float  # Distance/cost
    name: str = ""  # Street name


@dataclass
class Node:
    """Represents a node (intersection) in the graph."""
    id: int
    lat: float
    lng: float
    name: str = ""


class UnionFind:
    """Union-Find (Disjoint Set Union) data structure for Kruskal's algorithm."""
    
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n
    
    def find(self, x: int) -> int:
        """Find with path compression."""
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]
    
    def union(self, x: int, y: int) -> bool:
        """Union by rank. Returns True if merged, False if already in same set."""
        px, py = self.find(x), self.find(y)
        if px == py:
            return False
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1
        return True


class Graph:
    """Graph representation for routing algorithms."""
    
    def __init__(self):
        self.nodes: Dict[int, Node] = {}
        self.edges: List[Edge] = []
        self.adj: Dict[int, List[Tuple[int, float, str]]] = {}  # node -> [(neighbor, weight, name)]
    
    def add_node(self, node_id: int, lat: float, lng: float, name: str = ""):
        """Add a node to the graph."""
        self.nodes[node_id] = Node(node_id, lat, lng, name)
        if node_id not in self.adj:
            self.adj[node_id] = []
    
    def add_edge(self, u: int, v: int, weight: float, name: str = "", bidirectional: bool = True):
        """Add an edge to the graph."""
        self.edges.append(Edge(u, v, weight, name))
        
        if u not in self.adj:
            self.adj[u] = []
        if v not in self.adj:
            self.adj[v] = []
        
        self.adj[u].append((v, weight, name))
        if bidirectional:
            self.adj[v].append((u, weight, name))
    
    def haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in meters using Haversine formula."""
        R = 6371000  # Earth radius in meters
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        
        a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))


# ============== KRUSKAL'S ALGORITHM ==============

def kruskal_mst(graph: Graph) -> Tuple[List[Edge], float]:
    """
    Kruskal's Algorithm - Minimum Spanning Tree
    
    Finds the minimum spanning tree of the graph - the subset of edges
    that connects all vertices with minimum total weight.
    
    Time Complexity: O(E log E) where E is number of edges
    
    Returns:
        Tuple of (list of MST edges, total MST weight)
    """
    if not graph.nodes:
        return [], 0.0
    
    # Create node index mapping
    node_ids = list(graph.nodes.keys())
    node_to_idx = {nid: idx for idx, nid in enumerate(node_ids)}
    n = len(node_ids)
    
    # Sort edges by weight (ascending)
    sorted_edges = sorted(graph.edges, key=lambda e: e.weight)
    
    # Initialize Union-Find
    uf = UnionFind(n)
    
    mst_edges: List[Edge] = []
    total_weight = 0.0
    
    for edge in sorted_edges:
        u_idx = node_to_idx.get(edge.u)
        v_idx = node_to_idx.get(edge.v)
        
        if u_idx is None or v_idx is None:
            continue
        
        # If adding this edge doesn't create a cycle
        if uf.union(u_idx, v_idx):
            mst_edges.append(edge)
            total_weight += edge.weight
            
            # MST has exactly n-1 edges
            if len(mst_edges) == n - 1:
                break
    
    return mst_edges, total_weight


def kruskal_mst_path(graph: Graph, node_ids: List[int]) -> Tuple[List[Edge], float]:
    """
    Find MST connecting only specific nodes (useful for multi-stop routing).
    
    Args:
        graph: The full graph
        node_ids: List of node IDs to connect
    
    Returns:
        Tuple of (MST edges, total weight)
    """
    if len(node_ids) < 2:
        return [], 0.0
    
    # Build subgraph with only required nodes
    subgraph = Graph()
    
    for nid in node_ids:
        if nid in graph.nodes:
            node = graph.nodes[nid]
            subgraph.add_node(nid, node.lat, node.lng, node.name)
    
    # For each pair of required nodes, find shortest path and add as edge
    for i, u in enumerate(node_ids):
        for v in node_ids[i+1:]:
            path, dist = dijkstra_shortest_path(graph, u, v)
            if path:
                subgraph.add_edge(u, v, dist, f"Path {u}->{v}", bidirectional=False)
    
    return kruskal_mst(subgraph)


# ============== DIJKSTRA'S ALGORITHM ==============

def dijkstra_shortest_path(
    graph: Graph, 
    start: int, 
    end: int
) -> Tuple[List[int], float]:
    """
    Dijkstra's Algorithm - Shortest Path
    
    Finds the shortest path between two nodes in the graph.
    
    Time Complexity: O((V + E) log V) with binary heap
    
    Args:
        graph: The graph to search
        start: Starting node ID
        end: Destination node ID
    
    Returns:
        Tuple of (path as list of node IDs, total distance)
    """
    if start not in graph.adj or end not in graph.adj:
        return [], float('inf')
    
    # Distance from start to each node
    dist: Dict[int, float] = {start: 0}
    
    # Previous node in optimal path
    prev: Dict[int, Optional[int]] = {start: None}
    
    # Priority queue: (distance, node_id)
    pq = [(0.0, start)]
    
    # Visited set
    visited: Set[int] = set()
    
    while pq:
        d, u = heapq.heappop(pq)
        
        if u in visited:
            continue
        visited.add(u)
        
        # Found destination
        if u == end:
            break
        
        # Explore neighbors
        for v, weight, _ in graph.adj.get(u, []):
            if v in visited:
                continue
            
            new_dist = d + weight
            
            if v not in dist or new_dist < dist[v]:
                dist[v] = new_dist
                prev[v] = u
                heapq.heappush(pq, (new_dist, v))
    
    # Reconstruct path
    if end not in prev:
        return [], float('inf')
    
    path = []
    current = end
    while current is not None:
        path.append(current)
        current = prev.get(current)
    path.reverse()
    
    return path, dist.get(end, float('inf'))


def dijkstra_shortest_path_with_details(
    graph: Graph, 
    start: int, 
    end: int
) -> Dict:
    """
    Dijkstra's Algorithm with detailed step-by-step result.
    
    Returns:
        Dictionary with path, distance, coordinates, and street names
    """
    path, distance = dijkstra_shortest_path(graph, start, end)
    
    if not path:
        return {
            "found": False,
            "path": [],
            "distance": 0,
            "duration": 0,
            "coordinates": [],
            "steps": []
        }
    
    # Build detailed result
    coordinates = []
    steps = []
    
    for i, node_id in enumerate(path):
        node = graph.nodes.get(node_id)
        if node:
            coordinates.append([node.lng, node.lat])
        
        if i < len(path) - 1:
            next_id = path[i + 1]
            # Find edge info
            for neighbor, weight, name in graph.adj.get(node_id, []):
                if neighbor == next_id:
                    steps.append({
                        "from": node_id,
                        "to": next_id,
                        "distance": weight,
                        "street": name or "Unknown street"
                    })
                    break
    
    # Estimate duration (assuming 40 km/h average speed in city)
    duration_minutes = (distance / 1000) / 40 * 60
    
    return {
        "found": True,
        "path": path,
        "distance": distance,
        "distance_km": distance / 1000,
        "duration_minutes": duration_minutes,
        "coordinates": coordinates,
        "steps": steps
    }


# ============== A* ALGORITHM (Bonus) ==============

def astar_shortest_path(
    graph: Graph, 
    start: int, 
    end: int
) -> Tuple[List[int], float]:
    """
    A* Algorithm - Shortest Path with heuristic
    
    Uses haversine distance as heuristic for faster pathfinding.
    
    Time Complexity: O((V + E) log V) but typically faster than Dijkstra
    
    Returns:
        Tuple of (path as list of node IDs, total distance)
    """
    if start not in graph.nodes or end not in graph.nodes:
        return [], float('inf')
    
    end_node = graph.nodes[end]
    
    def heuristic(node_id: int) -> float:
        """Haversine distance to end point."""
        node = graph.nodes.get(node_id)
        if not node:
            return 0
        return graph.haversine_distance(node.lat, node.lng, end_node.lat, end_node.lng)
    
    # g_score: actual distance from start
    g_score: Dict[int, float] = {start: 0}
    
    # f_score: g_score + heuristic
    f_score: Dict[int, float] = {start: heuristic(start)}
    
    # Previous node in optimal path
    prev: Dict[int, Optional[int]] = {start: None}
    
    # Priority queue: (f_score, node_id)
    pq = [(f_score[start], start)]
    
    # Nodes in the open set
    open_set: Set[int] = {start}
    
    while pq:
        _, current = heapq.heappop(pq)
        
        if current not in open_set:
            continue
        
        if current == end:
            # Reconstruct path
            path = []
            while current is not None:
                path.append(current)
                current = prev.get(current)
            path.reverse()
            return path, g_score[end]
        
        open_set.remove(current)
        
        for neighbor, weight, _ in graph.adj.get(current, []):
            tentative_g = g_score[current] + weight
            
            if neighbor not in g_score or tentative_g < g_score[neighbor]:
                prev[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score[neighbor] = tentative_g + heuristic(neighbor)
                
                if neighbor not in open_set:
                    open_set.add(neighbor)
                    heapq.heappush(pq, (f_score[neighbor], neighbor))
    
    return [], float('inf')


# ============== UTILITY FUNCTIONS ==============

def build_graph_from_edges(
    nodes: List[Dict], 
    edges: List[Dict]
) -> Graph:
    """
    Build a Graph from node and edge data.
    
    Args:
        nodes: List of {"id": int, "lat": float, "lng": float, "name": str}
        edges: List of {"from": int, "to": int, "weight": float, "name": str}
    
    Returns:
        Constructed Graph object
    """
    graph = Graph()
    
    for node in nodes:
        graph.add_node(
            node_id=node["id"],
            lat=node["lat"],
            lng=node["lng"],
            name=node.get("name", "")
        )
    
    for edge in edges:
        graph.add_edge(
            u=edge["from"],
            v=edge["to"],
            weight=edge["weight"],
            name=edge.get("name", ""),
            bidirectional=edge.get("bidirectional", True)
        )
    
    return graph


def build_chisinau_graph() -> Graph:
    """
    Build a graph of Chișinău road network.
    Contains major intersections and roads.
    """
    graph = Graph()
    
    # Major intersections in Chișinău
    # Format: (id, lat, lng, name)
    intersections = [
        # Center
        (1, 47.0245, 28.8322, "Piața Marii Adunări Naționale"),
        (2, 47.0227, 28.8305, "Ștefan cel Mare / Pușkin"),
        (3, 47.0262, 28.8352, "Ștefan cel Mare / Ismail"),
        (4, 47.0289, 28.8260, "Ștefan cel Mare / Columna"),
        (5, 47.0178, 28.8428, "Ștefan cel Mare / Banulescu-Bodoni"),
        (6, 47.0156, 28.8278, "Gara Centrală"),
        
        # Buiucani
        (10, 47.0312, 28.8189, "Buiucani / Calea Ieșilor"),
        (11, 47.0378, 28.8156, "Buiucani / Alba Iulia"),
        (12, 47.0445, 28.8223, "Buiucani / Petru Movilă"),
        (13, 47.0489, 28.8278, "Sculeni"),
        
        # Rîșcani  
        (20, 47.0423, 28.8345, "Rîșcani / Moscova"),
        (21, 47.0456, 28.8412, "Rîșcani / Calea Orheiului"),
        (22, 47.0512, 28.8367, "Poșta Veche"),
        
        # Ciocana
        (30, 47.0367, 28.8978, "Ciocana / Mircea cel Bătrân"),
        (31, 47.0345, 28.8856, "Ciocana / Meșterul Manole"),
        (32, 47.0301, 28.8812, "Ciocana / Alecu Russo"),
        (33, 47.0279, 28.8756, "Ciocana Sud"),
        
        # Botanica
        (40, 47.0145, 28.8445, "Botanica / Dacia"),
        (41, 46.9997, 28.8590, "Botanica / Cuza Vodă"),
        (42, 46.9923, 28.8512, "Aeroport / Dacia"),
        (43, 46.9847, 28.8576, "Botanica Sud"),
        
        # Telecentru
        (50, 47.0012, 28.8189, "Telecentru / Grenoble"),
        (51, 47.0056, 28.8256, "Telecentru / Tighina"),
        (52, 47.0100, 28.8322, "Telecentru / Ismail"),
        
        # Center extra
        (60, 47.0200, 28.8389, "Piața Centrală"),
        (61, 47.0183, 28.8356, "31 August / Ismail"),
    ]
    
    for node_id, lat, lng, name in intersections:
        graph.add_node(node_id, lat, lng, name)
    
    # Roads with approximate distances in meters
    # Format: (from, to, distance, street_name)
    roads = [
        # Ștefan cel Mare (main boulevard)
        (1, 2, 250, "Bd. Ștefan cel Mare"),
        (1, 3, 400, "Bd. Ștefan cel Mare"),
        (3, 4, 350, "Bd. Ștefan cel Mare"),
        (4, 10, 450, "Bd. Ștefan cel Mare"),
        (10, 11, 550, "Bd. Ștefan cel Mare"),
        (1, 5, 500, "Bd. Ștefan cel Mare"),
        (5, 6, 600, "Bd. Ștefan cel Mare"),
        
        # Buiucani connections
        (11, 12, 400, "Str. Alba Iulia"),
        (12, 13, 350, "Calea Ieșilor"),
        (10, 20, 800, "Bd. Moscova"),
        (12, 20, 600, "Str. Petru Movilă"),
        
        # Rîșcani connections
        (20, 21, 450, "Calea Orheiului"),
        (21, 22, 400, "Str. Petricani"),
        (13, 22, 700, "Bd. Renașterii"),
        
        # Ciocana connections
        (3, 33, 1800, "Bd. Mircea cel Bătrân"),
        (33, 32, 350, "Str. Alecu Russo"),
        (32, 31, 400, "Str. Meșterul Manole"),
        (31, 30, 450, "Bd. Mircea cel Bătrân"),
        (21, 30, 2500, "Bd. Moscova"),
        
        # Botanica connections
        (5, 40, 600, "Str. Dacia"),
        (40, 41, 1200, "Bd. Dacia"),
        (41, 42, 800, "Bd. Dacia"),
        (42, 43, 600, "Str. Grenoble"),
        (40, 60, 450, "Str. Tighina"),
        
        # Telecentru connections
        (6, 50, 800, "Str. Calea Basarabiei"),
        (50, 51, 400, "Str. Grenoble"),
        (51, 52, 350, "Str. Tighina"),
        (52, 61, 300, "Str. Ismail"),
        (52, 40, 600, "Bd. Dacia"),
        
        # Center connections
        (60, 61, 300, "Str. 31 August"),
        (61, 5, 350, "Str. 31 August"),
        (60, 3, 450, "Bd. Grigore Vieru"),
        (2, 61, 400, "Str. Pușkin"),
        
        # Cross connections
        (4, 20, 600, "Bd. Renașterii"),
        (6, 51, 500, "Str. Tighina"),
    ]
    
    for u, v, weight, name in roads:
        graph.add_edge(u, v, weight, name)
    
    return graph


# ============== EXAMPLE USAGE ==============

if __name__ == "__main__":
    # Example: Small Chișinău road network
    graph = Graph()
    
    # Add some intersections in Chișinău
    intersections = [
        (1, 47.0245, 28.8322, "Piața Marii Adunări Naționale"),
        (2, 47.0227, 28.8305, "Ștefan cel Mare / Pușkin"),
        (3, 47.0262, 28.8352, "Ștefan cel Mare / Ismail"),
        (4, 47.0289, 28.8260, "Bd. Ștefan cel Mare"),
        (5, 47.0312, 28.8189, "Buiucani"),
        (6, 47.0145, 28.8445, "Botanica"),
        (7, 47.0367, 28.8978, "Ciocana"),
    ]
    
    for node_id, lat, lng, name in intersections:
        graph.add_node(node_id, lat, lng, name)
    
    # Add roads (edges) with approximate distances in meters
    roads = [
        (1, 2, 250, "Bd. Ștefan cel Mare"),
        (1, 3, 400, "Bd. Ștefan cel Mare"),
        (2, 3, 350, "Str. Pușkin"),
        (3, 4, 450, "Bd. Ștefan cel Mare"),
        (4, 5, 600, "Bd. Ștefan cel Mare"),
        (1, 6, 1200, "Str. Dacia"),
        (3, 7, 2500, "Bd. Mircea cel Bătrân"),
        (5, 7, 3000, "Bd. Moscova"),
    ]
    
    for u, v, weight, name in roads:
        graph.add_edge(u, v, weight, name)
    
    print("=" * 60)
    print("KRUSKAL'S ALGORITHM - Minimum Spanning Tree")
    print("=" * 60)
    
    mst_edges, mst_weight = kruskal_mst(graph)
    
    print(f"\nMST Total Weight: {mst_weight:.0f} meters")
    print(f"MST Edges ({len(mst_edges)}):")
    for edge in mst_edges:
        node_u = graph.nodes[edge.u]
        node_v = graph.nodes[edge.v]
        print(f"  {node_u.name} <-> {node_v.name}: {edge.weight:.0f}m ({edge.name})")
    
    print("\n" + "=" * 60)
    print("DIJKSTRA'S ALGORITHM - Shortest Path")
    print("=" * 60)
    
    # Find shortest path from Piața MAN to Ciocana
    start_id, end_id = 1, 7
    result = dijkstra_shortest_path_with_details(graph, start_id, end_id)
    
    if result["found"]:
        print(f"\nPath from {graph.nodes[start_id].name} to {graph.nodes[end_id].name}:")
        print(f"  Distance: {result['distance_km']:.2f} km")
        print(f"  Duration: {result['duration_minutes']:.1f} minutes")
        print(f"\nRoute:")
        for step in result["steps"]:
            print(f"  → {step['street']}: {step['distance']:.0f}m")
    else:
        print("No path found!")
    
    print("\n" + "=" * 60)
    print("A* ALGORITHM - Shortest Path with Heuristic")
    print("=" * 60)
    
    path, dist = astar_shortest_path(graph, start_id, end_id)
    if path:
        path_names = [graph.nodes[n].name for n in path]
        print(f"\nA* Path: {' → '.join(path_names)}")
        print(f"Distance: {dist:.0f} meters")
