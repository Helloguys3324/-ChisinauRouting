/**
 * @file graph.cpp
 * @brief Graph implementation
 */

#include "graph.hpp"
#include <algorithm>
#include <sstream>
#include <cmath>

namespace chisinau {

void Graph::reserve(size_t nodeCount, size_t edgeCount) {
    nodes_.reserve(nodeCount);
    edges_.reserve(edgeCount);
    osmIdToIndex_.reserve(nodeCount);
}

uint32_t Graph::addNode(const Node& node) {
    uint32_t index = static_cast<uint32_t>(nodes_.size());
    nodes_.push_back(node);
    osmIdToIndex_[node.id] = index;
    return index;
}

void Graph::addEdge(const Edge& edge) {
    edges_.push_back(edge);
}

void Graph::finalize() {
    if (finalized_) return;
    
    // Sort edges by source node for adjacency list construction
    std::sort(edges_.begin(), edges_.end(),
              [](const Edge& a, const Edge& b) {
                  return a.source < b.source;
              });
    
    // Build adjacency list offsets
    for (auto& node : nodes_) {
        node.firstEdge = 0;
        node.edgeCount = 0;
    }
    
    uint32_t currentSource = UINT32_MAX;
    for (size_t i = 0; i < edges_.size(); ++i) {
        uint32_t source = edges_[i].source;
        
        if (source != currentSource) {
            if (source < nodes_.size()) {
                nodes_[source].firstEdge = static_cast<uint32_t>(i);
            }
            currentSource = source;
        }
        
        if (source < nodes_.size()) {
            nodes_[source].edgeCount++;
        }
    }
    
    finalized_ = true;
}

int32_t Graph::findNodeByOsmId(int64_t osmId) const {
    auto it = osmIdToIndex_.find(osmId);
    if (it != osmIdToIndex_.end()) {
        return static_cast<int32_t>(it->second);
    }
    return -1;
}

int32_t Graph::findNearestNode(const Coordinate& coord, double maxDistanceM) const {
    int32_t nearest = -1;
    double minDist = maxDistanceM;
    
    // Simple linear scan - for production use spatial index
    for (size_t i = 0; i < nodes_.size(); ++i) {
        double dist = coord.distanceTo(nodes_[i].coord);
        if (dist < minDist) {
            minDist = dist;
            nearest = static_cast<int32_t>(i);
        }
    }
    
    return nearest;
}

std::pair<const Edge*, const Edge*> Graph::getOutgoingEdges(uint32_t nodeIndex) const {
    if (nodeIndex >= nodes_.size()) {
        return {nullptr, nullptr};
    }
    
    const Node& node = nodes_[nodeIndex];
    if (node.edgeCount == 0) {
        return {nullptr, nullptr};
    }
    
    const Edge* first = &edges_[node.firstEdge];
    const Edge* last = first + node.edgeCount;
    return {first, last};
}

std::string Graph::getStats() const {
    std::ostringstream ss;
    ss << "Graph Statistics:\n";
    ss << "  Nodes: " << nodes_.size() << "\n";
    ss << "  Edges: " << edges_.size() << "\n";
    ss << "  Finalized: " << (finalized_ ? "yes" : "no") << "\n";
    
    if (!edges_.empty()) {
        double totalLength = 0;
        for (const auto& edge : edges_) {
            totalLength += edge.lengthM;
        }
        ss << "  Total road length: " << (totalLength / 1000.0) << " km\n";
    }
    
    return ss.str();
}

}  // namespace chisinau
