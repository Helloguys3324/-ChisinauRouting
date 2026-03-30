/**
 * @file db_loader.hpp
 * @brief Database loading utilities for graph and weights
 */

#ifndef CHISINAU_DB_LOADER_HPP
#define CHISINAU_DB_LOADER_HPP

#include "graph.hpp"
#include "weight_manager.hpp"
#include <string>
#include <memory>

namespace chisinau {

/**
 * @brief Database connection configuration
 */
struct DbConfig {
    std::string host = "localhost";
    int port = 5432;
    std::string dbname = "chisinau_routing";
    std::string user = "chisinau";
    std::string password = "routing_engine_2024";
    
    /**
     * @brief Get libpq connection string
     */
    std::string connectionString() const;
};

/**
 * @brief Load graph and weights from PostgreSQL database
 */
class DbLoader {
public:
    explicit DbLoader(const DbConfig& config);
    ~DbLoader();
    
    /**
     * @brief Load road graph from database
     * 
     * Loads nodes and edges tables into in-memory graph.
     * 
     * @return Unique pointer to loaded graph
     */
    std::unique_ptr<Graph> loadGraph();
    
    /**
     * @brief Load edge speed profiles for weight manager
     * 
     * @param weightMgr WeightManager to populate
     * @return Number of profile entries loaded
     */
    size_t loadWeights(WeightManager& weightMgr);
    
    /**
     * @brief Get statistics about loaded data
     */
    std::string getStats() const;

private:
    DbConfig config_;
    void* conn_;  // PGconn* (opaque to avoid libpq header in hpp)
    
    size_t nodesLoaded_ = 0;
    size_t edgesLoaded_ = 0;
    size_t profilesLoaded_ = 0;
    
    /**
     * @brief Connect to database
     */
    void connect();
    
    /**
     * @brief Disconnect from database
     */
    void disconnect();
};

}  // namespace chisinau

#endif  // CHISINAU_DB_LOADER_HPP
