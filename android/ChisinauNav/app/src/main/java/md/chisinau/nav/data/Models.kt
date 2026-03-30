package md.chisinau.nav.data

/**
 * Data models for the routing API.
 */

/**
 * Geographic coordinate (WGS84)
 */
data class Coordinate(
    val latitude: Double,
    val longitude: Double
)

/**
 * Route request to the routing API
 */
data class RouteRequest(
    val origin: Coordinate,
    val destination: Coordinate,
    val departure_time: Long? = null,
    val include_geometry: Boolean = true,
    val include_segments: Boolean = true
)

/**
 * Individual route segment (one road)
 */
data class RouteSegment(
    val edge_id: Long,
    val name: String,
    val length_m: Double,
    val time_sec: Double,
    val geometry: List<List<Double>>? = null  // [[lat, lon], ...]
)

/**
 * Complete route from API
 */
data class Route(
    val found: Boolean,
    val total_distance_m: Double,
    val total_time_sec: Double,
    val geometry: List<List<Double>>,  // [[lat, lon], ...]
    val segments: List<RouteSegment>,
    val nodes_explored: Int,
    val compute_time_ms: Double
) {
    /**
     * Convert geometry to list of Coordinates
     */
    fun geometryAsCoordinates(): List<Coordinate> {
        return geometry.map { Coordinate(it[0], it[1]) }
    }
    
    /**
     * Format distance for display
     */
    fun formatDistance(): String {
        return when {
            total_distance_m < 1000 -> "${total_distance_m.toInt()} m"
            else -> String.format("%.1f km", total_distance_m / 1000)
        }
    }
    
    /**
     * Format travel time for display
     */
    fun formatTime(): String {
        val minutes = (total_time_sec / 60).toInt()
        return when {
            minutes < 60 -> "$minutes min"
            else -> "${minutes / 60}h ${minutes % 60}min"
        }
    }
}

/**
 * Route API response wrapper
 */
data class RouteResponse(
    val route: Route? = null,
    val error: String? = null
)

/**
 * Map match request
 */
data class MapMatchRequest(
    val latitude: Double,
    val longitude: Double,
    val max_distance_m: Double = 50.0
)

/**
 * Map match result
 */
data class MapMatchResult(
    val matched: Boolean,
    val edge_id: Long,
    val distance_m: Double,
    val fraction: Double,
    val projected_point: Coordinate?
)

/**
 * Traffic data for an edge
 */
data class EdgeTraffic(
    val edge_id: Long,
    val current_speed_kmh: Double,
    val free_flow_speed_kmh: Double,
    val congestion_ratio: Double,
    val last_updated: Long
) {
    /**
     * Get congestion level for display
     */
    fun getCongestionLevel(): CongestionLevel {
        return when {
            congestion_ratio >= 0.9 -> CongestionLevel.FREE_FLOW
            congestion_ratio >= 0.7 -> CongestionLevel.LIGHT
            congestion_ratio >= 0.5 -> CongestionLevel.MODERATE
            congestion_ratio >= 0.3 -> CongestionLevel.HEAVY
            else -> CongestionLevel.SEVERE
        }
    }
}

/**
 * Congestion levels for visualization
 */
enum class CongestionLevel(val color: Int) {
    FREE_FLOW(0xFF00C853.toInt()),    // Green
    LIGHT(0xFFFFEB3B.toInt()),        // Yellow
    MODERATE(0xFFFF9800.toInt()),     // Orange
    HEAVY(0xFFFF5722.toInt()),        // Deep Orange
    SEVERE(0xFFD32F2F.toInt())        // Red
}

/**
 * Health check response
 */
data class HealthResponse(
    val healthy: Boolean,
    val status: String,
    val node_count: Long,
    val edge_count: Long,
    val profile_count: Long,
    val uptime_seconds: Double
)

/**
 * Navigation instruction for turn-by-turn
 */
data class NavigationInstruction(
    val type: InstructionType,
    val text: String,
    val distance_m: Double,
    val segment: RouteSegment
)

enum class InstructionType {
    DEPART,
    TURN_LEFT,
    TURN_RIGHT,
    TURN_SLIGHT_LEFT,
    TURN_SLIGHT_RIGHT,
    CONTINUE,
    ARRIVE
}
