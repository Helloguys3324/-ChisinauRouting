/**
 * @file weight_manager.cpp
 * @brief Dynamic weight management implementation
 */

#include "weight_manager.hpp"
#include <libpq-fe.h>
#include <ctime>
#include <stdexcept>
#include <iostream>

namespace chisinau {

// TimeSlot implementation

TimeSlot TimeSlot::fromTime(std::chrono::system_clock::time_point tp) {
    auto time_t_val = std::chrono::system_clock::to_time_t(tp);
    std::tm* tm = std::localtime(&time_t_val);
    
    // tm_wday: 0=Sunday, need 0=Monday
    uint8_t dow = (tm->tm_wday == 0) ? 6 : tm->tm_wday - 1;
    uint8_t hour = static_cast<uint8_t>(tm->tm_hour);
    
    return TimeSlot(dow, hour);
}

TimeSlot TimeSlot::fromUnixTime(int64_t timestamp) {
    auto tp = std::chrono::system_clock::from_time_t(timestamp);
    return fromTime(tp);
}

// EdgeProfiles implementation

void EdgeProfiles::setProfile(const TimeSlot& slot, const SpeedProfile& profile) {
    uint16_t idx = slot.toIndex();
    if (idx < profiles_.size()) {
        profiles_[idx] = profile;
        hasData_ = true;
    }
}

const SpeedProfile& EdgeProfiles::getProfile(const TimeSlot& slot) const {
    static SpeedProfile empty;
    uint16_t idx = slot.toIndex();
    if (idx < profiles_.size()) {
        return profiles_[idx];
    }
    return empty;
}

// WeightManager implementation

WeightManager::WeightManager() = default;
WeightManager::~WeightManager() = default;

size_t WeightManager::loadFromDatabase(const DbConfig& config) {
    dbConfig_ = config;
    
    // Build connection string
    std::string connStr = "host=" + config.host +
                          " port=" + std::to_string(config.port) +
                          " dbname=" + config.dbname +
                          " user=" + config.user;
    if (!config.password.empty()) {
        connStr += " password=" + config.password;
    }
    
    // Connect
    PGconn* conn = PQconnectdb(connStr.c_str());
    if (PQstatus(conn) != CONNECTION_OK) {
        std::string error = PQerrorMessage(conn);
        PQfinish(conn);
        throw std::runtime_error("Database connection failed: " + error);
    }
    
    // Query all speed profiles
    const char* query = R"(
        SELECT edge_id, day_of_week, hour_of_day,
               avg_speed_kmh, min_speed_kmh, max_speed_kmh,
               std_dev, sample_count, avg_time_sec
        FROM edge_speed_profiles
        WHERE sample_count >= 5
        ORDER BY edge_id, day_of_week, hour_of_day
    )";
    
    PGresult* result = PQexec(conn, query);
    if (PQresultStatus(result) != PGRES_TUPLES_OK) {
        std::string error = PQerrorMessage(conn);
        PQclear(result);
        PQfinish(conn);
        throw std::runtime_error("Query failed: " + error);
    }
    
    // Load profiles
    std::lock_guard<std::mutex> lock(mutex_);
    edgeProfiles_.clear();
    
    int rows = PQntuples(result);
    size_t loadedCount = 0;
    
    for (int i = 0; i < rows; ++i) {
        int64_t edgeId = std::stoll(PQgetvalue(result, i, 0));
        uint8_t dow = static_cast<uint8_t>(std::stoi(PQgetvalue(result, i, 1)));
        uint8_t hour = static_cast<uint8_t>(std::stoi(PQgetvalue(result, i, 2)));
        
        SpeedProfile profile;
        profile.avgSpeedKmh = std::stof(PQgetvalue(result, i, 3));
        
        if (!PQgetisnull(result, i, 4))
            profile.minSpeedKmh = std::stof(PQgetvalue(result, i, 4));
        if (!PQgetisnull(result, i, 5))
            profile.maxSpeedKmh = std::stof(PQgetvalue(result, i, 5));
        if (!PQgetisnull(result, i, 6))
            profile.stdDev = std::stof(PQgetvalue(result, i, 6));
        
        profile.sampleCount = std::stoi(PQgetvalue(result, i, 7));
        
        if (!PQgetisnull(result, i, 8))
            profile.avgTimeSec = std::stof(PQgetvalue(result, i, 8));
        
        // Insert into map
        edgeProfiles_[edgeId].setProfile(TimeSlot(dow, hour), profile);
        loadedCount++;
    }
    
