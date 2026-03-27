// =============================================================================
// options — CLI and pipeline parameters for zernike-cra runner
//
// Minimal parameter set: image path, camera, principle axes (spheroid a,b,c),
// orientation (quaternion), edge/distance params. Mirrors plan (Zernike+
// Sobel, SpheroidDistanceDeterminationAlgorithm).
// =============================================================================

#pragma once

#include <string>

namespace pipeline {

/** Pipeline mode: edge (image -> points), distance (points -> position), full (image -> position). */
enum class PipelineMode { kEdge, kDistance, kFull };

/** Regression used in the distance stage (spheroid fit). Default is TLS. */
enum class RegressionKind {
    kTls,    /** Total least squares (default). */
    kOls,    /** Ordinary least squares. */
    kRidge,  /** Ridge regression; requires --ridge-lambda. */
    kRansac, /** RANSAC; requires --ransac-residual-threshold and --ransac-max-iterations. */
};

struct PipelineOptions {
    // Pipeline selection
    PipelineMode pipeline_mode = PipelineMode::kFull;

    // I/O
    std::string image_path;
    std::string output_file;
    /** Path to edge points file for --pipeline distance (lines "x y"). */
    std::string edges_file;

    /** Image width/height for --pipeline distance (no image loaded). */
    int image_width  = 0;
    int image_height = 0;

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

    // SobelEdgeDetectionAlgorithm (gray_threshold 0–255 mapped to normalized [0,1] highThreshold)
    unsigned char gray_threshold = 10;
    int           line_count     = 360;
    double        line_epsilon   = 1e-6;
    int           mask           = 1;   // or mask type
    double        sparseness     = 1.0;

    // ZernikeEdgeDetectionAlgorithm (Sobel-only when zernike_refine is false)
    int    window_size     = 7;
    double transition_width = 1.66;
    /** If true, refine Sobel edges with Zernike moments; if false, use Sobel points only. */
    bool   zernike_refine  = true;

    // Distance stage regression (--regression tls|ols|ridge|ransac)
    RegressionKind regression = RegressionKind::kTls;
    // Ridge: --ridge-lambda
    double ridge_lambda = 1e-6;
    // RANSAC: --ransac-residual-threshold, --ransac-max-iterations, --ransac-min-samples
    double ransac_residual_threshold = 1e-4;
    int    ransac_max_iterations     = 100;
    int    ransac_min_samples        = 0;  // 0 = use (M-1) for unique OLS
};

/** If ParseOptions returns false, set to true when --help was requested. */
extern bool g_help_requested;

// Returns true if parsing succeeded and options are valid.
bool ParseOptions(int argc, char* argv[], PipelineOptions* out);

// Print usage to stdout.
void Usage(const char* prog);

}  // namespace pipeline
