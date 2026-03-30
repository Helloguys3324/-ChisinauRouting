package md.chisinau.nav

import android.app.Application
import dagger.hilt.android.HiltAndroidApp

/**
 * Main Application class for Chișinău Navigation.
 * Uses Hilt for dependency injection.
 */
@HiltAndroidApp
class ChisinauNavApp : Application() {
    
    override fun onCreate() {
        super.onCreate()
        // Initialize any app-wide services here
    }
}
