/**
 * @file grpc_server.cpp
 * @brief gRPC server implementation for the routing service
 */

#include "graph.hpp"
#include "astar.hpp"
#include "weight_manager.hpp"
#include "map_matcher.hpp"
#include "db_loader.hpp"

// gRPC includes
#include <grpcpp/grpcpp.h>
#include <grpcpp/health_check_service_interface.h>

// Generated protobuf code (from routing.proto)
// #include "routing.grpc.pb.h"
// #include "routing.pb.h"

// For compilation without generated proto code, we define stubs
// In production, run protoc to generate these files
namespace chisinau {
namespace routing {

// Stub definitions - replace with actual generated code
struct Coordinate {
    double latitude() const { return lat_; }
    double longitude() const { return lon_; }
    void set_latitude(double v) { lat_ = v; }
    void set_longitude(double v) { lon_ = v; }
    double lat_ = 0, lon_ = 0;
};

struct RouteRequest {
    const Coordinate& origin() const { return origin_; }
    const Coordinate& destination() const { return dest_; }
    Coordinate origin_, dest_;
};

struct RouteSegment {
    void set_edge_id(int64_t v) {}
    void set_name(const std::string& v) {}
    void set_length_m(double v) {}
    void set_time_sec(double v) {}
    Coordinate* add_geometry() { return nullptr; }
};

struct Route {
    void set_found(bool v) {}
    void set_total_distance_m(double v) {}
    void set_total_time_sec(double v) {}
    void set_nodes_explored(uint32_t v) {}
    void set_compute_time_ms(double v) {}
    RouteSegment* add_segments() { return nullptr; }
    Coordinate* add_geometry() { return nullptr; }
};

struct RouteResponse {
    Route* mutable_route() { return &route_; }
    void set_error_message(const std::string& v) {}
    Route route_;
};

struct MapMatchRequest {
    const Coordinate& point() const { return point_; }
    double max_distance_m() const { return 50.0; }
    Coordinate point_;
};

struct MapMatchResult {
    void set_matched(bool v) {}
    void set_edge_id(int64_t v) {}
    void set_distance_m(double v) {}
    void set_fraction(double v) {}
    Coordinate* mutable_projected_point() { return nullptr; }
};

struct TrafficRequest {};
struct TrafficResponse {};

struct HealthRequest {};
struct HealthResponse {
    void set_healthy(bool v) {}
    void set_status(const std::string& v) {}
    void set_node_count(int64_t v) {}
    void set_edge_count(int64_t v) {}
    void set_profile_count(int64_t v) {}
    void set_uptime_seconds(double v) {}
};

// Service stub
class RoutingService {
public:
    class Service {
    public:
        virtual ~Service() = default;
        virtual grpc::Status FindRoute(grpc::ServerContext*, const RouteRequest*, RouteResponse*) {
            return grpc::Status::OK;
        }
        virtual grpc::Status MapMatch(grpc::ServerContext*, const MapMatchRequest*, MapMatchResult*) {
            return grpc::Status::OK;
        }
        virtual grpc::Status GetTraffic(grpc::ServerContext*, const TrafficRequest*, TrafficResponse*) {
            return grpc::Status::OK;
        }
        virtual grpc::Status Health(grpc::ServerContext*, const HealthRequest*, HealthResponse*) {
            return grpc::Status::OK;
        }
    };
};

}  // namespace routing
}  // namespace chisinau

#include <iostream>
#include <memory>
#include <chrono>
#include <atomic>

using namespace chisinau;

class RoutingServiceImpl final : public routing::RoutingService::Service {
public:
    RoutingServiceImpl(std::shared_ptr<Graph> graph,
                       std::shared_ptr<AStarEngine> router,
                       std::shared_ptr<MapMatcher> matcher,
                       std::shared_ptr<WeightManager> weightMgr)
        : graph_(graph), router_(router), matcher_(matcher), weightMgr_(weightMgr),
          startTime_(std::chrono::steady_clock::now()) {}
    
