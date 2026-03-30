/**
 * @file db_loader.cpp
 * @brief Database loading implementation
 */

#include "db_loader.hpp"
#include <libpq-fe.h>
#include <stdexcept>
#include <iostream>
#include <sstream>

namespace chisinau {

std::string DbConfig::connectionString() const {
    std::ostringstream ss;
    ss << "host=" << host
       << " port=" << port
       << " dbname=" << dbname
       << " user=" << user;
    if (!password.empty()) {
        ss << " password=" << password;
    }
    return ss.str();
}

DbLoader::DbLoader(const DbConfig& config)
    : config_(config), conn_(nullptr) {
    connect();
}

DbLoader::~DbLoader() {
    disconnect();
}

void DbLoader::connect() {
    std::string connStr = config_.connectionString();
    conn_ = PQconnectdb(connStr.c_str());
    
    PGconn* pgconn = static_cast<PGconn*>(conn_);
    if (PQstatus(pgconn) != CONNECTION_OK) {
        std::string error = PQerrorMessage(pgconn);
        PQfinish(pgconn);
        conn_ = nullptr;
        throw std::runtime_error("Database connection failed: " + error);
    }
    
    std::cout << "Connected to database: " << config_.dbname << std::endl;
}

void DbLoader::disconnect() {
    if (conn_) {
        PQfinish(static_cast<PGconn*>(conn_));
        conn_ = nullptr;
    }
}

std::unique_ptr<Graph> DbLoader::loadGraph() {
    PGconn* pgconn = static_cast<PGconn*>(conn_);
    
    auto graph = std::make_unique<Graph>();
    
    // Count nodes and edges for reservation
    PGresult* countResult = PQexec(pgconn, 
        "SELECT (SELECT COUNT(*) FROM nodes), (SELECT COUNT(*) FROM edges)");
    
    if (PQresultStatus(countResult) != PGRES_TUPLES_OK) {
        std::string error = PQerrorMessage(pgconn);
        PQclear(countResult);
        throw std::runtime_error("Count query failed: " + error);
    }
    
    size_t nodeCount = std::stoull(PQgetvalue(countResult, 0, 0));
    size_t edgeCount = std::stoull(PQgetvalue(countResult, 0, 1));
    PQclear(countResult);
    
    std::cout << "Loading " << nodeCount << " nodes and " 
              << edgeCount << " edges..." << std::endl;
    
    graph->reserve(nodeCount, edgeCount);
    
    // Load nodes
    const char* nodeQuery = R"(
        SELECT id, ST_Y(geom) as lat, ST_X(geom) as lon
        FROM nodes
        ORDER BY id
    )";
    
    PGresult* nodeResult = PQexec(pgconn, nodeQuery);
    if (PQresultStatus(nodeResult) != PGRES_TUPLES_OK) {
        std::string error = PQerrorMessage(pgconn);
        PQclear(nodeResult);
        throw std::runtime_error("Node query failed: " + error);
    }
    
    int nodeRows = PQntuples(nodeResult);
    std::unordered_map<int64_t, uint32_t> nodeIdToIndex;
    
    for (int i = 0; i < nodeRows; ++i) {
        Node node;
        node.id = std::stoll(PQgetvalue(nodeResult, i, 0));
        node.coord.latitude = std::stod(PQgetvalue(nodeResult, i, 1));
        node.coord.longitude = std::stod(PQgetvalue(nodeResult, i, 2));
        node.firstEdge = 0;
        node.edgeCount = 0;
        
        uint32_t idx = graph->addNode(node);
        nodeIdToIndex[node.id] = idx;
    }
    PQclear(nodeResult);
    nodesLoaded_ = nodeRows;
    
    std::cout << "  Loaded " << nodeRows << " nodes" << std::endl;
    
    // Load edges
    const char* edgeQuery = R"(
        SELECT id, osm_way_id, source_node, target_node,
               highway_type, name, oneway,
               length_m, max_speed_kmh, base_time_sec
        FROM edges
        ORDER BY source_node
    )";
    
    PGresult* edgeResult = PQexec(pgconn, edgeQuery);
    if (PQresultStatus(edgeResult) != PGRES_TUPLES_OK) {
        std::string error = PQerrorMessage(pgconn);
        PQclear(edgeResult);
        throw std::runtime_error("Edge query failed: " + error);
    }
    
    int edgeRows = PQntuples(edgeResult);
    int skippedEdges = 0;
    
    for (int i = 0; i < edgeRows; ++i) {
        Edge edge;
        edge.id = std::stoll(PQgetvalue(edgeResult, i, 0));
        
        if (!PQgetisnull(edgeResult, i, 1)) {
            edge.osmWayId = std::stoll(PQgetvalue(edgeResult, i, 1));
        }
        
        int64_t sourceId = std::stoll(PQgetvalue(edgeResult, i, 2));
        int64_t targetId = std::stoll(PQgetvalue(edgeResult, i, 3));
        
        // Look up node indices
        auto sourceIt = nodeIdToIndex.find(sourceId);
        auto targetIt = nodeIdToIndex.find(targetId);
        
        if (sourceIt == nodeIdToIndex.end() || targetIt == nodeIdToIndex.end()) {
            skippedEdges++;
            continue;
        }
        
        edge.source = sourceIt->second;
        edge.target = targetIt->second;
        
        if (!PQgetisnull(edgeResult, i, 4)) {
            edge.highway = PQgetvalue(edgeResult, i, 4);
        }
        if (!PQgetisnull(edgeResult, i, 5)) {
            edge.name = PQgetvalue(edgeResult, i, 5);
        }
        
        edge.oneway = (PQgetvalue(edgeResult, i, 6)[0] == 't');
        edge.lengthM = std::stod(PQgetvalue(edgeResult, i, 7));
        edge.maxSpeedKmh = static_cast<int16_t>(std::stoi(PQgetvalue(edgeResult, i, 8)));
        edge.baseTimeSec = std::stod(PQgetvalue(edgeResult, i, 9));
        
        graph->addEdge(edge);
    }
    PQclear(edgeResult);
    edgesLoaded_ = edgeRows - skippedEdges;
    
    std::cout << "  Loaded " << edgesLoaded_ << " edges";
    if (skippedEdges > 0) {
        std::cout << " (" << skippedEdges << " skipped due to missing nodes)";
    }
    std::cout << std::endl;
    
    // Finalize graph
    std::cout << "  Finalizing graph..." << std::endl;
    graph->finalize();
    
    std::cout << "Graph loading complete!" << std::endl;
    std::cout << graph->getStats() << std::endl;
    
    return graph;
}

size_t DbLoader::loadWeights(WeightManager& weightMgr) {
    WeightManager::DbConfig wmConfig;
    wmConfig.host = config_.host;
    wmConfig.port = config_.port;
    wmConfig.dbname = config_.dbname;
    wmConfig.user = config_.user;
    wmConfig.password = config_.password;
    
    profilesLoaded_ = weightMgr.loadFromDatabase(wmConfig);
    return profilesLoaded_;
}

std::string DbLoader::getStats() const {
    std::ostringstream ss;
    ss << "Database Load Statistics:\n";
    ss << "  Nodes loaded:    " << nodesLoaded_ << "\n";
    ss << "  Edges loaded:    " << edgesLoaded_ << "\n";
    ss << "  Profiles loaded: " << profilesLoaded_ << "\n";
    return ss.str();
}

}  // namespace chisinau
