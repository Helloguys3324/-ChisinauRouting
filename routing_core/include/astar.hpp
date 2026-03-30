/**
 * @file astar.hpp
 * @brief A* pathfinding algorithm implementation
 * 
 * Implements A* search with:
 * - Haversine heuristic for geographic graphs
 * - Time-varying edge weights via WeightManager
 * - Early termination optimizations
 */

#ifndef CHISINAU_ASTAR_HPP
#define CHISINAU_ASTAR_HPP

#include "graph.hpp"
#include "weight_manager.hpp"

#include <vector>
#include <queue>
#include <functional>
#include <chrono>
#include <optional>

namespace chisinau {

/**
 * @brief A* search node state
 */
struct AStarNode {
    uint32_t nodeIndex;   ///< Graph node index
    double gScore;        ///< Cost from start
    double fScore;        ///< g + heuristic (priority)
    uint32_t parent;      ///< Parent node index for path reconstruction
    uint32_t parentEdge;  ///< Edge used to reach this node
    
    // For priority queue (min-heap by fScore)
    bool operator>(const AStarNode& other) const {
        return fScore > other.fScore;
    }
};

/**
 * @brief Search parameters
 */
struct SearchParams {
    // Maximum nodes to explore before giving up
    uint32_t maxNodes = 100000;
    
    // Maximum search time (milliseconds)
    uint32_t maxTimeMs = 5000;
    
    // Heuristic weight (1.0 = optimal, >1.0 = faster but suboptimal)
    double heuristicWeight = 1.0;
    
    // Departure time for time-varying weights
    std::chrono::system_clock::time_point departureTime;
    
    SearchParams() : departureTime(std::chrono::system_clock::now()) {}
};

/**
 * @brief A* pathfinding engine
 */
class AStarEngine {
public:
    /**
     * @brief Construct A* engine with graph and optional weight manager
     */
    explicit AStarEngine(const Graph& graph, WeightManager* weightMgr = nullptr);
    
    ~AStarEngine() = default;
    
    /**
     * @brief Find shortest path between two coordinates
     * 
     * @param start Start coordinate (will find nearest node)
     * @param end End coordinate (will find nearest node)
     * @param params Search parameters
     * @return Route result (check route.found)
     */
    Route findRoute(const Coordinate& start, const Coordinate& end,
                    const SearchParams& params = SearchParams());
    
    /**
     * @brief Find shortest path between two node indices
     * 
     * Lower-level API when node indices are already known.
     */
    Route findRoute(uint32_t startNode, uint32_t endNode,
                    const SearchParams& params = SearchParams());
    
    /**
     * @brief Set weight manager for time-varying weights
     */
    void setWeightManager(WeightManager* weightMgr) { weightMgr_ = weightMgr; }
    
private:
    const Graph& graph_;
    WeightManager* weightMgr_;
    
    // Reusable search state (avoids allocations)
    std::vector<double> gScores_;
    std::vector<uint32_t> parents_;
    std::vector<uint32_t> parentEdges_;
    std::vector<bool> visited_;
    
    /**
     * @brief Calculate heuristic (estimated remaining cost)
     * 
     * Uses haversine distance / max_speed as admissible heuristic.
     */
    double heuristic(uint32_t fromNode, uint32_t toNode, double weight) const;
    
    /**
     * @brief Get edge weight considering time-of-day
     */
    double getEdgeWeight(const Edge& edge, double currentTimeSec) const;
    
    /**
     * @brief Reconstruct path from search state
     */
    Route reconstructPath(uint32_t startNode, uint32_t endNode,
                          const SearchParams& params, double computeTimeMs,
                          uint32_t nodesExplored);
    
    /**
     * @brief Reset search state for new query
     */
    void resetState();
};

/**
 * @brief Priority queue type for A*
 */
using AStarPriorityQueue = std::priority_queue<
    AStarNode,
    std::vector<AStarNode>,
    std::greater<AStarNode>
>;

}  // namespace chisinau

#endif  // CHISINAU_ASTAR_HPP
