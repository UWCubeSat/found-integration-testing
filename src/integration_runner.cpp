#include "integration_runner.hpp"

#include <iostream>
#include <fstream>
#include <cmath>
#include <stdexcept>

// FOUND headers
#include "common/style.hpp"
#include "common/spatial/camera.hpp"
#include "distance/distance.hpp"
#include "distance/edge.hpp"

// For image loading
#include <stb_image/stb_image.h>

namespace integration {

// ─────────────────────────────────────────────────────────────────────────────
// Edge detection + distance pipeline using FOUND's API
// ─────────────────────────────────────────────────────────────────────────────

RunResult run_pipeline(const std::string& image_path,
                       const CameraConfig& camera,
                       double ground_truth_m) {
    RunResult r;
    r.ground_truth_m = ground_truth_m;

    // Check image exists
    FILE* probe = fopen(image_path.c_str(), "rb");
    if (!probe) {
        r.error_message = "Image file not found: " + image_path;
        return r;
    }
    fclose(probe);

    try {
        // Load image using stb_image
        int width, height, channels;
        unsigned char* data = stbi_load(image_path.c_str(), &width, &height, &channels, 0);
        
        if (!data) {
            r.error_message = "Could not load image: " + image_path;
            return r;
        }

        // Create FOUND Image struct
        found::Image image{width, height, channels, data};

        // Create edge detector (mimicking minimalSEDA from FOUND's tests)
        // Parameters: threshold=10, border_thickness=1, offset=0
        found::SimpleEdgeDetectionAlgorithm edge_detector(10, 1, 0);
        
        // Run edge detection
        found::Points edges = edge_detector.Run(image);
        stbi_image_free(data);

        r.num_edges = static_cast<int>(edges.size());

        if (edges.empty()) {
            r.error_message = "No edges detected";
            return r;
        }

        // Create Camera (from FOUND's distance tests)
        found::Camera cam(camera.focal_length, camera.pixel_size, width, height);

        // Create distance algorithm (parameters from FOUND's integration tests)
        constexpr double RADIUS_OF_EARTH = 6378137.0;
        found::IterativeSphericalDistanceDeterminationAlgorithm algo(
            RADIUS_OF_EARTH,
            std::move(cam),
            2,      // iterations
            1,      // refreshes
            10,     // distance tolerance
            1.1,    // discriminator ratio
            2,      // PDF order
            4       // radius loss order
        );

        // Run distance determination
        found::PositionVector pos = algo.Run(edges);

        // Extract distance (magnitude of position vector)
        r.distance_m = std::sqrt(pos.x * pos.x + pos.y * pos.y + pos.z * pos.z);
        r.altitude_m = r.distance_m - RADIUS_OF_EARTH;
        r.error_m = std::abs(r.distance_m - ground_truth_m);
        r.error_percent = (r.error_m / ground_truth_m) * 100.0;
        r.success = true;

    } catch (const std::exception& e) {
        r.error_message = e.what();
    }

    return r;
}

// ─────────────────────────────────────────────────────────────────────────────
// Output
// ─────────────────────────────────────────────────────────────────────────────

void print_result(const RunResult& r) {
    if (!r.success) {
        std::cout << "[integration] FAILED: " << r.error_message << "\n";
        return;
    }
    std::cout << "[integration] edges:        " << r.num_edges              << "\n"
              << "[integration] distance:     " << r.distance_m / 1e6
                                                 << " Mm  ("
                                                 << r.altitude_m / 1e3
                                                 << " km alt)\n"
              << "[integration] ground truth: " << r.ground_truth_m / 1e6  << " Mm\n"
              << "[integration] error:        " << r.error_m / 1e3
                                                 << " km  ("
                                                 << r.error_percent         << "%)\n";
}

void write_result_json(const RunResult& r, const std::string& path) {
    std::ofstream f(path);
    if (!f) throw std::runtime_error("Cannot write: " + path);

    f << "{\n"
      << "  \"success\": "       << (r.success ? "true" : "false") << ",\n";

    if (!r.success) {
        f << "  \"error\": \""   << r.error_message << "\"\n}\n";
        return;
    }

    f << "  \"num_edges\": "     << r.num_edges                    << ",\n"
      << "  \"distance_m\": "    << r.distance_m                   << ",\n"
      << "  \"altitude_m\": "    << r.altitude_m                   << ",\n"
      << "  \"ground_truth_m\": "<< r.ground_truth_m               << ",\n"
      << "  \"error_m\": "       << r.error_m                      << ",\n"
      << "  \"error_percent\": " << r.error_percent                 << "\n"
      << "}\n";
}

} // namespace integration