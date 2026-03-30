# PostgreSQL + PostGIS + TimescaleDB Setup Guide for Windows

This guide walks you through installing the database stack required for the Chișinău Routing Engine.

## Option 1: Docker (Recommended)

The easiest approach is using the TimescaleDB Docker image with PostGIS extension.

### Step 1: Install Docker Desktop
Download and install from: https://www.docker.com/products/docker-desktop/

### Step 2: Run TimescaleDB with PostGIS

```powershell
# Create a persistent volume for data
docker volume create chisinau_pgdata

# Run TimescaleDB with PostGIS
docker run -d `
  --name chisinau-db `
  -p 5432:5432 `
  -e POSTGRES_USER=chisinau `
  -e POSTGRES_PASSWORD=routing_engine_2024 `
  -e POSTGRES_DB=chisinau_routing `
  -v chisinau_pgdata:/var/lib/postgresql/data `
  timescale/timescaledb-ha:pg16-all

# Wait ~30 seconds for initialization, then verify
docker logs chisinau-db
```

### Step 3: Install PostGIS Extension
```powershell
# Connect to the database
docker exec -it chisinau-db psql -U chisinau -d chisinau_routing

# Inside psql, run:
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS timescaledb;
\dx  -- verify extensions are installed
\q
```

### Step 4: Initialize Schema
```powershell
# Run the init.sql script
docker exec -i chisinau-db psql -U chisinau -d chisinau_routing < D:\ChisinauRouting\database\init.sql
```

---

## Option 2: Native Windows Installation

### Step 1: Install PostgreSQL 16+
1. Download from: https://www.postgresql.org/download/windows/
2. Run the installer (include Stack Builder)
3. Set password for `postgres` user
4. Default port: 5432

### Step 2: Install PostGIS via Stack Builder
1. Launch Stack Builder (installed with PostgreSQL)
2. Select your PostgreSQL installation
3. Under "Spatial Extensions" → select PostGIS 3.4+
4. Complete installation

### Step 3: Install TimescaleDB
1. Download from: https://docs.timescale.com/self-hosted/latest/install/installation-windows/
2. Run the installer
3. Follow the prompts to configure with your PostgreSQL installation
4. Restart PostgreSQL service

### Step 4: Create Database and Extensions
```powershell
# Open psql (from Start Menu or command line)
psql -U postgres

# In psql:
CREATE DATABASE chisinau_routing;
CREATE USER chisinau WITH PASSWORD 'routing_engine_2024';
GRANT ALL PRIVILEGES ON DATABASE chisinau_routing TO chisinau;

\c chisinau_routing
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS timescaledb;

# Grant schema permissions
GRANT ALL ON SCHEMA public TO chisinau;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO chisinau;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO chisinau;
\q
```

### Step 5: Initialize Schema
```powershell
psql -U chisinau -d chisinau_routing -f D:\ChisinauRouting\database\init.sql
```

---

## Connection Details

After setup, use these connection parameters:

| Parameter | Value |
|-----------|-------|
| Host | localhost |
| Port | 5432 |
| Database | chisinau_routing |
| User | chisinau |
| Password | routing_engine_2024 |

**Connection string:**
```
postgresql://chisinau:routing_engine_2024@localhost:5432/chisinau_routing
```

---

## Verify Installation

```sql
-- Connect and check extensions
\c chisinau_routing
SELECT postgis_version();
SELECT extversion FROM pg_extension WHERE extname = 'timescaledb';

-- Check tables exist after running init.sql
\dt
```

Expected output should show PostGIS 3.x and TimescaleDB 2.x versions, plus tables: `nodes`, `edges`, `trolleybus_telemetry`, `tomtom_traffic`, `edge_speed_profiles`.