    PQclear(result);
    PQfinish(conn);
    
    std::cout << "Loaded " << loadedCount << " speed profile entries for "
              << edgeProfiles_.size() << " edges" << std::endl;
    
    return loadedCount;
}

void WeightManager::refresh() {
    // Reload from database
    if (!dbConfig_.host.empty()) {
        loadFromDatabase(dbConfig_);
    }
    
    // Also refresh real-time weights
    if (realTimeEnabled_) {
        loadRealTimeWeights();
    }
}

double WeightManager::getWeight(int64_t edgeId, double baseTimeSec,
                                 std::chrono::system_clock::time_point timestamp) const {
    TimeSlot slot = TimeSlot::fromTime(timestamp);
    return getWeight(edgeId, baseTimeSec, slot);
}

double WeightManager::getWeight(int64_t edgeId, double baseTimeSec,
                                 const TimeSlot& slot) const {
    std::lock_guard<std::mutex> lock(mutex_);
    
    // Look up historical profile
    auto it = edgeProfiles_.find(edgeId);
    if (it != edgeProfiles_.end() && it->second.hasProfiles()) {
        const SpeedProfile& profile = it->second.getProfile(slot);
        
        if (profile.isValid() && profile.avgTimeSec > 0) {
            double weight = profile.avgTimeSec;
            
            // Apply real-time adjustment if available
            if (realTimeEnabled_) {
                auto rtIt = realTimeWeights_.find(edgeId);
                if (rtIt != realTimeWeights_.end()) {
                    weight *= rtIt->second;
                }
            }
            
            return weight;
        }
    }
    
    // Fall back to base time
    return baseTimeSec;
}

size_t WeightManager::profileCount() const {
    std::lock_guard<std::mutex> lock(mutex_);
    
    size_t count = 0;
    for (const auto& [edgeId, profiles] : edgeProfiles_) {
        if (profiles.hasProfiles()) {
            count += EdgeProfiles::SLOTS_PER_WEEK;
        }
    }
    return count;
}

void WeightManager::loadRealTimeWeights() {
    // Connect to database and fetch recent TomTom data
    if (dbConfig_.host.empty()) return;
    
    std::string connStr = "host=" + dbConfig_.host +
                          " port=" + std::to_string(dbConfig_.port) +
                          " dbname=" + dbConfig_.dbname +
                          " user=" + dbConfig_.user;
    if (!dbConfig_.password.empty()) {
        connStr += " password=" + dbConfig_.password;
    }
    
    PGconn* conn = PQconnectdb(connStr.c_str());
    if (PQstatus(conn) != CONNECTION_OK) {
        PQfinish(conn);
        return;
    }
    
    // Get most recent TomTom readings (last 10 minutes)
    const char* query = R"(
        SELECT DISTINCT ON (unnest(matched_edge_ids)) 
               unnest(matched_edge_ids) as edge_id,
               current_speed / NULLIF(free_flow_speed, 0) as ratio
        FROM tomtom_traffic
        WHERE time > NOW() - INTERVAL '10 minutes'
          AND matched_edge_ids IS NOT NULL
          AND current_speed IS NOT NULL
          AND free_flow_speed > 0
        ORDER BY unnest(matched_edge_ids), time DESC
    )";
    
    PGresult* result = PQexec(conn, query);
    if (PQresultStatus(result) == PGRES_TUPLES_OK) {
        std::lock_guard<std::mutex> lock(mutex_);
        realTimeWeights_.clear();
        
        int rows = PQntuples(result);
        for (int i = 0; i < rows; ++i) {
            int64_t edgeId = std::stoll(PQgetvalue(result, i, 0));
            float ratio = std::stof(PQgetvalue(result, i, 1));
            
            // Convert speed ratio to time multiplier
            // If ratio < 1 (slower than free flow), time multiplier > 1
            if (ratio > 0 && ratio <= 2.0) {
                realTimeWeights_[edgeId] = 1.0f / ratio;
            }
        }
    }
    
    PQclear(result);
    PQfinish(conn);
}

}  // namespace chisinau
