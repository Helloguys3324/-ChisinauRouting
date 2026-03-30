/**
 * @file map_matcher.hpp
 * @brief Map matching for snapping GPS coordinates to road edges
 * 
 * Provides functionality to:
 * - Find nearest edge to a GPS point
 * - Project point onto edge geometry
 * - Handle ambiguous cases (intersections, parallel roads)
 */

#ifndef CHISINAU_MAP_MATCHER_HPP
#define CHISINAU_MAP_MATCHER_HPP

#include "graph.hpp"
#include <vector>
#include <optional>

namespace chisinau {

/**
 * @brief Result of map matching a single point
 */
struct MatchResult {
    bool matched;          ///< Was a match found?
    uint32_t edgeIndex;    ///< Matched edge index in graph
    double distanceM;      ///< Distance from point to edge
    double fraction;       ///< Position along edge (0=start, 1=end)
    Coordinate projectedPoint;  ///< Point projected onto edge
    
    MatchResult() : matched(false), edgeIndex(0), distanceM(0), fraction(0) {}
};

/**
 * @brief Map matching candidate
 */
struct MatchCandidate {
    uint32_t edgeIndex;
    double distance;
    double fraction;
    
    bool operator<(const MatchCandidate& other) const {
        return distance < other.distance;
    }
};

/**
 * @brief Map matcher using spatial index
 * 
 * Uses a simple grid-based spatial index for efficient nearest-edge queries.
 * For production, consider R-tree (e.g., boost::geometry::index).
 */
class MapMatcher {
public:
    /**
     * @brief Construct map matcher with graph reference
     */
    explicit MapMatcher(const Graph& graph);
    
    ~MapMatcher() = default;
    
    /**
     * @brief Build spatial index for efficient lookups
     * 
     * Must be called after graph is finalized, before matching.
     * 
     * @param cellSizeM Grid cell size in meters (default 100m)
     */
    void buildIndex(double cellSizeM = 100.0);
    
    /**
     * @brief Match a single GPS coordinate to nearest edge
     * 
     * @param coord GPS coordinate to match
     * @param maxDistanceM Maximum distance to consider (meters)
     * @return MatchResult with best match or matched=false
     */
    MatchResult match(const Coordinate& coord, double maxDistanceM = 50.0) const;
    
    /**
     * @brief Get multiple match candidates for a coordinate
     * 
     * Useful when the best match is ambiguous (e.g., at intersections).
     * 
     * @param coord GPS coordinate
     * @param maxCandidates Maximum number of candidates to return
     * @param maxDistanceM Maximum distance to consider
     * @return Vector of candidates sorted by distance
     */
    std::vector<MatchCandidate> getCandidates(const Coordinate& coord,
                                               size_t maxCandidates = 5,
                                               double maxDistanceM = 50.0) const;
    
    /**
     * @brief Project a point onto an edge
     * 
     * @param coord Point to project
     * @param edgeIndex Edge to project onto
     * @return Fraction along edge (0-1) and projected coordinate
     */
    std::pair<double, Coordinate> projectToEdge(const Coordinate& coord,
                                                 uint32_t edgeIndex) const;
    
    /**
     * @brief Check if spatial index is built
     */
    bool isIndexed() const { return indexed_; }

private:
    const Graph& graph_;
    
    // Grid-based spatial index
    struct GridCell {
        std::vector<uint32_t> edgeIndices;
    };
    
    std::vector<std::vector<GridCell>> grid_;
    double cellSizeM_ = 100.0;
    double minLat_ = 0, minLon_ = 0;
    double maxLat_ = 0, maxLon_ = 0;
    size_t gridRows_ = 0, gridCols_ = 0;
    bool indexed_ = false;
    
    /**
     * @brief Convert coordinate to grid cell indices
     */
    std::pair<size_t, size_t> coordToCell(const Coordinate& coord) const;
    
    /**
     * @brief Get edge indices in cells within radius of a coordinate
     */
    std::vector<uint32_t> getEdgesInRadius(const Coordinate& coord,
                                           double radiusM) const;
    
    /**
     * @brief Calculate perpendicular distance from point to line segment
     */
    double distanceToSegment(const Coordinate& point,
                             const Coordinate& segStart,
                             const Coordinate& segEnd,
                             double& fraction) const;
};

}  // namespace chisinau

#endif  // CHISINAU_MAP_MATCHER_HPP
