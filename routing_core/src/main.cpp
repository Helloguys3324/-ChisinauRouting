/**
 * @file main.cpp
 * @brief Chișinău Routing Engine - Main entry point
 * 
 * Demonstrates loading the graph and performing routing queries.
 */

#include "graph.hpp"
#include "astar.hpp"
#include "weight_manager.hpp"
#include "map_matcher.hpp"
#include "db_loader.hpp"

#include <iostream>
#include <iomanip>
#include <chrono>
#include <string>

using namespace chisinau;

void printRoute(const Route& route) {
    if (!route.found) {
        std::cout << "No route found!" << std::endl;
        return;
    }
    
    std::cout << "\n=== ROUTE FOUND ===" << std::endl;
    std::cout << "Distance:      " << std::fixed << std::setprecision(1) 
              << route.totalDistanceM << " m ("
              << route.totalDistanceM / 1000.0 << " km)" << std::endl;
    std::cout << "Travel time:   " << route.totalTimeSec << " sec ("
              << route.totalTimeSec / 60.0 << " min)" << std::endl;
    std::cout << "Segments:      " << route.segments.size() << std::endl;
    std::cout << "Nodes explored:" << route.nodesExplored << std::endl;
    std::cout << "Compute time:  " << route.computeTimeMs << " ms" << std::endl;
    
    std::cout << "\nRoute segments:" << std::endl;
    for (size_t i = 0; i < route.segments.size() && i < 10; ++i) {
        const auto& seg = route.segments[i];
        std::cout << "  " << (i + 1) << ". ";
        if (!seg.name.empty()) {
            std::cout << seg.name;
        } else {
            std::cout << "(unnamed)";
        }
        std::cout << " - " << seg.lengthM << " m, " 
                  << seg.timeSec << " s" << std::endl;
    }
    
    if (route.segments.size() > 10) {
        std::cout << "  ... and " << (route.segments.size() - 10) 
                  << " more segments" << std::endl;
    }
}

void runInteractiveMode(AStarEngine& router) {
    std::cout << "\n=== Interactive Routing Mode ===" << std::endl;
    std::cout << "Enter coordinates as: start_lat start_lon end_lat end_lon" << std::endl;
    std::cout << "Example: 47.0245 28.8322 47.0412 28.8156" << std::endl;
    std::cout << "Enter 'quit' to exit." << std::endl;
    
    std::string line;
    while (true) {
        std::cout << "\n> ";
        std::getline(std::cin, line);
        
        if (line == "quit" || line == "exit" || line == "q") {
            break;
        }
        
        double startLat, startLon, endLat, endLon;
        if (sscanf(line.c_str(), "%lf %lf %lf %lf", 
                   &startLat, &startLon, &endLat, &endLon) != 4) {
            std::cout << "Invalid input. Format: start_lat start_lon end_lat end_lon"
                      << std::endl;
            continue;
        }
        
        Coordinate start(startLat, startLon);
        Coordinate end(endLat, endLon);
        
        std::cout << "Routing from (" << startLat << ", " << startLon 
                  << ") to (" << endLat << ", " << endLon << ")..." << std::endl;
        
        SearchParams params;
        Route route = router.findRoute(start, end, params);
        printRoute(route);
    }
}

void runBenchmark(const Graph& graph, AStarEngine& router) {
    std::cout << "\n=== Benchmark Mode ===" << std::endl;
    
    // Sample coordinates in Chișinău
    struct TestCase {
        const char* name;
        Coordinate start;
        Coordinate end;
    };
    
    std::vector<TestCase> testCases = {
        {"Center to Botanica", 
         {47.0227, 28.8355}, {46.9923, 28.8512}},
        {"Stefan cel Mare to Rascani",
         {47.0245, 28.8322}, {47.0456, 28.8678}},
        {"Buiucani to Ciocana",
         {47.0350, 28.8100}, {47.0280, 28.8750}},
        {"Short: Central Market area",
         {47.0227, 28.8355}, {47.0250, 28.8400}},
    };
    
    std::cout << std::setw(35) << std::left << "Test Case"
              << std::setw(12) << std::right << "Distance"
              << std::setw(12) << "Time"
              << std::setw(12) << "Nodes"
              << std::setw(12) << "Compute"
              << std::endl;
    std::cout << std::string(83, '-') << std::endl;
    
    double totalComputeTime = 0;
    int successCount = 0;
    
    for (const auto& tc : testCases) {
        SearchParams params;
        Route route = router.findRoute(tc.start, tc.end, params);
        
        std::cout << std::setw(35) << std::left << tc.name;
        
        if (route.found) {
            std::cout << std::setw(10) << std::right << std::fixed 
                      << std::setprecision(0) << route.totalDistanceM << " m"
                      << std::setw(10) << route.totalTimeSec << " s"
                      << std::setw(12) << route.nodesExplored
                      << std::setw(10) << std::setprecision(2) 
                      << route.computeTimeMs << " ms";
            totalComputeTime += route.computeTimeMs;
            successCount++;
        } else {
            std::cout << "  NOT FOUND";
        }
        std::cout << std::endl;
    }
    
    std::cout << std::string(83, '-') << std::endl;
    std::cout << "Success rate: " << successCount << "/" << testCases.size()
              << ", Avg compute time: " 
              << (successCount > 0 ? totalComputeTime / successCount : 0)
              << " ms" << std::endl;
}

