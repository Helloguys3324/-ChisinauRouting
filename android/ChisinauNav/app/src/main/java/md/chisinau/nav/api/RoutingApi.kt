package md.chisinau.nav.api

import md.chisinau.nav.data.*
import retrofit2.Response
import retrofit2.http.*

/**
 * Retrofit interface for the Chișinău Routing REST API.
 */
interface RoutingApi {
    
    /**
     * Health check endpoint
     */
    @GET("/health")
    suspend fun health(): Response<HealthResponse>
    
    /**
     * Find route between two points
     */
    @POST("/route")
    suspend fun findRoute(@Body request: RouteRequest): Response<Route>
    
    /**
     * Map-match a GPS point to the road network
     */
    @POST("/map-match")
    suspend fun mapMatch(@Body request: MapMatchRequest): Response<MapMatchResult>
    
    /**
     * Get traffic data for a bounding box
     */
    @GET("/traffic")
    suspend fun getTraffic(
        @Query("sw_lat") swLat: Double,
        @Query("sw_lon") swLon: Double,
        @Query("ne_lat") neLat: Double,
        @Query("ne_lon") neLon: Double
    ): Response<List<EdgeTraffic>>
}
