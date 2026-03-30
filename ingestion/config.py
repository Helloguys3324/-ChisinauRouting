"""
Configuration management for Chișinău Routing Engine.

Uses pydantic-settings for type-safe configuration with environment variable support.
Create a .env file in the ingestion directory or set environment variables.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
import os


class DatabaseSettings(BaseSettings):
    """PostgreSQL connection settings."""
    
    model_config = SettingsConfigDict(
        env_prefix='DB_',
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )
    
    host: str = Field(default='localhost', description='Database host')
    port: int = Field(default=5432, description='Database port')
    name: str = Field(default='chisinau_routing', description='Database name')
    user: str = Field(default='chisinau', description='Database user')
    password: str = Field(default='routing_engine_2024', description='Database password')
    
    @property
    def connection_string(self) -> str:
        """SQLAlchemy connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
    
    @property
    def psycopg2_params(self) -> dict:
        """Connection parameters for psycopg2."""
        return {
            'host': self.host,
            'port': self.port,
            'dbname': self.name,
            'user': self.user,
            'password': self.password
        }


class OSMSettings(BaseSettings):
    """OpenStreetMap extraction settings."""
    
    model_config = SettingsConfigDict(
        env_prefix='OSM_',
        env_file='.env',
        extra='ignore'
    )
    
    # Chișinău bounding box (expanded slightly for suburbs)
    place_name: str = Field(
        default='Chișinău, Moldova',
        description='Place name for osmnx geocoding'
    )
    
    # Alternative: explicit bounding box
    # North, South, East, West bounds
    bbox_north: float = Field(default=47.08, description='North latitude')
    bbox_south: float = Field(default=46.95, description='South latitude')
    bbox_east: float = Field(default=28.95, description='East longitude')
    bbox_west: float = Field(default=28.75, description='West longitude')
    
    # Network type
    network_type: str = Field(
        default='drive',
        description='OSMnx network type: drive, walk, bike, all'
    )
    
    # Default speed limits by road type (km/h)
    default_speeds: dict = Field(
        default={
            'motorway': 90,
            'motorway_link': 60,
            'trunk': 70,
            'trunk_link': 50,
            'primary': 60,
            'primary_link': 40,
            'secondary': 50,
            'secondary_link': 40,
            'tertiary': 40,
            'tertiary_link': 30,
            'residential': 30,
            'living_street': 20,
            'service': 20,
            'unclassified': 30,
            'road': 30,
        },
        description='Default speed limits by highway type'
    )


class RoatawaySettings(BaseSettings):
    """Roataway GTFS-RT settings for trolleybus telemetry."""
    
    model_config = SettingsConfigDict(
        env_prefix='ROATAWAY_',
        env_file='.env',
        extra='ignore'
    )
    
    # GTFS-RT vehicle positions endpoint
    # Based on https://github.com/roataway/roataway-server
    vehicle_positions_url: str = Field(
        default='https://roataway.md/api/v1/vehicle_positions.pb',
        description='GTFS-RT vehicle positions protobuf endpoint'
    )
    
    # Alternative JSON API (if protobuf not available)
    json_api_url: str = Field(
        default='https://roataway.md/api/v1/vehicles',
        description='JSON API for vehicle positions'
    )
    
    # Polling interval
    poll_interval_seconds: int = Field(
        default=30,
        description='How often to poll for new positions'
    )
    
    # Request timeout
    timeout_seconds: int = Field(default=10, description='HTTP request timeout')


