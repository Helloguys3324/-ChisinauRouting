package md.chisinau.nav.ui

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.google.android.material.bottomsheet.BottomSheetBehavior
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import md.chisinau.nav.R
import md.chisinau.nav.data.Coordinate
import md.chisinau.nav.data.Route
import md.chisinau.nav.databinding.ActivityMainBinding
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.geometry.LatLngBounds
import org.maplibre.android.location.LocationComponentActivationOptions
import org.maplibre.android.location.modes.CameraMode
import org.maplibre.android.location.modes.RenderMode
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.Style
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.PropertyFactory.*
import org.maplibre.android.style.sources.GeoJsonSource

/**
 * Main activity displaying the map and routing interface.
 */
@AndroidEntryPoint
class MainActivity : AppCompatActivity() {
    
    private lateinit var binding: ActivityMainBinding
    private val viewModel: MapViewModel by viewModels()
    
    private var map: MapLibreMap? = null
    private lateinit var routeBottomSheet: BottomSheetBehavior<View>
    
    // Route layer sources
    private var routeSource: GeoJsonSource? = null
    
    // Location permission launcher
    private val locationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val fineGranted = permissions[Manifest.permission.ACCESS_FINE_LOCATION] ?: false
        val coarseGranted = permissions[Manifest.permission.ACCESS_COARSE_LOCATION] ?: false
        
