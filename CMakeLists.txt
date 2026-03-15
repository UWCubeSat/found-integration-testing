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
set(FOUND_GIT_TAG        paper-cram-ah)

# Zernike-cra runner (Zernike + InertialSymmetry → Spheroid; options in options.hpp)
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
# Zernike-cra pipeline runner
# =============================================================================

add_executable(${ZERNIKE_CRA_TARGET} ${ZERNIKE_CRA_SOURCES})
target_link_libraries(${ZERNIKE_CRA_TARGET} PRIVATE found::found_lib stb_image)
target_include_directories(${ZERNIKE_CRA_TARGET} PRIVATE
    ${ZERNIKE_CRA_DIR}
    ${FOUND_SOURCE_DIR}
    ${FOUND_SOURCE_DIR}/src
)
set_target_properties(${ZERNIKE_CRA_TARGET}
    PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${FOUND_INTEGRATION_BIN_DIR}
)
