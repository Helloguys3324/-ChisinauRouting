/**
 * @file weight_manager.hpp
 * @brief Dynamic edge weight management based on traffic patterns
 * 
 * Provides time-varying edge weights by looking up historical
 * speed profiles from the database.
 */

#ifndef CHISINAU_WEIGHT_MANAGER_HPP
#define CHISINAU_WEIGHT_MANAGER_HPP

#include <unordered_map>
#include <vector>
#include <cstdint>
#include <chrono>
#include <mutex>
#include <memory>

namespace chisinau {

/**
 * @brief Speed profile for a single time slot (day + hour)
 */
struct SpeedProfile {
    float avgSpeedKmh;
    float minSpeedKmh;
    float maxSpeedKmh;
    float stdDev;
    int32_t sampleCount;
    float avgTimeSec;  // Pre-computed travel time
    
    SpeedProfile() : avgSpeedKmh(0), minSpeedKmh(0), maxSpeedKmh(0),
                     stdDev(0), sampleCount(0), avgTimeSec(0) {}
    
    bool isValid() const { return sampleCount >= 5; }
};

/**
 * @brief Time slot key (combines day and hour)
 */
struct TimeSlot {
    uint8_t dayOfWeek;   // 0=Monday, 6=Sunday
    uint8_t hourOfDay;   // 0-23
    
    TimeSlot() : dayOfWeek(0), hourOfDay(0) {}
    TimeSlot(uint8_t dow, uint8_t hour) : dayOfWeek(dow), hourOfDay(hour) {}
    
    /**
     * @brief Create from system time
     */
    static TimeSlot fromTime(std::chrono::system_clock::time_point tp);
    
    /**
     * @brief Create from Unix timestamp (seconds since epoch)
     */
    static TimeSlot fromUnixTime(int64_t timestamp);
    
    /**
     * @brief Get slot index (0-167 for 7 days × 24 hours)
     */
    uint16_t toIndex() const { return dayOfWeek * 24 + hourOfDay; }
};

/**
 * @brief Per-edge speed profiles for all time slots
 * 
 * Stores 168 profiles (7 days × 24 hours) per edge.
 */
class EdgeProfiles {
public:
    static constexpr size_t SLOTS_PER_WEEK = 7 * 24;  // 168
    
    EdgeProfiles() : profiles_(SLOTS_PER_WEEK) {}
    
    /**
     * @brief Set profile for a time slot
     */
    void setProfile(const TimeSlot& slot, const SpeedProfile& profile);
    
    /**
     * @brief Get profile for a time slot
     */
    const SpeedProfile& getProfile(const TimeSlot& slot) const;
    
    /**
     * @brief Check if any profiles are set
     */
    bool hasProfiles() const { return hasData_; }
    
private:
    std::vector<SpeedProfile> profiles_;
    bool hasData_ = false;
};

/**
 * @brief Manages time-varying edge weights
 * 
 * Thread-safe weight lookups with periodic refresh from database.
 */
class WeightManager {
public:
    /**
     * @brief Database connection parameters
     */
    struct DbConfig {
        std::string host = "localhost";
        int port = 5432;
        std::string dbname = "chisinau_routing";
        std::string user = "chisinau";
        std::string password;
    };
    
    WeightManager();
    ~WeightManager();
    
    /**
     * @brief Load all edge profiles from database
     * 
     * @param config Database connection configuration
     * @return Number of edges loaded
     */
    size_t loadFromDatabase(const DbConfig& config);
    
    /**
     * @brief Refresh profiles from database (incremental update)
     */
    void refresh();
    
    /**
     * @brief Get edge weight (travel time) for a given time
     * 
     * @param edgeId Database edge ID
     * @param baseTimeSec Fallback base travel time
     * @param timestamp Time for which to get weight
     * @return Travel time in seconds
     */
    double getWeight(int64_t edgeId, double baseTimeSec,
                     std::chrono::system_clock::time_point timestamp) const;
    
    /**
     * @brief Get edge weight using time slot
     */
    double getWeight(int64_t edgeId, double baseTimeSec,
                     const TimeSlot& slot) const;
    
    /**
     * @brief Get number of edges with profiles
     */
    size_t edgeCount() const { return edgeProfiles_.size(); }
    
    /**
     * @brief Get total number of profile entries
     */
    size_t profileCount() const;
    
    /**
     * @brief Check if real-time updates are enabled
     */
    bool isRealTimeEnabled() const { return realTimeEnabled_; }
    
    /**
     * @brief Enable/disable real-time weight adjustments
     * 
     * When enabled, applies recent TomTom data on top of profiles.
     */
    void setRealTimeEnabled(bool enabled) { realTimeEnabled_ = enabled; }

private:
    // Edge ID -> profiles mapping
    std::unordered_map<int64_t, EdgeProfiles> edgeProfiles_;
    
    // Recent real-time weights (edge ID -> current weight multiplier)
    std::unordered_map<int64_t, float> realTimeWeights_;
    
    // Thread safety
    mutable std::mutex mutex_;
    
    // Configuration
    bool realTimeEnabled_ = true;
    DbConfig dbConfig_;
    
    /**
     * @brief Load real-time weights from TomTom data
     */
    void loadRealTimeWeights();
};

}  // namespace chisinau

#endif  // CHISINAU_WEIGHT_MANAGER_HPP