    grpc::Status FindRoute(grpc::ServerContext* context,
                           const routing::RouteRequest* request,
                           routing::RouteResponse* response) override {
        if (!router_) {
            response->set_error_message("Router not initialized");
            return grpc::Status(grpc::StatusCode::UNAVAILABLE, "Router not initialized");
        }
        
        // Convert request coordinates
        Coordinate origin(request->origin().latitude(), request->origin().longitude());
        Coordinate dest(request->destination().latitude(), request->destination().longitude());
        
        // Find route
        SearchParams params;
        Route route = router_->findRoute(origin, dest, params);
        
        // Build response
        routing::Route* routeMsg = response->mutable_route();
        routeMsg->set_found(route.found);
        routeMsg->set_total_distance_m(route.totalDistanceM);
        routeMsg->set_total_time_sec(route.totalTimeSec);
        routeMsg->set_nodes_explored(route.nodesExplored);
        routeMsg->set_compute_time_ms(route.computeTimeMs);
        
        // Add geometry
        for (const auto& coord : route.geometry) {
            routing::Coordinate* c = routeMsg->add_geometry();
            if (c) {
                c->set_latitude(coord.latitude);
                c->set_longitude(coord.longitude);
            }
        }
        
        // Add segments
        for (const auto& seg : route.segments) {
            routing::RouteSegment* s = routeMsg->add_segments();
            if (s) {
                s->set_edge_id(seg.edgeId);
                s->set_name(seg.name);
                s->set_length_m(seg.lengthM);
                s->set_time_sec(seg.timeSec);
            }
        }
        
        return grpc::Status::OK;
    }
    
    grpc::Status MapMatch(grpc::ServerContext* context,
                          const routing::MapMatchRequest* request,
                          routing::MapMatchResult* response) override {
        if (!matcher_) {
            return grpc::Status(grpc::StatusCode::UNAVAILABLE, "Matcher not initialized");
        }
        
        Coordinate point(request->point().latitude(), request->point().longitude());
        double maxDist = request->max_distance_m();
        if (maxDist <= 0) maxDist = 50.0;
        
        MatchResult result = matcher_->match(point, maxDist);
        
        response->set_matched(result.matched);
        response->set_edge_id(result.edgeIndex);
        response->set_distance_m(result.distanceM);
        response->set_fraction(result.fraction);
        
        routing::Coordinate* proj = response->mutable_projected_point();
        if (proj) {
            proj->set_latitude(result.projectedPoint.latitude);
            proj->set_longitude(result.projectedPoint.longitude);
        }
        
        return grpc::Status::OK;
    }
    
    grpc::Status GetTraffic(grpc::ServerContext* context,
                            const routing::TrafficRequest* request,
                            routing::TrafficResponse* response) override {
        // TODO: Implement traffic data retrieval
        return grpc::Status::OK;
    }
    
    grpc::Status Health(grpc::ServerContext* context,
                        const routing::HealthRequest* request,
                        routing::HealthResponse* response) override {
        auto now = std::chrono::steady_clock::now();
        double uptime = std::chrono::duration<double>(now - startTime_).count();
        
        response->set_healthy(true);
        response->set_status("running");
        response->set_node_count(graph_ ? graph_->nodeCount() : 0);
        response->set_edge_count(graph_ ? graph_->edgeCount() : 0);
        response->set_profile_count(weightMgr_ ? weightMgr_->profileCount() : 0);
        response->set_uptime_seconds(uptime);
        
        return grpc::Status::OK;
    }

private:
    std::shared_ptr<Graph> graph_;
    std::shared_ptr<AStarEngine> router_;
    std::shared_ptr<MapMatcher> matcher_;
    std::shared_ptr<WeightManager> weightMgr_;
    std::chrono::steady_clock::time_point startTime_;
};

void runServer(const std::string& address, RoutingServiceImpl& service) {
    grpc::ServerBuilder builder;
    
    // Listen on the given address without authentication
    builder.AddListeningPort(address, grpc::InsecureServerCredentials());
    
    // Register the service
    builder.RegisterService(&service);
    
    // Enable health checking
    grpc::EnableDefaultHealthCheckService(true);
    
    // Build and start the server
    std::unique_ptr<grpc::Server> server(builder.BuildAndStart());
    
    if (server) {
        std::cout << "gRPC server listening on " << address << std::endl;
        server->Wait();
    } else {
        std::cerr << "Failed to start gRPC server" << std::endl;
    }
}

int main(int argc, char* argv[]) {
    std::cout << "╔══════════════════════════════════════════════════════════╗" << std::endl;
    std::cout << "║        Chișinău Routing Engine - gRPC Server             ║" << std::endl;
    std::cout << "╚══════════════════════════════════════════════════════════╝" << std::endl;
    
    int port = 50051;
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
        
        // Create service
        RoutingServiceImpl service(graph, router, matcher, weightMgr);
        
        // Run server
        std::string address = "0.0.0.0:" + std::to_string(port);
        runServer(address, service);
        
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}
