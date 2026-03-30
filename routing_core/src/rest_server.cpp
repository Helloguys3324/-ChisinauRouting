/**
 * @file rest_server.cpp
 * @brief REST API server using cpp-httplib
 * 
 * Provides a simple HTTP API for routing queries.
 * 
 * Endpoints:
 *   GET  /health              - Health check
 *   POST /route               - Find route (JSON body with origin/destination)
 *   POST /map-match           - Map match GPS point to edge
 *   GET  /traffic?bbox=...    - Get traffic data for bounding box
 */

// cpp-httplib is header-only, download from:
// https://github.com/yhirose/cpp-httplib/blob/master/httplib.h
// Place in include/ directory

#ifdef CPPHTTPLIB_OPENSSL_SUPPORT
#define CPPHTTPLIB_OPENSSL_SUPPORT
#endif

// Minimal httplib stub for compilation without the actual header
// In production, include the real httplib.h
#ifndef HTTPLIB_H
#include <string>
#include <functional>
#include <map>

namespace httplib {
    struct Request {
        std::string body;
        std::map<std::string, std::string> params;
        std::string get_param_value(const std::string& key) const {
            auto it = params.find(key);
            return it != params.end() ? it->second : "";
        }
        bool has_param(const std::string& key) const {
            return params.find(key) != params.end();
        }
    };
    
    struct Response {
        std::string body;
        int status = 200;
        void set_content(const std::string& content, const std::string& type) {
            body = content;
        }
    };
    
    class Server {
    public:
        void Get(const std::string&, std::function<void(const Request&, Response&)>) {}
        void Post(const std::string&, std::function<void(const Request&, Response&)>) {}
        void set_mount_point(const std::string&, const std::string&) {}
        bool listen(const std::string&, int) { return true; }
        void stop() {}
    };
}
#else
#include "httplib.h"
#endif

#include "graph.hpp"
#include "astar.hpp"
#include "weight_manager.hpp"
#include "map_matcher.hpp"
#include "db_loader.hpp"

#include <iostream>
#include <sstream>
#include <chrono>
#include <memory>
#include <atomic>

using namespace chisinau;

// Simple JSON helpers (for production, use nlohmann/json or similar)
namespace json {
    std::string escape(const std::string& s) {
        std::string result;
        for (char c : s) {
            switch (c) {
                case '"': result += "\\\""; break;
                case '\\': result += "\\\\"; break;
                case '\n': result += "\\n"; break;
                case '\r': result += "\\r"; break;
                case '\t': result += "\\t"; break;
                default: result += c;
            }
        }
        return result;
    }
    
    // Very basic JSON parsing (for production, use proper library)
    double parseDouble(const std::string& json, const std::string& key) {
        size_t pos = json.find("\"" + key + "\"");
        if (pos == std::string::npos) return 0;
        pos = json.find(":", pos);
        if (pos == std::string::npos) return 0;
        return std::stod(json.substr(pos + 1));
    }
    
    std::string parseObject(const std::string& json, const std::string& key) {
        size_t pos = json.find("\"" + key + "\"");
        if (pos == std::string::npos) return "";
        pos = json.find("{", pos);
        if (pos == std::string::npos) return "";
        int depth = 1;
        size_t end = pos + 1;
        while (end < json.size() && depth > 0) {
            if (json[end] == '{') depth++;
            else if (json[end] == '}') depth--;
            end++;
        }
        return json.substr(pos, end - pos);
    }
}

class RestServer {
public:
    RestServer(int port = 8080)
        : port_(port), running_(false) {}
    
    ~RestServer() {
        stop();
    }
    
    void setGraph(std::shared_ptr<Graph> graph) { graph_ = graph; }
    void setRouter(std::shared_ptr<AStarEngine> router) { router_ = router; }
    void setMatcher(std::shared_ptr<MapMatcher> matcher) { matcher_ = matcher; }
    void setWeightManager(std::shared_ptr<WeightManager> weightMgr) { weightMgr_ = weightMgr; }
    