        if (fineGranted || coarseGranted) {
            enableLocationComponent()
        } else {
            Toast.makeText(this, "Location permission required for navigation", Toast.LENGTH_LONG).show()
        }
    }
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Initialize MapLibre
        MapLibre.getInstance(this)
        
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        
        setupMap(savedInstanceState)
        setupBottomSheet()
        setupClickListeners()
        observeViewModel()
    }
    
    private fun setupMap(savedInstanceState: Bundle?) {
        binding.mapView.onCreate(savedInstanceState)
        binding.mapView.getMapAsync { mapLibreMap ->
            map = mapLibreMap
            
            // Set map style (OpenStreetMap-based)
            mapLibreMap.setStyle(
                Style.Builder()
                    .fromUri("https://demotiles.maplibre.org/style.json")
            ) { style ->
                setupMapLayers(style)
                checkLocationPermission()
                centerOnChisinau()
            }
            
            // Map click listener for destination selection
            mapLibreMap.addOnMapClickListener { latLng ->
                handleMapClick(latLng)
                true
            }
            
            // Long click for origin selection
            mapLibreMap.addOnMapLongClickListener { latLng ->
                handleMapLongClick(latLng)
                true
            }
        }
    }
    
    private fun setupMapLayers(style: Style) {
        // Add route source
        routeSource = GeoJsonSource("route-source")
        style.addSource(routeSource!!)
        
        // Add route line layer
        val routeLayer = LineLayer("route-layer", "route-source").withProperties(
            lineColor(Color.parseColor("#4285F4")),
            lineWidth(6f),
            lineOpacity(0.8f),
            lineCap("round"),
            lineJoin("round")
        )
        style.addLayer(routeLayer)
        
        // Add traffic layer (for congestion visualization)
        val trafficSource = GeoJsonSource("traffic-source")
        style.addSource(trafficSource)
        
        val trafficLayer = LineLayer("traffic-layer", "traffic-source").withProperties(
            lineWidth(4f),
            lineOpacity(0.7f)
        )
        style.addLayerBelow(trafficLayer, "route-layer")
    }
    
    private fun centerOnChisinau() {
        // Center on Chișinău city center
        val chisinauCenter = LatLng(47.0245, 28.8322)
        map?.animateCamera(
            CameraUpdateFactory.newCameraPosition(
                CameraPosition.Builder()
                    .target(chisinauCenter)
                    .zoom(13.0)
                    .build()
            ),
            1000
        )
    }
    
    private fun checkLocationPermission() {
        when {
            ContextCompat.checkSelfPermission(
                this, Manifest.permission.ACCESS_FINE_LOCATION
            ) == PackageManager.PERMISSION_GRANTED -> {
                enableLocationComponent()
            }
            else -> {
                locationPermissionLauncher.launch(
                    arrayOf(
                        Manifest.permission.ACCESS_FINE_LOCATION,
                        Manifest.permission.ACCESS_COARSE_LOCATION
                    )
                )
            }
        }
    }
    
    private fun enableLocationComponent() {
        map?.style?.let { style ->
            val locationComponent = map?.locationComponent
            
            locationComponent?.activateLocationComponent(
                LocationComponentActivationOptions.builder(this, style)
                    .useDefaultLocationEngine(true)
                    .build()
            )
            
            try {
                locationComponent?.isLocationComponentEnabled = true
                locationComponent?.cameraMode = CameraMode.TRACKING
                locationComponent?.renderMode = RenderMode.COMPASS
            } catch (e: SecurityException) {
                // Permission not granted
            }
        }
    }
    
    private fun setupBottomSheet() {
        routeBottomSheet = BottomSheetBehavior.from(binding.routeInfoSheet)
        routeBottomSheet.state = BottomSheetBehavior.STATE_HIDDEN
    }
    
    private fun setupClickListeners() {
        // My location button
        binding.fabMyLocation.setOnClickListener {
            val location = map?.locationComponent?.lastKnownLocation
            if (location != null) {
                map?.animateCamera(
                    CameraUpdateFactory.newLatLngZoom(
                        LatLng(location.latitude, location.longitude),
                        15.0
                    )
                )
            } else {
                Toast.makeText(this, "Location not available", Toast.LENGTH_SHORT).show()
            }
        }
        
        // Clear route button
        binding.btnClearRoute.setOnClickListener {
            viewModel.clearRoute()
            routeBottomSheet.state = BottomSheetBehavior.STATE_HIDDEN
            clearRouteFromMap()
        }
        
        // Start navigation button
        binding.btnStartNavigation.setOnClickListener {
            // TODO: Start turn-by-turn navigation
            Toast.makeText(this, "Navigation starting...", Toast.LENGTH_SHORT).show()
        }
    }
    
    private fun observeViewModel() {
        lifecycleScope.launch {
            viewModel.uiState.collectLatest { state ->
                when (state) {
                    is MapUiState.Loading -> {
                        binding.progressBar.visibility = View.VISIBLE
                    }
                    is MapUiState.RouteFound -> {
                        binding.progressBar.visibility = View.GONE
                        displayRoute(state.route)
                    }
                    is MapUiState.Error -> {
                        binding.progressBar.visibility = View.GONE
                        Toast.makeText(this@MainActivity, state.message, Toast.LENGTH_LONG).show()
                    }
                    is MapUiState.Idle -> {
                        binding.progressBar.visibility = View.GONE
                    }
                }
            }
        }
    }
    
    private fun handleMapClick(latLng: LatLng) {
        val destination = Coordinate(latLng.latitude, latLng.longitude)
        viewModel.setDestination(destination)
        
        // If we have current location, request route
        val location = map?.locationComponent?.lastKnownLocation
        if (location != null) {
            val origin = Coordinate(location.latitude, location.longitude)
            viewModel.findRoute(origin, destination)
        } else {
            Toast.makeText(this, "Long press to set origin, or enable location", Toast.LENGTH_SHORT).show()
        }
    }
    
    private fun handleMapLongClick(latLng: LatLng) {
        val origin = Coordinate(latLng.latitude, latLng.longitude)
        viewModel.setOrigin(origin)
        Toast.makeText(this, "Origin set. Tap to set destination.", Toast.LENGTH_SHORT).show()
    }
    
    private fun displayRoute(route: Route) {
        // Build GeoJSON for route
        val coordinates = route.geometry.map { "[${it[1]}, ${it[0]}]" }.joinToString(",")
        val geoJson = """
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [$coordinates]
                }
            }
        """.trimIndent()
        
        routeSource?.setGeoJson(geoJson)
        
        // Fit camera to route
        if (route.geometry.isNotEmpty()) {
            val bounds = LatLngBounds.Builder()
            route.geometry.forEach { coord ->
                bounds.include(LatLng(coord[0], coord[1]))
            }
            map?.animateCamera(
                CameraUpdateFactory.newLatLngBounds(bounds.build(), 100)
            )
        }
        
        // Show route info
        binding.tvRouteDistance.text = route.formatDistance()
        binding.tvRouteTime.text = route.formatTime()
        binding.tvRouteSegments.text = "${route.segments.size} segments"
        routeBottomSheet.state = BottomSheetBehavior.STATE_COLLAPSED
    }
    
    private fun clearRouteFromMap() {
        routeSource?.setGeoJson("{\"type\":\"FeatureCollection\",\"features\":[]}")
    }
    
    // Lifecycle methods for MapView
    override fun onStart() {
        super.onStart()
        binding.mapView.onStart()
    }
    
    override fun onResume() {
        super.onResume()
        binding.mapView.onResume()
    }
    
    override fun onPause() {
        super.onPause()
        binding.mapView.onPause()
    }
    
    override fun onStop() {
        super.onStop()
        binding.mapView.onStop()
    }
    
    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        binding.mapView.onSaveInstanceState(outState)
    }
    
    override fun onLowMemory() {
        super.onLowMemory()
        binding.mapView.onLowMemory()
    }
    
    override fun onDestroy() {
        super.onDestroy()
        binding.mapView.onDestroy()
    }
}
