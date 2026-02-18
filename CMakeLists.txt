cmake_minimum_required(VERSION 3.16)
project(found-integration CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# =============================================================================
# FOUND as a library via FetchContent
# =============================================================================

include(FetchContent)

FetchContent_Declare(
    found
    GIT_REPOSITORY https://github.com/UWCubeSat/found.git
    GIT_TAG        main
)

FetchContent_MakeAvailable(found)

# Get FOUND's source directory for includes
FetchContent_GetProperties(found SOURCE_DIR FOUND_SOURCE_DIR)

# =============================================================================
# Integration test executable
# =============================================================================

add_executable(found_integration
    src/main.cpp
    src/integration_runner.cpp
)

# Link against found_lib (FOUND's main library)
target_link_libraries(found_integration PRIVATE found::found_lib)

# Link against stb_image (FOUND builds this as a separate target)
# This gives us stbi_load() and stbi_image_free()
target_link_libraries(found_integration PRIVATE stb_image)

# Add FOUND's include directories for style.hpp, edge.hpp, etc.
target_include_directories(found_integration PRIVATE
    ${FOUND_SOURCE_DIR}
    ${FOUND_SOURCE_DIR}/src
)

set_target_properties(found_integration
    PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin
)
