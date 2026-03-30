/**
 * @file graph.hpp
 * @brief Graph data structures for the Chișinău routing engine
 * 
 * Defines the in-memory graph representation loaded from PostgreSQL.
 * Optimized for A* traversal with support for dynamic edge weights.
 */

#ifndef CHISINAU_GRAPH_HPP
#define CHISINAU_GRAPH_HPP

#include <vector>
#include <unordered_map>
#include <cstdint>
#include <string>
#include <memory>
#include <limits>
#include <cmath>

namespace chisinau {

/**
 * @brief Geographic coordinate (WGS84)
 */
struct Coordinate {
    double latitude;
    double longitude;
    
    Coordinate() : latitude(0), longitude(0) {}
    Coordinate(double lat, double lon) : latitude(lat), longitude(lon) {}
    
    /**
     * @brief Calculate great-circle distance to another coordinate (meters)
     */
    double distanceTo(const Coordinate& other) const {
        constexpr double R = 6371000.0;  // Earth radius in meters
        
        double lat1 = latitude * M_PI / 180.0;
        double lat2 = other.latitude * M_PI / 180.0;
        double deltaLat = (other.latitude - latitude) * M_PI / 180.0;
        double deltaLon = (other.longitude - longitude) * M_PI / 180.0;
        
        double a = std::sin(deltaLat / 2) * std::sin(deltaLat / 2) +
                   std::cos(lat1) * std::cos(lat2) *
                   std::sin(deltaLon / 2) * std::sin(deltaLon / 2);
        double c = 2 * std::atan2(std::sqrt(a), std::sqrt(1 - a));
        
        return R * c;
    }
};

/**
 * @brief Graph node (intersection/waypoint)
 */
struct Node {
    int64_t id;          ///< OSM node ID
    Coordinate coord;     ///< Geographic location
    
    // Adjacency list indices (filled during graph construction)
    uint32_t firstEdge;   ///< Index of first outgoing edge
    uint32_t edgeCount;   ///< Number of outgoing edges
};

/**
 * @brief Graph edge (road segment)
 */
struct Edge {
    int64_t id;           ///< Database edge ID
    int64_t osmWayId;     ///< Original OSM way ID
    
    uint32_t source;      ///< Index of source node
    uint32_t target;      ///< Index of target node
    
    // Static attributes
    double lengthM;       ///< Length in meters
    int16_t maxSpeedKmh;  ///< Speed limit (km/h)
    double baseTimeSec;   ///< Base travel time (seconds)
    
    std::string name;     ///< Street name
    std::string highway;  ///< Highway type (primary, secondary, etc.)
    bool oneway;          ///< Is one-way street
    
    /**
     * @brief Get edge weight for routing (travel time in seconds)
     * 
     * This is the base weight; WeightManager provides time-varying weights.
     */
    double getWeight() const {
        return baseTimeSec;
    }
};

/**
 * @brief Route segment for API responses
 */
struct RouteSegment {
    int64_t edgeId;
    std::string name;
    double lengthM;
    double timeSec;
    std::vector<Coordinate> geometry;
};

/**
 * @brief Complete route result
 */
struct Route {
    bool found;                          ///< Was a route found?
    double totalDistanceM;               ///< Total distance in meters
    double totalTimeSec;                 ///< Total time in seconds
    std::vector<RouteSegment> segments;  ///< Ordered route segments
    std::vector<Coordinate> geometry;    ///< Full route geometry
    
    // Performance metrics
    uint32_t nodesExplored;
    double computeTimeMs;
    
    Route() : found(false), totalDistanceM(0), totalTimeSec(0),
              nodesExplored(0), computeTimeMs(0) {}
};

/**
 * @brief Road graph container
 * 
 * Stores the graph in CSR-like format for cache-efficient traversal.
 * Nodes are stored in a vector, edges in a separate vector sorted by source.
 */
class Graph {
public:
    Graph() = default;
    ~Graph() = default;
    
    // Prevent copying (graph can be large)
    Graph(const Graph&) = delete;
    Graph& operator=(const Graph&) = delete;
    
    // Allow moving
    Graph(Graph&&) = default;
    Graph& operator=(Graph&&) = default;
    
    /**
     * @brief Reserve memory for expected graph size
     */
    void reserve(size_t nodeCount, size_t edgeCount);
    
    /**
     * @brief Add a node to the graph
     * @return Index of the added node
     */
    uint32_t addNode(const Node& node);
    
    /**
     * @brief Add an edge to the graph
     * 
     * Edges should be added after all nodes, then finalize() called.
     */
    void addEdge(const Edge& edge);
    
    /**
     * @brief Finalize graph construction
     * 
     * Sorts edges and builds adjacency structure. Must be called
     * after all nodes/edges are added, before routing.
     */
    void finalize();
    
    /**
     * @brief Find node index by OSM ID
     * @return Node index or -1 if not found
     */
    int32_t findNodeByOsmId(int64_t osmId) const;
    
    /**
     * @brief Find nearest node to a coordinate
     * @return Node index or -1 if none found
     */
    int32_t findNearestNode(const Coordinate& coord, double maxDistanceM = 500.0) const;
    
    /**
     * @brief Get node by index
     */
    const Node& getNode(uint32_t index) const { return nodes_[index]; }
    
    /**
     * @brief Get edge by index
     */
    const Edge& getEdge(uint32_t index) const { return edges_[index]; }
    
    /**
     * @brief Get outgoing edges for a node
     */
    std::pair<const Edge*, const Edge*> getOutgoingEdges(uint32_t nodeIndex) const;
    
    /**
     * @brief Get number of nodes
     */
    size_t nodeCount() const { return nodes_.size(); }
    
    /**
     * @brief Get number of edges
     */
    size_t edgeCount() const { return edges_.size(); }
    
    /**
     * @brief Check if graph is ready for routing
     */
    bool isFinalized() const { return finalized_; }
    
    /**
     * @brief Get graph statistics for logging
     */
    std::string getStats() const;

private:
    std::vector<Node> nodes_;
    std::vector<Edge> edges_;
    
    // OSM ID -> node index mapping
    std::unordered_map<int64_t, uint32_t> osmIdToIndex_;
    
    bool finalized_ = false;
};

}  // namespace chisinau

#endif  // CHISINAU_GRAPH_HPP