class TomTomSettings(BaseSettings):
    """TomTom Traffic Flow API settings."""
    
    model_config = SettingsConfigDict(
        env_prefix='TOMTOM_',
        env_file='.env',
        extra='ignore'
    )
    
    # API key (required for TomTom API)
    api_key: Optional[str] = Field(
        default=None,
        description='TomTom API key (get from developer.tomtom.com)'
    )
    
    # Traffic Flow API base URL
    base_url: str = Field(
        default='https://api.tomtom.com/traffic/services/4/flowSegmentData',
        description='TomTom Traffic Flow API base URL'
    )
    
    # Polling interval (10 min for free tier - 2500 requests/day limit)
    poll_interval_seconds: int = Field(
        default=600,  # 10 minutes for free tier
        description='How often to poll TomTom API'
    )
    
    # Request parameters
    unit: str = Field(default='KMPH', description='Speed unit: KMPH or MPH')
    thickness: int = Field(default=10, description='Road thickness for query')
    zoom: int = Field(default=18, description='Zoom level for query precision')
    
    @property
    def is_configured(self) -> bool:
        """Check if TomTom API is properly configured."""
        return self.api_key is not None and len(self.api_key) > 10


class TrafficEngineSettings(BaseSettings):
    """Traffic analysis engine settings."""
    
    model_config = SettingsConfigDict(
        env_prefix='TRAFFIC_',
        env_file='.env',
        extra='ignore'
    )
    
    # Map matching
    max_match_distance_m: float = Field(
        default=50.0,
        description='Maximum distance to match GPS point to edge'
    )
    
    # Speed calculation
    min_speed_kmh: float = Field(
        default=3.0,
        description='Minimum realistic speed (filter GPS noise)'
    )
    max_speed_kmh: float = Field(
        default=120.0,
        description='Maximum realistic speed (filter outliers)'
    )
    
    # Profile aggregation
    min_samples_for_profile: int = Field(
        default=5,
        description='Minimum samples needed to create speed profile'
    )
    
    # Profile update interval
    profile_update_interval_minutes: int = Field(
        default=60,
        description='How often to recalculate speed profiles'
    )


class Settings(BaseSettings):
    """Main application settings aggregating all subsettings."""
    
    model_config = SettingsConfigDict(
        env_file='.env',
        extra='ignore'
    )
    
    # Application metadata
    app_name: str = Field(default='Chișinău Routing Engine')
    debug: bool = Field(default=False, description='Enable debug logging')
    log_level: str = Field(default='INFO', description='Logging level')
    
    # Sub-configurations
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    osm: OSMSettings = Field(default_factory=OSMSettings)
    roataway: RoatawaySettings = Field(default_factory=RoatawaySettings)
    tomtom: TomTomSettings = Field(default_factory=TomTomSettings)
    traffic: TrafficEngineSettings = Field(default_factory=TrafficEngineSettings)


# Global settings instance
settings = Settings()


# Example .env file content
ENV_TEMPLATE = """
# Chișinău Routing Engine Configuration
# Copy this to .env and customize as needed

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=chisinau_routing
DB_USER=chisinau
DB_PASSWORD=routing_engine_2024

# OSM Settings
OSM_PLACE_NAME=Chișinău, Moldova
OSM_NETWORK_TYPE=drive

# Roataway GTFS-RT
ROATAWAY_POLL_INTERVAL_SECONDS=30

# TomTom API (get key from developer.tomtom.com)
TOMTOM_API_KEY=your_api_key_here
TOMTOM_POLL_INTERVAL_SECONDS=300

# Traffic Engine
TRAFFIC_MAX_MATCH_DISTANCE_M=50

# Application
DEBUG=false
LOG_LEVEL=INFO
"""


def create_env_template():
    """Create a template .env file if it doesn't exist."""
    env_path = os.path.join(os.path.dirname(__file__), '.env.template')
    if not os.path.exists(env_path):
        with open(env_path, 'w') as f:
            f.write(ENV_TEMPLATE.strip())
        print(f"Created {env_path}")


if __name__ == '__main__':
    # Print current configuration
    create_env_template()
    print("Current Settings:")
    print(f"  Database: {settings.db.connection_string}")
    print(f"  OSM Place: {settings.osm.place_name}")
    print(f"  Roataway URL: {settings.roataway.vehicle_positions_url}")
    print(f"  TomTom Configured: {settings.tomtom.is_configured}")