    void start() {
        startTime_ = std::chrono::steady_clock::now();
        running_ = true;
        
        setupRoutes();
        
        std::cout << "REST API server starting on port " << port_ << std::endl;
        std::cout << "Endpoints:" << std::endl;
        std::cout << "  GET  /health" << std::endl;
        std::cout << "  POST /route" << std::endl;
        std::cout << "  POST /map-match" << std::endl;
        std::cout << "  GET  /traffic" << std::endl;
        
        server_.listen("0.0.0.0", port_);
    }
    
    void stop() {
        if (running_) {
            running_ = false;
            server_.stop();
        }
    }

private:
    httplib::Server server_;
    int port_;
    std::atomic<bool> running_;
    std::chrono::steady_clock::time_point startTime_;
    
    std::shared_ptr<Graph> graph_;
    std::shared_ptr<AStarEngine> router_;
    std::shared_ptr<MapMatcher> matcher_;
    std::shared_ptr<WeightManager> weightMgr_;
    
    void setupRoutes() {
        // Health check
        server_.Get("/health", [this](const httplib::Request& req,
                                       httplib::Response& res) {
            handleHealth(req, res);
        });
        
        // Route finding
        server_.Post("/route", [this](const httplib::Request& req,
                                       httplib::Response& res) {
            handleRoute(req, res);
        });
        
        // Map matching
        server_.Post("/map-match", [this](const httplib::Request& req,
                                           httplib::Response& res) {
            handleMapMatch(req, res);
        });
        
        // Traffic data
        server_.Get("/traffic", [this](const httplib::Request& req,
                                        httplib::Response& res) {
            handleTraffic(req, res);
        });
    }
    
    void handleHealth(const httplib::Request& req, httplib::Response& res) {
        auto now = std::chrono::steady_clock::now();
        double uptime = std::chrono::duration<double>(now - startTime_).count();
        
        std::ostringstream json;
        json << "{"
             << "\"healthy\":true,"
             << "\"status\":\"running\","
             << "\"node_count\":" << (graph_ ? graph_->nodeCount() : 0) << ","
             << "\"edge_count\":" << (graph_ ? graph_->edgeCount() : 0) << ","
             << "\"profile_count\":" << (weightMgr_ ? weightMgr_->profileCount() : 0) << ","
             << "\"uptime_seconds\":" << uptime
             << "}";
        
        res.set_content(json.str(), "application/json");
    }
    
    void handleRoute(const httplib::Request& req, httplib::Response& res) {
        if (!router_ || !graph_) {
            res.status = 503;
            res.set_content("{\"error\":\"Router not initialized\"}", 
                           "application/json");
            return;
        }
        
        try {
            // Parse request body
            std::string originJson = json::parseObject(req.body, "origin");
            std::string destJson = json::parseObject(req.body, "destination");
            
            Coordinate origin(
                json::parseDouble(originJson, "latitude"),
                json::parseDouble(originJson, "longitude")
            );
            Coordinate dest(
                json::parseDouble(destJson, "latitude"),
                json::parseDouble(destJson, "longitude")
            );
            
            // Find route
            SearchParams params;
            Route route = router_->findRoute(origin, dest, params);
            
            // Build response
            std::ostringstream json;
            json << "{"
                 << "\"found\":" << (route.found ? "true" : "false") << ","
                 << "\"total_distance_m\":" << route.totalDistanceM << ","
                 << "\"total_time_sec\":" << route.totalTimeSec << ","
                 << "\"nodes_explored\":" << route.nodesExplored << ","
                 << "\"compute_time_ms\":" << route.computeTimeMs << ","
                 << "\"geometry\":[";
            
            for (size_t i = 0; i < route.geometry.size(); ++i) {
                if (i > 0) json << ",";
                json << "[" << route.geometry[i].latitude << ","
                     << route.geometry[i].longitude << "]";
            }
            json << "],"
                 << "\"segments\":[";
            
            for (size_t i = 0; i < route.segments.size(); ++i) {
                if (i > 0) json << ",";
                const auto& seg = route.segments[i];
                json << "{"
                     << "\"edge_id\":" << seg.edgeId << ","
                     << "\"name\":\"" << json::escape(seg.name) << "\","
                     << "\"length_m\":" << seg.lengthM << ","
                     << "\"time_sec\":" << seg.timeSec
                     << "}";
            }
            json << "]}";
            
            res.set_content(json.str(), "application/json");
            
        } catch (const std::exception& e) {
            res.status = 400;
            res.set_content("{\"error\":\"" + std::string(e.what()) + "\"}",
                           "application/json");
        }
    }
    
