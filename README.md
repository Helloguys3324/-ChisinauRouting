# Chișinău GPS Routing Engine & Traffic Information System

A complete, custom-built routing engine for Chișinău, Moldova. Uses OpenStreetMap for the road network, trolleybus telemetry for historical traffic patterns, and TomTom API for real-time traffic.

## 🚀 Quick Start (One-Click)

**Double-click `START.bat` to launch everything!**

This will:
1. Start PostgreSQL database
2. Start telemetry workers (Roataway + TomTom)
3. Show live dashboard with trolleybus positions
4. Automatically stop everything when you close the window

## ⚙️ TomTom API Key Setup

1. Get your free API key at: https://developer.tomtom.com/
2. Edit file: `D:\ChisinauRouting\ingestion\.env`
3. Replace `YOUR_TOMTOM_API_KEY_HERE` with your key:
   ```
   TOMTOM_API_KEY=your_actual_key_here
   ```

Free tier allows 2,500 requests/day (polling every 10 minutes).

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Android App    │────▶│  REST/gRPC API  │────▶│  C++ Routing    │
│  (MapLibre)     │     │  Port 8080/50051│     │  Core (A*)      │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
┌─────────────────┐     ┌─────────────────┐     ┌────────▼────────┐
│  Roataway       │────▶│  Python Workers │────▶│  PostgreSQL     │
│  GTFS-RT        │     │  (Ingestion)    │     │  PostGIS        │
└─────────────────┘     └─────────────────┘     │  TimescaleDB    │
                                                └─────────────────┘
```

## Project Structure

```
D:\ChisinauRouting\
├── START.bat              ← ONE-CLICK LAUNCHER
├── routing.bat            ← Manual control script
├── ingestion\
│   ├── .env               ← PUT YOUR TOMTOM API KEY HERE
│   ├── dashboard.py       ← Live dashboard
│   ├── gtfsrt_worker.py   ← Trolleybus telemetry
│   ├── tomtom_worker.py   ← Traffic data
│   └── osm_extractor.py   ← Road network import
├── routing_core\          ← C++ A* routing engine
│   └── build.bat          ← Build script
├── database\
│   └── init.sql           ← Database schema
└── tools\
    └── cmake\             ← CMake for C++ builds
```

## Manual Commands

```powershell
# Start PostgreSQL only
D:\ChisinauRouting\routing.bat start

# Stop PostgreSQL
D:\ChisinauRouting\routing.bat stop

# Open SQL console
D:\ChisinauRouting\routing.bat psql

# Show database stats
D:\ChisinauRouting\routing.bat status
```

## Database Connection

| Parameter | Value |
|-----------|-------|
| Host | localhost |
| Port | 5432 |
| Database | chisinau_routing |
| User | chisinau |
| Password | routing_engine_2024 |

## Building C++ Routing Core

1. Install Visual Studio Build Tools (C++ workload)
2. Run: `D:\ChisinauRouting\routing_core\build.bat`

## Data Sources

- **Road Network**: OpenStreetMap via OSMnx
- **Trolleybus Telemetry**: Roataway GTFS-RT (https://roataway.md)
- **Real-time Traffic**: TomTom Traffic Flow API

# Start workers
python gtfsrt_worker.py &
python tomtom_worker.py --mock &
```

#### C++ Routing Core
```powershell
cd routing_core
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
cmake --build .

# Run
./rest_server --port 8080
```

## API Reference

### REST API (Port 8080)

#### Health Check
```bash
GET /health
```
Response:
```json
{
  "healthy": true,
  "status": "running",
  "node_count": 45231,
  "edge_count": 98452,
  "profile_count": 156840
}
```

#### Find Route
```bash
POST /route
Content-Type: application/json

{
  "origin": {"latitude": 47.0245, "longitude": 28.8322},
  "destination": {"latitude": 47.0456, "longitude": 28.8678}
}
```
Response:
```json
{
  "found": true,
  "total_distance_m": 4523.7,
  "total_time_sec": 612,
  "geometry": [[47.0245, 28.8322], ...],
  "segments": [
    {"edge_id": 1234, "name": "Bulevardul Ștefan cel Mare", "length_m": 450, "time_sec": 45}
  ],
  "compute_time_ms": 12.5
}
```

#### Map Match
```bash
POST /map-match
Content-Type: application/json

{
  "latitude": 47.0250,
  "longitude": 28.8340,
  "max_distance_m": 50
}
```

### gRPC API (Port 50051)

See `routing_core/proto/routing.proto` for service definitions.

```protobuf
service RoutingService {
  rpc FindRoute(RouteRequest) returns (RouteResponse);
  rpc MapMatch(MapMatchRequest) returns (MapMatchResult);
  rpc GetTraffic(TrafficRequest) returns (TrafficResponse);
  rpc Health(HealthRequest) returns (HealthResponse);
}
```

## Project Structure

```
D:\ChisinauRouting\
├── database/
│   ├── init.sql                 # Database schema
│   └── setup_instructions.md    # Installation guide
├── ingestion/
│   ├── config.py                # Configuration management
│   ├── osm_extractor.py         # OSM → PostgreSQL
│   ├── gtfsrt_worker.py         # Roataway telemetry
│   ├── tomtom_worker.py         # TomTom Traffic API
│   └── traffic_engine.py        # Speed profile calculation
├── routing_core/
│   ├── include/                 # C++ headers
│   ├── src/                     # C++ implementation
│   ├── proto/                   # gRPC definitions
│   └── CMakeLists.txt
├── android/
│   └── ChisinauNav/             # Android app
└── docker/
    └── docker-compose.yml       # Full stack deployment
```

## Data Sources

1. **OpenStreetMap** (via OSMnx)
   - Road network graph for Chișinău
   - ~45k nodes, ~100k edges

2. **Roataway GTFS-RT**
   - Real-time trolleybus positions
   - Used as floating car data for traffic estimation
   - https://github.com/roataway

3. **TomTom Traffic Flow API**
   - Real-time traffic at critical intersections
   - Requires API key from developer.tomtom.com

## Configuration

Create `.env` in `ingestion/`:
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=chisinau_routing
DB_USER=chisinau
DB_PASSWORD=routing_engine_2024

ROATAWAY_POLL_INTERVAL_SECONDS=30
TOMTOM_API_KEY=your_key_here
TOMTOM_POLL_INTERVAL_SECONDS=300
```

## Android App

The Android app uses:
- **MapLibre GL** for map rendering (OpenStreetMap tiles)
- **Retrofit** for REST API calls
- **gRPC** for high-performance routing
- **Hilt** for dependency injection

Build with Android Studio or:
```bash
cd android/ChisinauNav
./gradlew assembleDebug
```

## License

MIT License - See LICENSE file
