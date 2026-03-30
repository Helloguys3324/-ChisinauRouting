/**
 * @file astar.cpp
 * @brief A* pathfinding implementation
 */

#include "astar.hpp"
#include <algorithm>
#include <chrono>
#include <limits>
#include <cmath>

namespace chisinau {

// Assumed maximum speed for heuristic (km/h)
constexpr double MAX_SPEED_KMH = 90.0;
constexpr double MAX_SPEED_MS = MAX_SPEED_KMH / 3.6;

AStarEngine::AStarEngine(const Graph& graph, WeightManager* weightMgr)
    : graph_(graph), weightMgr_(weightMgr) {
}

Route AStarEngine::findRoute(const Coordinate& start, const Coordinate& end,
                              const SearchParams& params) {
    // Find nearest nodes to start and end coordinates
    int32_t startNode = graph_.findNearestNode(start, 500.0);
    int32_t endNode = graph_.findNearestNode(end, 500.0);
    
    if (startNode < 0 || endNode < 0) {
        Route result;
        result.found = false;
        return result;
    }
    
    return findRoute(static_cast<uint32_t>(startNode),
                     static_cast<uint32_t>(endNode), params);
}

Route AStarEngine::findRoute(uint32_t startNode, uint32_t endNode,
                              const SearchParams& params) {
    auto startTime = std::chrono::high_resolution_clock::now();
    
    // Handle trivial case
    if (startNode == endNode) {
        Route result;
        result.found = true;
        result.totalDistanceM = 0;
        result.totalTimeSec = 0;
        result.nodesExplored = 1;
        result.geometry.push_back(graph_.getNode(startNode).coord);
        return result;
    }
    
    // Reset search state
    resetState();
    
    // Initialize data structures
    size_t nodeCount = graph_.nodeCount();
    gScores_.assign(nodeCount, std::numeric_limits<double>::infinity());
    parents_.assign(nodeCount, UINT32_MAX);
    parentEdges_.assign(nodeCount, UINT32_MAX);
    visited_.assign(nodeCount, false);
    
    // Priority queue
    AStarPriorityQueue openSet;
    
    // Start node
    gScores_[startNode] = 0;
    double h = heuristic(startNode, endNode, params.heuristicWeight);
    openSet.push({startNode, 0, h, UINT32_MAX, UINT32_MAX});
    
    uint32_t nodesExplored = 0;
    const Coordinate& endCoord = graph_.getNode(endNode).coord;
    
    // Departure time for weight calculation
    double departureTimeSec = 0;
    {
        auto epoch = params.departureTime.time_since_epoch();
        departureTimeSec = std::chrono::duration<double>(epoch).count();
    }
    
    while (!openSet.empty()) {
        // Check termination conditions
        nodesExplored++;
        if (nodesExplored >= params.maxNodes) {
            break;
        }
        
        auto elapsed = std::chrono::high_resolution_clock::now() - startTime;
        if (std::chrono::duration_cast<std::chrono::milliseconds>(elapsed).count() 
            >= params.maxTimeMs) {
            break;
        }
        
        // Get best node
        AStarNode current = openSet.top();
        openSet.pop();
        
        // Skip if already visited with better score
        if (visited_[current.nodeIndex]) {
            continue;
        }
        visited_[current.nodeIndex] = true;
        
        // Check if we reached the goal
        if (current.nodeIndex == endNode) {
            auto endTime = std::chrono::high_resolution_clock::now();
            double computeTimeMs = std::chrono::duration<double, std::milli>(
                endTime - startTime).count();
            
            return reconstructPath(startNode, endNode, params,
                                   computeTimeMs, nodesExplored);
        }
        
        // Explore neighbors
        auto [edgeBegin, edgeEnd] = graph_.getOutgoingEdges(current.nodeIndex);
        
        for (const Edge* edge = edgeBegin; edge != edgeEnd; ++edge) {
            uint32_t neighbor = edge->target;
            
            if (visited_[neighbor]) {
                continue;
            }
            
            // Calculate edge weight (travel time)
            double currentTime = departureTimeSec + current.gScore;
            double edgeWeight = getEdgeWeight(*edge, currentTime);
            
            // Calculate tentative g score
            double tentativeG = gScores_[current.nodeIndex] + edgeWeight;
            
            if (tentativeG < gScores_[neighbor]) {
                // This path is better
                gScores_[neighbor] = tentativeG;
                parents_[neighbor] = current.nodeIndex;
                parentEdges_[neighbor] = static_cast<uint32_t>(edge - &graph_.getEdge(0));
                
                double h = heuristic(neighbor, endNode, params.heuristicWeight);
                double fScore = tentativeG + h;
                
                openSet.push({neighbor, tentativeG, fScore,
                             current.nodeIndex,
                             static_cast<uint32_t>(edge - &graph_.getEdge(0))});
            }
        }
    }
    
    // No path found
    auto endTime = std::chrono::high_resolution_clock::now();
    double computeTimeMs = std::chrono::duration<double, std::milli>(
        endTime - startTime).count();
    
    Route result;
    result.found = false;
    result.nodesExplored = nodesExplored;
    result.computeTimeMs = computeTimeMs;
    return result;
}

double AStarEngine::heuristic(uint32_t fromNode, uint32_t toNode, double weight) const {
    const Coordinate& from = graph_.getNode(fromNode).coord;
    const Coordinate& to = graph_.getNode(toNode).coord;
    
    // Distance in meters
    double distance = from.distanceTo(to);
    
    // Optimistic time estimate: distance / max_speed
    double timeEstimate = distance / MAX_SPEED_MS;
    
    return timeEstimate * weight;
}

double AStarEngine::getEdgeWeight(const Edge& edge, double currentTimeSec) const {
    if (weightMgr_) {
        // Convert to system_clock time_point
        auto tp = std::chrono::system_clock::time_point(
            std::chrono::duration_cast<std::chrono::system_clock::duration>(
                std::chrono::duration<double>(currentTimeSec)));
        
        return weightMgr_->getWeight(edge.id, edge.baseTimeSec, tp);
    }
    
    return edge.baseTimeSec;
}

Route AStarEngine::reconstructPath(uint32_t startNode, uint32_t endNode,
                                    const SearchParams& params,
                                    double computeTimeMs,
                                    uint32_t nodesExplored) {
    Route result;
    result.found = true;
    result.nodesExplored = nodesExplored;
    result.computeTimeMs = computeTimeMs;
    result.totalDistanceM = 0;
    result.totalTimeSec = gScores_[endNode];
    
    // Reconstruct path by following parent pointers
    std::vector<uint32_t> path;
    std::vector<uint32_t> edgePath;
    
    uint32_t current = endNode;
    while (current != startNode && current != UINT32_MAX) {
        path.push_back(current);
        if (parentEdges_[current] != UINT32_MAX) {
            edgePath.push_back(parentEdges_[current]);
        }
        current = parents_[current];
    }
    path.push_back(startNode);
    
    // Reverse to get start-to-end order
    std::reverse(path.begin(), path.end());
    std::reverse(edgePath.begin(), edgePath.end());
    
    // Build geometry and segments
    for (uint32_t nodeIdx : path) {
        result.geometry.push_back(graph_.getNode(nodeIdx).coord);
    }
    
    for (uint32_t edgeIdx : edgePath) {
        const Edge& edge = graph_.getEdge(edgeIdx);
        
        RouteSegment seg;
        seg.edgeId = edge.id;
        seg.name = edge.name;
        seg.lengthM = edge.lengthM;
        seg.timeSec = edge.baseTimeSec;
        
        // Add node coordinates as geometry
        seg.geometry.push_back(graph_.getNode(edge.source).coord);
        seg.geometry.push_back(graph_.getNode(edge.target).coord);
        
        result.segments.push_back(std::move(seg));
        result.totalDistanceM += edge.lengthM;
    }
    
    return result;
}

void AStarEngine::resetState() {
    // Vectors will be reassigned in findRoute
}

}  // namespace chisinau