    void handleMapMatch(const httplib::Request& req, httplib::Response& res) {
        if (!matcher_) {
            res.status = 503;
            res.set_content("{\"error\":\"Matcher not initialized\"}", 
                           "application/json");
            return;
        }
        
        try {
            double lat = json::parseDouble(req.body, "latitude");
            double lon = json::parseDouble(req.body, "longitude");
            double maxDist = json::parseDouble(req.body, "max_distance_m");
            if (maxDist <= 0) maxDist = 50.0;
            
            Coordinate point(lat, lon);
            MatchResult result = matcher_->match(point, maxDist);
            
            std::ostringstream json;
            json << "{"
                 << "\"matched\":" << (result.matched ? "true" : "false") << ","
                 << "\"edge_id\":" << result.edgeIndex << ","
                 << "\"distance_m\":" << result.distanceM << ","
                 << "\"fraction\":" << result.fraction << ","
                 << "\"projected_point\":{"
                 << "\"latitude\":" << result.projectedPoint.latitude << ","
                 << "\"longitude\":" << result.projectedPoint.longitude
                 << "}}";
            
            res.set_content(json.str(), "application/json");
            
        } catch (const std::exception& e) {
            res.status = 400;
            res.set_content("{\"error\":\"" + std::string(e.what()) + "\"}",
                           "application/json");
        }
    }
    
    void handleTraffic(const httplib::Request& req, httplib::Response& res) {
        // Return empty array for now - would query edge traffic data
        res.set_content("{\"edges\":[]}", "application/json");
    }
};

int main(int argc, char* argv[]) {
    std::cout << "╔══════════════════════════════════════════════════════════╗" << std::endl;
    std::cout << "║        Chișinău Routing Engine - REST API Server         ║" << std::endl;
    std::cout << "╚══════════════════════════════════════════════════════════╝" << std::endl;
    
    int port = 8080;
    std::string dbHost = "localhost";
    std::string dbPassword = "routing_engine_2024";
    
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--port" && i + 1 < argc) {
            port = std::stoi(argv[++i]);
        } else if (arg == "--host" && i + 1 < argc) {
            dbHost = argv[++i];
        } else if (arg == "--password" && i + 1 < argc) {
            dbPassword = argv[++i];
        }
    }
    
    try {
        // Load graph
        DbConfig config;
        config.host = dbHost;
        config.password = dbPassword;
        
        DbLoader loader(config);
        auto graph = std::shared_ptr<Graph>(loader.loadGraph().release());
        
        // Load weights
        auto weightMgr = std::make_shared<WeightManager>();
        try {
            loader.loadWeights(*weightMgr);
        } catch (...) {
            std::cout << "Warning: Could not load weights" << std::endl;
        }
        
        // Build matcher
        auto matcher = std::make_shared<MapMatcher>(*graph);
        matcher->buildIndex(100.0);
        
        // Create router
        auto router = std::make_shared<AStarEngine>(*graph, weightMgr.get());
        
        // Start server
        RestServer server(port);
        server.setGraph(graph);
        server.setRouter(router);
        server.setMatcher(matcher);
        server.setWeightManager(weightMgr);
        server.start();
        
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}