int main(int argc, char* argv[]) {
    std::cout << "╔══════════════════════════════════════════════════════════╗" << std::endl;
    std::cout << "║        Chișinău GPS Routing Engine v1.0.0                ║" << std::endl;
    std::cout << "╚══════════════════════════════════════════════════════════╝" << std::endl;
    
    // Parse command line arguments
    bool benchmark = false;
    bool interactive = false;
    std::string dbHost = "localhost";
    std::string dbPassword = "routing_engine_2024";
    
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--benchmark" || arg == "-b") {
            benchmark = true;
        } else if (arg == "--interactive" || arg == "-i") {
            interactive = true;
        } else if (arg == "--host" && i + 1 < argc) {
            dbHost = argv[++i];
        } else if (arg == "--password" && i + 1 < argc) {
            dbPassword = argv[++i];
        } else if (arg == "--help" || arg == "-h") {
            std::cout << "\nUsage: " << argv[0] << " [options]\n\n"
                      << "Options:\n"
                      << "  -b, --benchmark    Run benchmark tests\n"
                      << "  -i, --interactive  Interactive routing mode\n"
                      << "  --host HOST        Database host (default: localhost)\n"
                      << "  --password PASS    Database password\n"
                      << "  -h, --help         Show this help\n"
                      << std::endl;
            return 0;
        }
    }
    
    try {
        // Configure database connection
        DbConfig config;
        config.host = dbHost;
        config.password = dbPassword;
        
        std::cout << "\nConnecting to database..." << std::endl;
        DbLoader loader(config);
        
        // Load graph
        std::cout << "\nLoading road network..." << std::endl;
        auto startLoad = std::chrono::high_resolution_clock::now();
        auto graph = loader.loadGraph();
        auto endLoad = std::chrono::high_resolution_clock::now();
        
        double loadTimeMs = std::chrono::duration<double, std::milli>(
            endLoad - startLoad).count();
        std::cout << "Graph loaded in " << loadTimeMs << " ms" << std::endl;
        
        // Load traffic weights
        std::cout << "\nLoading traffic weights..." << std::endl;
        WeightManager weightMgr;
        try {
            loader.loadWeights(weightMgr);
            std::cout << "Loaded " << weightMgr.profileCount() 
                      << " speed profile entries" << std::endl;
        } catch (const std::exception& e) {
            std::cout << "Warning: Could not load weights: " << e.what() << std::endl;
            std::cout << "Using base travel times." << std::endl;
        }
        
        // Build map matcher index
        std::cout << "\nBuilding spatial index..." << std::endl;
        MapMatcher matcher(*graph);
        matcher.buildIndex(100.0);
        std::cout << "Spatial index ready." << std::endl;
        
        // Create router
        AStarEngine router(*graph, &weightMgr);
        
        // Run requested mode
        if (benchmark) {
            runBenchmark(*graph, router);
        }
        
        if (interactive) {
            runInteractiveMode(router);
        }
        
        if (!benchmark && !interactive) {
            // Default: run a sample query
            std::cout << "\n=== Sample Route ===" << std::endl;
            Coordinate start(47.0245, 28.8322);  // Central Chișinău
            Coordinate end(47.0456, 28.8678);    // Râșcani
            
            std::cout << "Routing from Stefan cel Mare to Rascani..." << std::endl;
            
            SearchParams params;
            Route route = router.findRoute(start, end, params);
            printRoute(route);
            
            std::cout << "\nRun with -b for benchmark, -i for interactive mode."
                      << std::endl;
        }
        
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}
