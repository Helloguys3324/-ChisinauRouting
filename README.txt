============================================================
  CHIȘINĂU ROUTING ENGINE - QUICK START GUIDE
============================================================

📍 PROJECT LOCATION: D:\ChisinauRouting

🚀 START THE SERVER
   Double-click: START_MAP.bat
   - Opens web map on http://localhost:5000
   - On phone (same WiFi): http://192.168.0.11:5000

🛑 STOP THE SERVER
   Double-click: STOP_MAP.bat
   - Safely stops the web server

📱 ANDROID APP
   APK Location: C:\Users\PC\Desktop\ChisinauTransport.apk
   - Install on Android phone
   - Allow location permission when asked
   - Server must be running on PC

============================================================
  FEATURES
============================================================

✅ 3D map with MapLibre GL JS
✅ Real-time trolleybus simulation (25 vehicles, 8 routes)
✅ Traffic data from TomTom API
✅ GPS location tracking
✅ Mobile-friendly responsive UI
✅ Dark theme

============================================================
  CONTROLS
============================================================

📍 My Location - Show your GPS position
🚦 Traffic - Toggle traffic fog layer
3D/2D - Switch camera view
+/− - Zoom in/out

============================================================
  ARCHITECTURE
============================================================

Database: PostgreSQL 16 + PostGIS + TimescaleDB
  Port: 5432
  Database: chisinau_routing
  User: chisinau
  Password: routing_engine_2024

Road Network:
  - 3,192 nodes
  - 7,810 edges
  - 1,289 km total length

Web Server: Flask + Socket.IO (port 5000)
  - Python 3.x + venv
  - Real-time WebSocket updates every 2 seconds

Simulation:
  - 25 trolleybuses on 8 routes
  - Routes: 1, 2, 3, 5, 8, 10, 22, 24
  - Speed: 15-50 km/h

Traffic:
  - 8 monitoring points across Chișinău
  - TomTom Flow API (with simulated fallback)
  - Color coding: 🟢 Free >40 km/h, 🟡 Slow 20-40, 🔴 Jam <20

============================================================
  FILES & FOLDERS
============================================================

D:\ChisinauRouting\
  ├─ START_MAP.bat         ← Start web server
  ├─ STOP_MAP.bat          ← Stop web server
  ├─ webapp\
  │   ├─ app.py            ← Main Flask server
  │   └─ templates\
  │       └─ index.html    ← 3D map interface
  ├─ ingestion\
  │   ├─ venv\             ← Python virtual environment
  │   ├─ trolleybus_simulator.py
  │   ├─ gtfsrt_worker.py
  │   └─ tomtom_worker.py
  ├─ scripts\
  │   ├─ init.sql          ← Database schema
  │   └─ osm_extractor.py  ← Road network import
  └─ routing\              ← C++ routing core (future)

D:\PostgreSQL\            ← PostgreSQL portable
C:\Users\PC\AndroidStudioProjects\ChisinauTransport\  ← Android app

============================================================
  TROUBLESHOOTING
============================================================

Problem: "Port 5000 already in use"
Solution: Run STOP_MAP.bat first

Problem: "Cannot connect to database"
Solution: Check PostgreSQL is running:
  D:\PostgreSQL\pgsql\bin\pg_ctl.exe -D D:\PostgreSQL\data status

Problem: "Location error" on Android
Solution: 
  1. Grant location permission in app settings
  2. Reinstall latest APK from Desktop

Problem: Trolleybuses not moving
Solution: Refresh browser/app - WebSocket should reconnect

============================================================
  DEVELOPMENT
============================================================

Python Environment:
  D:\ChisinauRouting\ingestion\venv\Scripts\activate

Install Dependencies:
  pip install -r requirements.txt

Database Connection:
  psql -U chisinau -d chisinau_routing -h localhost -p 5432

Android Build:
  cd C:\Users\PC\AndroidStudioProjects\ChisinauTransport
  set JAVA_HOME=D:\jdk-17
  gradlew.bat assembleDebug

============================================================
  API ENDPOINTS
============================================================

GET /                     → Web map interface
GET /api/trolleybuses     → All trolleybus positions
GET /api/routes           → Route definitions
GET /api/stats            → System statistics
GET /api/traffic          → Traffic data (8 points)

WebSocket Events:
  - trolleybus_update     → Real-time position updates (every 2s)

============================================================
  CREDITS
============================================================

Built with assistance from GitHub Copilot CLI
Data sources:
  - OpenStreetMap (road network)
  - Roataway project (GTFS data - currently unavailable)
  - TomTom Traffic API

============================================================
