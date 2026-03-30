package md.chisinau.nav.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import md.chisinau.nav.data.*
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Repository for routing operations.
 * Abstracts the API calls and provides a clean interface for the UI layer.
 */
@Singleton
class RoutingRepository @Inject constructor(
    private val api: RoutingApi
) {
    
    /**
     * Check if the routing service is healthy
     */
    suspend fun checkHealth(): Result<HealthResponse> = withContext(Dispatchers.IO) {
        try {
            val response = api.health()
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception("Health check failed: ${response.code()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    /**
     * Find a route between two coordinates
     */
    suspend fun findRoute(
        origin: Coordinate,
        destination: Coordinate,
        departureTime: Long? = null
    ): Result<Route> = withContext(Dispatchers.IO) {
        try {
            val request = RouteRequest(
                origin = origin,
                destination = destination,
                departure_time = departureTime,
                include_geometry = true,
                include_segments = true
            )
            
            val response = api.findRoute(request)
            if (response.isSuccessful && response.body() != null) {
                val route = response.body()!!
                if (route.found) {
                    Result.success(route)
                } else {
                    Result.failure(Exception("No route found"))
                }
            } else {
                Result.failure(Exception("Route request failed: ${response.code()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    /**
     * Map-match a GPS point to the nearest road edge
     */
    suspend fun mapMatch(
        latitude: Double,
        longitude: Double,
        maxDistance: Double = 50.0
    ): Result<MapMatchResult> = withContext(Dispatchers.IO) {
        try {
            val request = MapMatchRequest(
                latitude = latitude,
                longitude = longitude,
                max_distance_m = maxDistance
            )
            
            val response = api.mapMatch(request)
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception("Map match failed: ${response.code()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    /**
     * Get traffic data for a bounding box
     */
    suspend fun getTraffic(
        swLat: Double,
        swLon: Double,
        neLat: Double,
        neLon: Double
    ): Result<List<EdgeTraffic>> = withContext(Dispatchers.IO) {
        try {
            val response = api.getTraffic(swLat, swLon, neLat, neLon)
            if (response.isSuccessful) {
                Result.success(response.body() ?: emptyList())
            } else {
                Result.failure(Exception("Traffic request failed: ${response.code()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
