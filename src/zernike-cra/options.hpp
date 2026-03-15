// =============================================================================
// options — CLI and pipeline parameters for zernike-cra runner
//
// Minimal parameter set: image path, camera, principle axes (spheroid a,b,c),
// orientation (quaternion), edge/distance params. Mirrors plan (Zernike+
// InertialSymmetry, SpheroidDistanceDeterminationAlgorithm).
// =============================================================================

#pragma once

#include <string>

namespace pipeline {

struct PipelineOptions {
    // I/O
    std::string image_path;
    std::string output_file;

    // Camera (focal length, pixel size; resolution from image)
    double focal_length = 85e-3;
    double pixel_size   = 1.0;

    // Spheroid principle axes a, b, c (meters). WGS84 default.
    double principle_axis_a = 6378137.0;
    double principle_axis_b = 6378137.0;
    double principle_axis_c = 6356752.31424518;

    // Orientation: quaternion (real, i, j, k) = (w, x, y, z). Identity when not set.
    double quat_w = 1.0;
    double quat_x = 0.0;
    double quat_y = 0.0;
    double quat_z = 0.0;
    bool   use_quaternion = false;

    // InertialSymmetryEdgeDetectionAlgorithm
    unsigned char gray_threshold = 10;
    int           line_count     = 360;
    double        line_epsilon   = 1e-6;
    int           mask           = 1;   // or mask type
    double        sparseness     = 1.0;

    // ZernikeEdgeDetectionAlgorithm
    int    window_size     = 7;
    double transition_width = 1.66;
};

// Returns true if parsing succeeded and options are valid (e.g. image_path set).
bool ParseOptions(int argc, char* argv[], PipelineOptions* out);

// Print usage to stdout.
void Usage(const char* prog);

}  // namespace pipeline
