/**
 * @file map_matcher.cpp
 * @brief Map matching implementation
 */

#include "map_matcher.hpp"
#include <algorithm>
#include <cmath>
#include <limits>

namespace chisinau {

// Approximate meters per degree at Chișinău latitude (~47°)
constexpr double METERS_PER_DEG_LAT = 111320.0;
constexpr double METERS_PER_DEG_LON = 111320.0 * 0.682;  // cos(47°)

MapMatcher::MapMatcher(const Graph& graph) : graph_(graph) {}

void MapMatcher::buildIndex(double cellSizeM) {
    if (graph_.nodeCount() == 0) return;
    
    cellSizeM_ = cellSizeM;
    
    // Find bounding box
    minLat_ = std::numeric_limits<double>::max();
    maxLat_ = std::numeric_limits<double>::lowest();
    minLon_ = std::numeric_limits<double>::max();
    maxLon_ = std::numeric_limits<double>::lowest();
    
    for (size_t i = 0; i < graph_.nodeCount(); ++i) {
        const Node& node = graph_.getNode(static_cast<uint32_t>(i));
        minLat_ = std::min(minLat_, node.coord.latitude);
        maxLat_ = std::max(maxLat_, node.coord.latitude);
        minLon_ = std::min(minLon_, node.coord.longitude);
        maxLon_ = std::max(maxLon_, node.coord.longitude);
    }
    
    // Add padding
    double latPad = cellSizeM / METERS_PER_DEG_LAT;
    double lonPad = cellSizeM / METERS_PER_DEG_LON;
    minLat_ -= latPad;
    maxLat_ += latPad;
    minLon_ -= lonPad;
    maxLon_ += lonPad;
    
    // Calculate grid dimensions
    double heightM = (maxLat_ - minLat_) * METERS_PER_DEG_LAT;
    double widthM = (maxLon_ - minLon_) * METERS_PER_DEG_LON;
    
    gridRows_ = static_cast<size_t>(std::ceil(heightM / cellSizeM)) + 1;
    gridCols_ = static_cast<size_t>(std::ceil(widthM / cellSizeM)) + 1;
    
    // Initialize grid
    grid_.resize(gridRows_);
    for (auto& row : grid_) {
        row.resize(gridCols_);
    }
    
    // Index edges
    for (size_t i = 0; i < graph_.edgeCount(); ++i) {
        const Edge& edge = graph_.getEdge(static_cast<uint32_t>(i));
        const Node& source = graph_.getNode(edge.source);
        const Node& target = graph_.getNode(edge.target);
        
        // Get bounding box of edge
        double edgeMinLat = std::min(source.coord.latitude, target.coord.latitude);
        double edgeMaxLat = std::max(source.coord.latitude, target.coord.latitude);
        double edgeMinLon = std::min(source.coord.longitude, target.coord.longitude);
        double edgeMaxLon = std::max(source.coord.longitude, target.coord.longitude);
        
        // Find cells this edge overlaps
        auto [minRow, minCol] = coordToCell({edgeMinLat, edgeMinLon});
        auto [maxRow, maxCol] = coordToCell({edgeMaxLat, edgeMaxLon});
        
        // Clamp to grid bounds
        minRow = std::min(minRow, gridRows_ - 1);
        maxRow = std::min(maxRow, gridRows_ - 1);
        minCol = std::min(minCol, gridCols_ - 1);
        maxCol = std::min(maxCol, gridCols_ - 1);
        
        // Add edge to all overlapping cells
        for (size_t r = minRow; r <= maxRow; ++r) {
            for (size_t c = minCol; c <= maxCol; ++c) {
                grid_[r][c].edgeIndices.push_back(static_cast<uint32_t>(i));
            }
        }
    }
    
    indexed_ = true;
}

MatchResult MapMatcher::match(const Coordinate& coord, double maxDistanceM) const {
    MatchResult result;
    
    auto candidates = getCandidates(coord, 1, maxDistanceM);
    if (!candidates.empty()) {
        const MatchCandidate& best = candidates[0];
        result.matched = true;
        result.edgeIndex = best.edgeIndex;
        result.distanceM = best.distance;
        result.fraction = best.fraction;
        
        auto [frac, proj] = projectToEdge(coord, best.edgeIndex);
        result.projectedPoint = proj;
    }
    
    return result;
}

std::vector<MatchCandidate> MapMatcher::getCandidates(const Coordinate& coord,
                                                       size_t maxCandidates,
                                                       double maxDistanceM) const {
    std::vector<MatchCandidate> candidates;
    
    if (!indexed_) {
        // Fall back to linear scan
        for (size_t i = 0; i < graph_.edgeCount(); ++i) {
            const Edge& edge = graph_.getEdge(static_cast<uint32_t>(i));
            const Coordinate& source = graph_.getNode(edge.source).coord;
            const Coordinate& target = graph_.getNode(edge.target).coord;
            
            double fraction;
            double dist = distanceToSegment(coord, source, target, fraction);
            
            if (dist <= maxDistanceM) {
                candidates.push_back({static_cast<uint32_t>(i), dist, fraction});
            }
        }
    } else {
        // Use spatial index
        auto edges = getEdgesInRadius(coord, maxDistanceM);
        
        for (uint32_t edgeIdx : edges) {
            const Edge& edge = graph_.getEdge(edgeIdx);
            const Coordinate& source = graph_.getNode(edge.source).coord;
            const Coordinate& target = graph_.getNode(edge.target).coord;
            
            double fraction;
            double dist = distanceToSegment(coord, source, target, fraction);
            
            if (dist <= maxDistanceM) {
                candidates.push_back({edgeIdx, dist, fraction});
            }
        }
    }
    
    // Sort by distance
    std::sort(candidates.begin(), candidates.end());
    
    // Limit to max candidates
    if (candidates.size() > maxCandidates) {
        candidates.resize(maxCandidates);
    }
    
    return candidates;
}

std::pair<double, Coordinate> MapMatcher::projectToEdge(const Coordinate& coord,
                                                         uint32_t edgeIndex) const {
    const Edge& edge = graph_.getEdge(edgeIndex);
    const Coordinate& source = graph_.getNode(edge.source).coord;
    const Coordinate& target = graph_.getNode(edge.target).coord;
    
    // Calculate fraction along edge
    double dx = target.longitude - source.longitude;
    double dy = target.latitude - source.latitude;
    double lenSq = dx * dx + dy * dy;
    
    double fraction = 0.0;
    if (lenSq > 0) {
        double t = ((coord.longitude - source.longitude) * dx +
                    (coord.latitude - source.latitude) * dy) / lenSq;
        fraction = std::max(0.0, std::min(1.0, t));
    }
    
    // Calculate projected point
    Coordinate projected;
    projected.longitude = source.longitude + fraction * dx;
    projected.latitude = source.latitude + fraction * dy;
    
    return {fraction, projected};
}

std::pair<size_t, size_t> MapMatcher::coordToCell(const Coordinate& coord) const {
    size_t row = static_cast<size_t>(
        (coord.latitude - minLat_) / (maxLat_ - minLat_) * (gridRows_ - 1));
    size_t col = static_cast<size_t>(
        (coord.longitude - minLon_) / (maxLon_ - minLon_) * (gridCols_ - 1));
    
    return {std::min(row, gridRows_ - 1), std::min(col, gridCols_ - 1)};
}

std::vector<uint32_t> MapMatcher::getEdgesInRadius(const Coordinate& coord,
                                                    double radiusM) const {
    std::vector<uint32_t> result;
    
    // Convert radius to cell count
    size_t cellRadius = static_cast<size_t>(std::ceil(radiusM / cellSizeM_)) + 1;
    
    auto [centerRow, centerCol] = coordToCell(coord);
    
    // Calculate search bounds
    size_t minRow = (centerRow >= cellRadius) ? centerRow - cellRadius : 0;
    size_t maxRow = std::min(centerRow + cellRadius, gridRows_ - 1);
    size_t minCol = (centerCol >= cellRadius) ? centerCol - cellRadius : 0;
    size_t maxCol = std::min(centerCol + cellRadius, gridCols_ - 1);
    
    // Collect unique edges from cells
    std::vector<bool> seen(graph_.edgeCount(), false);
    
    for (size_t r = minRow; r <= maxRow; ++r) {
        for (size_t c = minCol; c <= maxCol; ++c) {
            for (uint32_t edgeIdx : grid_[r][c].edgeIndices) {
                if (!seen[edgeIdx]) {
                    seen[edgeIdx] = true;
                    result.push_back(edgeIdx);
                }
            }
        }
    }
    
    return result;
}

double MapMatcher::distanceToSegment(const Coordinate& point,
                                      const Coordinate& segStart,
                                      const Coordinate& segEnd,
                                      double& fraction) const {
    // Vector from start to end
    double dx = segEnd.longitude - segStart.longitude;
    double dy = segEnd.latitude - segStart.latitude;
    
    // Length squared
    double lenSq = dx * dx + dy * dy;
    
    if (lenSq < 1e-12) {
        // Degenerate segment
        fraction = 0.0;
        return point.distanceTo(segStart);
    }
    
    // Project point onto line
    double t = ((point.longitude - segStart.longitude) * dx +
                (point.latitude - segStart.latitude) * dy) / lenSq;
    
    // Clamp to segment
    fraction = std::max(0.0, std::min(1.0, t));
    
    // Find closest point on segment
    Coordinate closest;
    closest.longitude = segStart.longitude + fraction * dx;
    closest.latitude = segStart.latitude + fraction * dy;
    
    return point.distanceTo(closest);
}

}  // namespace chisinau
