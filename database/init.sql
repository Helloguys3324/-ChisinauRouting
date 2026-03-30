-- =============================================================================
-- Chișinău Routing Engine - Database Schema
-- PostgreSQL + PostGIS + TimescaleDB
-- =============================================================================
-- Run this after creating the database and enabling extensions:
--   CREATE EXTENSION IF NOT EXISTS postgis;
--   CREATE EXTENSION IF NOT EXISTS timescaledb;
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. GRAPH TABLES: Nodes and Edges from OpenStreetMap
-- -----------------------------------------------------------------------------

-- Nodes represent intersections and waypoints from OSM
CREATE TABLE IF NOT EXISTS nodes (
    id              BIGINT PRIMARY KEY,         -- OSM node ID
    geom            GEOMETRY(Point, 4326),      -- WGS84 coordinates
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Spatial index for fast nearest-neighbor queries (map matching)
CREATE INDEX IF NOT EXISTS idx_nodes_geom ON nodes USING GIST(geom);

-- Edges represent road segments connecting nodes
CREATE TABLE IF NOT EXISTS edges (
    id              BIGSERIAL PRIMARY KEY,
    osm_way_id      BIGINT,                     -- Original OSM way ID
    source_node     BIGINT NOT NULL REFERENCES nodes(id),
    target_node     BIGINT NOT NULL REFERENCES nodes(id),
    geom            GEOMETRY(LineString, 4326), -- Full geometry of the edge
    
    -- Road attributes
    highway_type    VARCHAR(50),                -- 'primary', 'secondary', 'residential', etc.
    name            VARCHAR(255),               -- Street name
    oneway          BOOLEAN DEFAULT FALSE,      -- Is this a one-way street?
    
    -- Base weights (static, calculated from OSM data)
    length_m        DOUBLE PRECISION NOT NULL,  -- Length in meters
    max_speed_kmh   SMALLINT DEFAULT 50,        -- Speed limit (km/h), default 50 for urban
    base_time_sec   DOUBLE PRECISION,           -- Base travel time = length / max_speed
    
    -- Metadata
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Spatial index for edge geometries (map matching)
CREATE INDEX IF NOT EXISTS idx_edges_geom ON edges USING GIST(geom);

-- Index for graph traversal
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_node);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_node);

-- Composite index for bidirectional lookups
CREATE INDEX IF NOT EXISTS idx_edges_source_target ON edges(source_node, target_node);

