package md.chisinau.nav.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import md.chisinau.nav.api.RoutingRepository
import md.chisinau.nav.data.Coordinate
import md.chisinau.nav.data.Route
import javax.inject.Inject

/**
 * UI state for the map screen
 */
sealed class MapUiState {
    object Idle : MapUiState()
    object Loading : MapUiState()
    data class RouteFound(val route: Route) : MapUiState()
    data class Error(val message: String) : MapUiState()
}

/**
 * ViewModel for the main map screen.
 */
@HiltViewModel
class MapViewModel @Inject constructor(
    private val repository: RoutingRepository
) : ViewModel() {
    
    private val _uiState = MutableStateFlow<MapUiState>(MapUiState.Idle)
    val uiState: StateFlow<MapUiState> = _uiState.asStateFlow()
    
    private var _origin: Coordinate? = null
    private var _destination: Coordinate? = null
    private var _currentRoute: Route? = null
    
    val origin: Coordinate? get() = _origin
    val destination: Coordinate? get() = _destination
    val currentRoute: Route? get() = _currentRoute
    
    /**
     * Set the route origin
     */
    fun setOrigin(coordinate: Coordinate) {
        _origin = coordinate
    }
    
    /**
     * Set the route destination
     */
    fun setDestination(coordinate: Coordinate) {
        _destination = coordinate
    }
    
    /**
     * Find a route between origin and destination
     */
    fun findRoute(origin: Coordinate, destination: Coordinate) {
        _origin = origin
        _destination = destination
        
        viewModelScope.launch {
            _uiState.value = MapUiState.Loading
            
            repository.findRoute(origin, destination)
                .onSuccess { route ->
                    _currentRoute = route
                    _uiState.value = MapUiState.RouteFound(route)
                }
                .onFailure { error ->
                    _uiState.value = MapUiState.Error(
                        error.message ?: "Failed to find route"
                    )
                }
        }
    }
    
    /**
     * Clear the current route
     */
    fun clearRoute() {
        _origin = null
        _destination = null
        _currentRoute = null
        _uiState.value = MapUiState.Idle
    }
    
    /**
     * Retry the last route request
     */
    fun retry() {
        val o = _origin
        val d = _destination
        if (o != null && d != null) {
            findRoute(o, d)
        }
    }
    
    /**
     * Check service health
     */
    fun checkHealth() {
        viewModelScope.launch {
            repository.checkHealth()
                .onSuccess { health ->
                    // Log health status
                    android.util.Log.d("MapViewModel", 
                        "Service healthy: ${health.node_count} nodes, ${health.edge_count} edges"
                    )
                }
                .onFailure { error ->
                    android.util.Log.e("MapViewModel", "Health check failed", error)
                }
        }
    }
}
