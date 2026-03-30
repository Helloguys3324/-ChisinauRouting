cmake_minimum_required(VERSION 3.16)
project(ChisinauRoutingCore VERSION 1.0.0 LANGUAGES CXX)

# C++17 standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Build type
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Compiler flags
set(CMAKE_CXX_FLAGS_DEBUG "-g -O0 -DDEBUG")
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG")

# Options
option(BUILD_GRPC "Build gRPC server" ON)
option(BUILD_REST "Build REST API server" ON)
option(BUILD_TESTS "Build unit tests" OFF)

# Find required packages
find_package(Threads REQUIRED)

# PostgreSQL client library
find_package(PostgreSQL REQUIRED)

# For gRPC (optional)
if(BUILD_GRPC)
    find_package(Protobuf CONFIG REQUIRED)
    find_package(gRPC CONFIG REQUIRED)
    
    # Generate protobuf files
    set(PROTO_FILES ${CMAKE_SOURCE_DIR}/proto/routing.proto)
    
    add_library(routing_proto)
    target_link_libraries(routing_proto
        PUBLIC
            protobuf::libprotobuf
            gRPC::grpc++
    )
    
    protobuf_generate(TARGET routing_proto LANGUAGE cpp PROTOS ${PROTO_FILES})
    protobuf_generate(TARGET routing_proto LANGUAGE grpc PROTOS ${PROTO_FILES}
        PLUGIN "grpc_cpp_plugin"
        GENERATE_EXTENSIONS .grpc.pb.h .grpc.pb.cc)
endif()

# Source files
set(CORE_SOURCES
    src/graph.cpp
    src/astar.cpp
    src/weight_manager.cpp
    src/map_matcher.cpp
    src/db_loader.cpp
)

# Core library
add_library(routing_core STATIC ${CORE_SOURCES})
target_include_directories(routing_core
    PUBLIC
        ${CMAKE_SOURCE_DIR}/include
        ${PostgreSQL_INCLUDE_DIRS}
)
target_link_libraries(routing_core
    PUBLIC
        Threads::Threads
        ${PostgreSQL_LIBRARIES}
)

# Main executable
add_executable(chisinau_router src/main.cpp)
target_link_libraries(chisinau_router
    PRIVATE
        routing_core
)

# REST API server (using cpp-httplib, header-only)
if(BUILD_REST)
    add_executable(rest_server src/rest_server.cpp)
    target_link_libraries(rest_server
        PRIVATE
            routing_core
    )
    target_compile_definitions(rest_server PRIVATE CPPHTTPLIB_OPENSSL_SUPPORT)
endif()

# gRPC server
if(BUILD_GRPC)
    add_executable(grpc_server src/grpc_server.cpp)
    target_link_libraries(grpc_server
        PRIVATE
            routing_core
            routing_proto
            gRPC::grpc++
    )
endif()

# Installation
install(TARGETS chisinau_router DESTINATION bin)
install(TARGETS routing_core DESTINATION lib)
install(DIRECTORY include/ DESTINATION include)

# Print configuration summary
message(STATUS "")
message(STATUS "=== Chișinău Routing Core Configuration ===")
message(STATUS "Build type:     ${CMAKE_BUILD_TYPE}")
message(STATUS "gRPC support:   ${BUILD_GRPC}")
message(STATUS "REST support:   ${BUILD_REST}")
message(STATUS "PostgreSQL:     ${PostgreSQL_VERSION}")
message(STATUS "")