-- -----------------------------------------------------------------------------
-- 2. TELEMETRY TABLE: Trolleybus GPS Data (GTFS-RT from Roataway)
-- This is a TimescaleDB hypertable for efficient time-series storage
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS trolleybus_telemetry (
    time            TIMESTAMPTZ NOT NULL,       -- Timestamp of the observation
    vehicle_id      VARCHAR(50) NOT NULL,       -- Trolleybus identifier
    route_id        VARCHAR(50),                -- GTFS route ID
    trip_id         VARCHAR(100),               -- GTFS trip ID
    
    -- Position
    latitude        DOUBLE PRECISION NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    geom            GEOMETRY(Point, 4326),      -- Computed from lat/lon
    
    -- Speed (if available from GTFS-RT)
    speed_kmh       REAL,                       -- Current speed
    bearing         REAL,                       -- Direction of travel (degrees)
    
    -- Map-matched edge (filled by traffic engine)
    matched_edge_id BIGINT,                     -- Edge this point was matched to
    
    -- Metadata
    ingested_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to TimescaleDB hypertable (auto-partitioned by time)
SELECT create_hypertable('trolleybus_telemetry', 'time', 
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

-- Index for vehicle trajectory queries
CREATE INDEX IF NOT EXISTS idx_telemetry_vehicle_time 
    ON trolleybus_telemetry(vehicle_id, time DESC);

-- Spatial index for map matching
CREATE INDEX IF NOT EXISTS idx_telemetry_geom 
    ON trolleybus_telemetry USING GIST(geom);

-- Index for edge-based aggregations
CREATE INDEX IF NOT EXISTS idx_telemetry_edge 
    ON trolleybus_telemetry(matched_edge_id, time DESC);

-- -----------------------------------------------------------------------------
-- 3. TOMTOM TRAFFIC TABLE: Real-time Traffic Flow Data
-- Also a TimescaleDB hypertable
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tomtom_traffic (
    time            TIMESTAMPTZ NOT NULL,       -- Observation timestamp
    location_id     VARCHAR(100) NOT NULL,      -- Our identifier for the monitored location
    location_name   VARCHAR(255),               -- Human-readable name
    
    -- Location (center point of the monitored segment)
    latitude        DOUBLE PRECISION NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    geom            GEOMETRY(Point, 4326),
    
    -- Traffic flow data from TomTom API
    current_speed   REAL,                       -- Current average speed (km/h)
    free_flow_speed REAL,                       -- Expected speed without traffic
    current_travel_time   INTEGER,              -- Current travel time (seconds)
    free_flow_travel_time INTEGER,              -- Travel time without traffic
    confidence      REAL,                       -- Data confidence (0-1)
    
    -- Road closure info
    road_closure    BOOLEAN DEFAULT FALSE,
    
    -- Map-matched edges (a monitored location may span multiple edges)
    matched_edge_ids BIGINT[],                  -- Array of edge IDs
    
    -- Metadata
    ingested_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable
SELECT create_hypertable('tomtom_traffic', 'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

-- Index for location-based queries
CREATE INDEX IF NOT EXISTS idx_tomtom_location_time 
    ON tomtom_traffic(location_id, time DESC);

-- Spatial index
CREATE INDEX IF NOT EXISTS idx_tomtom_geom 
    ON tomtom_traffic USING GIST(geom);

-- -----------------------------------------------------------------------------
-- 4. EDGE SPEED PROFILES: Pre-computed Historical Traffic Patterns
-- Stores average speeds per edge, per time bucket (e.g., hourly)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS edge_speed_profiles (
    edge_id         BIGINT NOT NULL REFERENCES edges(id),
    day_of_week     SMALLINT NOT NULL,          -- 0=Monday, 6=Sunday
    hour_of_day     SMALLINT NOT NULL,          -- 0-23
    
    -- Aggregated speed statistics
    avg_speed_kmh   REAL NOT NULL,              -- Average observed speed
    min_speed_kmh   REAL,                       -- Minimum observed
    max_speed_kmh   REAL,                       -- Maximum observed
    std_dev         REAL,                       -- Standard deviation
    sample_count    INTEGER DEFAULT 0,          -- Number of observations
    
    -- Computed travel time for this time slot
    avg_time_sec    REAL,                       -- Average travel time
    
    -- Metadata
    last_updated    TIMESTAMPTZ DEFAULT NOW(),
    
    PRIMARY KEY (edge_id, day_of_week, hour_of_day)
);

-- Index for quick profile lookups
CREATE INDEX IF NOT EXISTS idx_speed_profiles_lookup 
    ON edge_speed_profiles(day_of_week, hour_of_day);

-- -----------------------------------------------------------------------------
-- 5. MONITORED LOCATIONS: Configuration for TomTom API Polling
-- Defines which intersections/segments to monitor
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS monitored_locations (
    id              VARCHAR(100) PRIMARY KEY,   -- Unique identifier
    name            VARCHAR(255) NOT NULL,      -- Human-readable name
    description     TEXT,
    
    -- Location definition
    latitude        DOUBLE PRECISION NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    geom            GEOMETRY(Point, 4326),
    radius_m        INTEGER DEFAULT 100,        -- Monitoring radius
    
    -- TomTom API parameters
    tomtom_segment_id VARCHAR(255),             -- TomTom's segment identifier (if known)
    
    -- Status
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Some example monitored locations (major Chișinău intersections)
-- These can be updated based on actual traffic hotspots
INSERT INTO monitored_locations (id, name, latitude, longitude, geom) VALUES
    ('stefan-ismail', 'Bulevardul Ștefan cel Mare / Strada Ismail', 
     47.0245, 28.8322, ST_SetSRID(ST_MakePoint(28.8322, 47.0245), 4326)),
    ('decebal-calea-iesilor', 'Strada Decebal / Calea Ieșilor', 
     47.0412, 28.8156, ST_SetSRID(ST_MakePoint(28.8156, 47.0412), 4326)),
    ('center-piata-centrala', 'Piața Centrală', 
     47.0227, 28.8355, ST_SetSRID(ST_MakePoint(28.8355, 47.0227), 4326)),
    ('botanica-dacia', 'Bulevardul Dacia (Botanica)', 
     46.9923, 28.8512, ST_SetSRID(ST_MakePoint(28.8512, 46.9923), 4326)),
    ('rascani-moscow', 'Bulevardul Moscova (Râșcani)', 
     47.0456, 28.8678, ST_SetSRID(ST_MakePoint(28.8678, 47.0456), 4326))
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 6. HELPER FUNCTIONS
-- -----------------------------------------------------------------------------

-- Function to calculate travel time based on current conditions
-- Falls back to: edge profile -> edge base time -> distance/speed
CREATE OR REPLACE FUNCTION get_edge_travel_time(
    p_edge_id BIGINT,
    p_timestamp TIMESTAMPTZ DEFAULT NOW()
)
RETURNS DOUBLE PRECISION AS $$
DECLARE
    v_dow SMALLINT;
    v_hour SMALLINT;
    v_profile_time REAL;
    v_base_time DOUBLE PRECISION;
BEGIN
    -- Extract day of week and hour from timestamp
    v_dow := EXTRACT(DOW FROM p_timestamp)::SMALLINT;
    -- Convert Sunday=0 to Monday=0 format
    v_dow := CASE WHEN v_dow = 0 THEN 6 ELSE v_dow - 1 END;
    v_hour := EXTRACT(HOUR FROM p_timestamp)::SMALLINT;
    
    -- Try to get from speed profile
    SELECT avg_time_sec INTO v_profile_time
    FROM edge_speed_profiles
    WHERE edge_id = p_edge_id
      AND day_of_week = v_dow
      AND hour_of_day = v_hour
      AND sample_count >= 5;  -- Require minimum samples
    
    IF v_profile_time IS NOT NULL THEN
        RETURN v_profile_time;
    END IF;
    
    -- Fall back to base time
    SELECT base_time_sec INTO v_base_time
    FROM edges
    WHERE id = p_edge_id;
    
    RETURN COALESCE(v_base_time, 999999);  -- Return high value if edge not found
END;
$$ LANGUAGE plpgsql STABLE;

-- Function to find nearest edge to a GPS point (for map matching)
CREATE OR REPLACE FUNCTION find_nearest_edge(
    p_latitude DOUBLE PRECISION,
    p_longitude DOUBLE PRECISION,
    p_max_distance_m DOUBLE PRECISION DEFAULT 50.0
)
RETURNS TABLE(
    edge_id BIGINT,
    distance_m DOUBLE PRECISION,
    fraction DOUBLE PRECISION
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        e.id,
        ST_Distance(
            e.geom::geography,
            ST_SetSRID(ST_MakePoint(p_longitude, p_latitude), 4326)::geography
        ) AS dist,
        ST_LineLocatePoint(
            e.geom,
            ST_SetSRID(ST_MakePoint(p_longitude, p_latitude), 4326)
        ) AS frac
    FROM edges e
    WHERE ST_DWithin(
        e.geom::geography,
        ST_SetSRID(ST_MakePoint(p_longitude, p_latitude), 4326)::geography,
        p_max_distance_m
    )
    ORDER BY dist
    LIMIT 5;
END;
$$ LANGUAGE plpgsql STABLE;

-- -----------------------------------------------------------------------------
-- 7. CONTINUOUS AGGREGATES (TimescaleDB feature)
-- Auto-refreshing materialized views for traffic analysis
-- -----------------------------------------------------------------------------

-- Hourly speed aggregation per edge
CREATE MATERIALIZED VIEW IF NOT EXISTS hourly_edge_speeds
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    matched_edge_id,
    AVG(speed_kmh) AS avg_speed,
    MIN(speed_kmh) AS min_speed,
    MAX(speed_kmh) AS max_speed,
    STDDEV(speed_kmh) AS std_speed,
    COUNT(*) AS sample_count
FROM trolleybus_telemetry
WHERE matched_edge_id IS NOT NULL
  AND speed_kmh IS NOT NULL
  AND speed_kmh > 0
  AND speed_kmh < 120  -- Filter outliers
GROUP BY bucket, matched_edge_id
WITH NO DATA;

-- Refresh policy: update every hour, covering last 3 hours
SELECT add_continuous_aggregate_policy('hourly_edge_speeds',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- -----------------------------------------------------------------------------
-- 8. DATA RETENTION POLICIES
-- Automatically drop old data to manage storage
-- -----------------------------------------------------------------------------

-- Keep raw telemetry for 30 days
SELECT add_retention_policy('trolleybus_telemetry', 
    INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Keep TomTom data for 90 days
SELECT add_retention_policy('tomtom_traffic', 
    INTERVAL '90 days',
    if_not_exists => TRUE
);

-- -----------------------------------------------------------------------------
-- 9. STATISTICS AND MONITORING
-- -----------------------------------------------------------------------------

-- View for system health monitoring
CREATE OR REPLACE VIEW system_stats AS
SELECT
    (SELECT COUNT(*) FROM nodes) AS total_nodes,
    (SELECT COUNT(*) FROM edges) AS total_edges,
    (SELECT COUNT(*) FROM trolleybus_telemetry 
     WHERE time > NOW() - INTERVAL '1 hour') AS telemetry_last_hour,
    (SELECT COUNT(*) FROM tomtom_traffic 
     WHERE time > NOW() - INTERVAL '1 hour') AS tomtom_last_hour,
    (SELECT COUNT(*) FROM edge_speed_profiles 
     WHERE sample_count >= 10) AS edges_with_profiles,
    (SELECT MAX(time) FROM trolleybus_telemetry) AS last_telemetry,
    (SELECT MAX(time) FROM tomtom_traffic) AS last_tomtom;

-- =============================================================================
-- SCHEMA COMPLETE
-- =============================================================================

COMMENT ON TABLE nodes IS 'OSM intersection nodes for the Chișinău road graph';
COMMENT ON TABLE edges IS 'OSM road segments with base travel times';
COMMENT ON TABLE trolleybus_telemetry IS 'GTFS-RT trolleybus GPS observations (TimescaleDB hypertable)';
COMMENT ON TABLE tomtom_traffic IS 'TomTom Traffic Flow API observations (TimescaleDB hypertable)';
COMMENT ON TABLE edge_speed_profiles IS 'Pre-computed historical speed patterns per edge/time';
COMMENT ON TABLE monitored_locations IS 'Configuration for TomTom API polling locations';
