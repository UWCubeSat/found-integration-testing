cmake_minimum_required(VERSION 3.21)  # match UWCubeSat/found
project(found-integration CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# =============================================================================
# Paths and target names (set at top for easy updates)
# =============================================================================

set(FOUND_INTEGRATION_ROOT ${CMAKE_CURRENT_SOURCE_DIR})
set(FOUND_INTEGRATION_BIN_DIR ${CMAKE_BINARY_DIR}/bin)

# FOUND dependency (FetchContent)
set(FOUND_GIT_REPOSITORY https://github.com/UWCubeSat/found.git)
set(FOUND_GIT_TAG        cram-sobel)

# Zernike-cra runner (Zernike + Sobel → Spheroid; options in options.hpp)
set(ZERNIKE_CRA_DIR ${FOUND_INTEGRATION_ROOT}/src/zernike-cra)
set(ZERNIKE_CRA_TARGET pipeline_runner)
set(ZERNIKE_CRA_SOURCES
    ${ZERNIKE_CRA_DIR}/main.cpp
    ${ZERNIKE_CRA_DIR}/options.cpp
)

# =============================================================================
# FOUND as a library via FetchContent
# =============================================================================

include(FetchContent)

FetchContent_Declare(
    found
    GIT_REPOSITORY ${FOUND_GIT_REPOSITORY}
    GIT_TAG        ${FOUND_GIT_TAG}
)

FetchContent_MakeAvailable(found)

FetchContent_GetProperties(found SOURCE_DIR FOUND_SOURCE_DIR)

# =============================================================================
# Point to the Custom Minimal OpenCV Build
# =============================================================================

# Tell CMake to look in your new build folder
set(OpenCV_DIR "${CMAKE_CURRENT_SOURCE_DIR}/opencv_build")

# Force static linking for the ARM binary
set(OpenCV_STATIC ON)

# Find the package
find_package(OpenCV REQUIRED)

message(STATUS "OpenCV library status:")
message(STATUS "    config: ${OpenCV_DIR}")
message(STATUS "    libraries: ${OpenCV_LIBRARIES}")
message(STATUS "    include path: ${OpenCV_INCLUDE_DIRS}")

# =============================================================================
# Zernike-cra pipeline runner
# =============================================================================

add_executable(${ZERNIKE_CRA_TARGET} ${ZERNIKE_CRA_SOURCES})

# 1. Direct Link to the static files we just built in Docker
set(OPENCV_STATIC_LIBS
    /src/build/opencv_install/lib/libopencv_imgproc.a
    /src/build/opencv_install/lib/libopencv_core.a
)

# 2. Add them to your target
target_link_libraries(${ZERNIKE_CRA_TARGET} PRIVATE 
    found::found_lib 
    stb_image 
    ${OPENCV_STATIC_LIBS}
    -lpthread -ldl -lm -lz # Required for static linking
)

target_include_directories(${ZERNIKE_CRA_TARGET} PRIVATE
    ${ZERNIKE_CRA_DIR}
    ${FOUND_SOURCE_DIR}
    ${FOUND_SOURCE_DIR}/src
    ${OpenCV_INCLUDE_DIRS}
)

set_target_properties(${ZERNIKE_CRA_TARGET}
    PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${FOUND_INTEGRATION_BIN_DIR}
)

# Edge-only runner (Zernike + Sobel → stdout "x y" per point; for plot_edges.py)
set(ZERNIKE_SOBEL_DIR ${FOUND_INTEGRATION_ROOT}/src/zernike-sobel)
set(EDGE_RUNNER_TARGET edge_runner)
add_executable(${EDGE_RUNNER_TARGET}
    ${ZERNIKE_SOBEL_DIR}/main.cpp
    ${ZERNIKE_CRA_DIR}/options.cpp
)
target_link_libraries(${EDGE_RUNNER_TARGET} PRIVATE found::found_lib stb_image)
target_include_directories(${EDGE_RUNNER_TARGET} PRIVATE
    ${ZERNIKE_CRA_DIR}
    ${ZERNIKE_SOBEL_DIR}
    ${FOUND_SOURCE_DIR}
    ${FOUND_SOURCE_DIR}/src
)
set_target_properties(${EDGE_RUNNER_TARGET}
    PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${FOUND_INTEGRATION_BIN_DIR}
)
