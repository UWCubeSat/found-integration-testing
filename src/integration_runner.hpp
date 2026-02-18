#pragma once

#include <string>

namespace integration {

struct CameraConfig {
    double focal_length;  // meters
    double pixel_size;    // meters
};

struct RunResult {
    bool        success       = false;
    std::string error_message;

    // Edge detection
    int           num_edges   = 0;

    // Distance determination
    double distance_m         = 0.0;
    double altitude_m         = 0.0;

    // Error vs ground truth
    double ground_truth_m     = 0.0;
    double error_m            = 0.0;
    double error_percent      = 0.0;
};

// Main entry point - uses FOUND's edge detection + distance algorithm
RunResult run_pipeline(const std::string& image_path,
                       const CameraConfig& camera,
                       double ground_truth_m);

void print_result(const RunResult& r);
void write_result_json(const RunResult& r, const std::string& path);

} // namespace integration