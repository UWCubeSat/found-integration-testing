// =============================================================================
// options — implementation
// =============================================================================

#include "options.hpp"
#include <cstring>
#include <iostream>
#include <string>

namespace pipeline {

bool g_help_requested = false;

static void usage_text(const char* prog) {
    std::cout
        << "Usage: " << prog << " --pipeline <mode> [OPTIONS]\n\n"
        << "  --pipeline         <mode>   Pipeline: edge | distance | full (default: full)\n"
        << "  --image            <path>   Input image (required for edge/full)\n"
        << "  --edges-file       <path>   Edge points file for distance mode (lines \"x y\")\n"
        << "  --width            <n>      Image width for distance mode (no image)\n"
        << "  --height           <n>      Image height for distance mode (no image)\n"
        << "  --output-file      <path>   Optional: write position/edges to file\n"
        << "  --focal-length     <m>      Camera focal length  (default: 85e-3)\n"
        << "  --pixel-size       <m>      Camera pixel size    (default: 20e-6)\n"
        << "  --principle-axes   <a> <b> <c>  Spheroid semi-axes (m). Default: WGS84\n"
        << "  --quaternion       <w> <x> <y> <z>  Orientation quaternion (real, i, j, k)\n"
        << "  --gray-threshold   <0-255>  Sobel high threshold (default: 10)\n"
        << "  --window-size      <n>      Zernike window size (default: 7)\n"
        << "  --transition-width <w>      Zernike transition width (default: 1.66)\n"
        << "  --zernike-refine   <0|1>    1 = Sobel + Zernike (default), 0 = Sobel only\n"
        << "  --sobel-only                Shorthand for --zernike-refine 0 (edge/full)\n"
        << "  Distance stage regression (for distance/full pipeline):\n"
        << "  --regression       <alg>   tls | ols | ridge | ransac (default: tls)\n"
        << "  --ridge-lambda     <λ>     Ridge L2 regularization (for --regression ridge, default: 1e-6)\n"
        << "  --ransac-residual-threshold <τ>  Max residual for inlier (for --regression ransac, default: 1e-4)\n"
        << "  --ransac-max-iterations <n>       RANSAC trials (for --regression ransac, default: 100)\n"
        << "  --ransac-min-samples <n>          Min rows per trial (0 = M-1, default: 0)\n"
        << "  --help                     Print this help\n";
}

void Usage(const char* prog) {
    usage_text(prog);
}

static bool parse_pipeline_mode(const char* arg, PipelineOptions* out) {
    if (std::strcmp(arg, "edge") == 0) {
        out->pipeline_mode = PipelineMode::kEdge;
        return true;
    }
    if (std::strcmp(arg, "distance") == 0) {
        out->pipeline_mode = PipelineMode::kDistance;
        return true;
    }
    if (std::strcmp(arg, "full") == 0) {
        out->pipeline_mode = PipelineMode::kFull;
        return true;
    }
    return false;
}

static bool parse_regression_kind(const char* arg, PipelineOptions* out) {
    if (std::strcmp(arg, "tls") == 0) {
        out->regression = RegressionKind::kTls;
        return true;
    }
    if (std::strcmp(arg, "ols") == 0) {
        out->regression = RegressionKind::kOls;
        return true;
    }
    if (std::strcmp(arg, "ridge") == 0) {
        out->regression = RegressionKind::kRidge;
        return true;
    }
    if (std::strcmp(arg, "ransac") == 0) {
        out->regression = RegressionKind::kRansac;
        return true;
    }
    return false;
}

bool ParseOptions(int argc, char* argv[], PipelineOptions* out) {
    if (out == nullptr) return false;
    *out = PipelineOptions{};

    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--pipeline") == 0 && i + 1 < argc) {
            if (!parse_pipeline_mode(argv[++i], out)) {
                std::cerr << "Unknown --pipeline mode (use edge | distance | full)\n";
                Usage(argv[0]);
                return false;
            }
        } else if (std::strcmp(argv[i], "--image") == 0 && i + 1 < argc) {
            out->image_path = argv[++i];
        } else if (std::strcmp(argv[i], "--edges-file") == 0 && i + 1 < argc) {
            out->edges_file = argv[++i];
        } else if (std::strcmp(argv[i], "--width") == 0 && i + 1 < argc) {
            out->image_width = std::stoi(argv[++i]);
        } else if (std::strcmp(argv[i], "--height") == 0 && i + 1 < argc) {
            out->image_height = std::stoi(argv[++i]);
        } else if (std::strcmp(argv[i], "--output-file") == 0 && i + 1 < argc) {
            out->output_file = argv[++i];
        } else if (std::strcmp(argv[i], "--focal-length") == 0 && i + 1 < argc) {
            out->focal_length = std::stod(argv[++i]);
        } else if (std::strcmp(argv[i], "--pixel-size") == 0 && i + 1 < argc) {
            out->pixel_size = std::stod(argv[++i]);
        } else if (std::strcmp(argv[i], "--principle-axes") == 0 && i + 3 < argc) {
            out->principle_axis_a = std::stod(argv[++i]);
            out->principle_axis_b = std::stod(argv[++i]);
            out->principle_axis_c = std::stod(argv[++i]);
        } else if (std::strcmp(argv[i], "--quaternion") == 0 && i + 4 < argc) {
            out->quat_w = std::stod(argv[++i]);
            out->quat_x = std::stod(argv[++i]);
            out->quat_y = std::stod(argv[++i]);
            out->quat_z = std::stod(argv[++i]);
            out->use_quaternion = true;
        } else if (std::strcmp(argv[i], "--gray-threshold") == 0 && i + 1 < argc) {
            out->gray_threshold = static_cast<unsigned char>(std::stoi(argv[++i]));
        } else if (std::strcmp(argv[i], "--line-count") == 0 && i + 1 < argc) {
            out->line_count = std::stoi(argv[++i]);
        } else if (std::strcmp(argv[i], "--line-epsilon") == 0 && i + 1 < argc) {
            out->line_epsilon = std::stod(argv[++i]);
        } else if (std::strcmp(argv[i], "--window-size") == 0 && i + 1 < argc) {
            out->window_size = std::stoi(argv[++i]);
        } else if (std::strcmp(argv[i], "--transition-width") == 0 && i + 1 < argc) {
            out->transition_width = std::stod(argv[++i]);
        } else if (std::strcmp(argv[i], "--zernike-refine") == 0 && i + 1 < argc) {
            const char* v = argv[++i];
            if (std::strcmp(v, "0") == 0 || std::strcmp(v, "false") == 0) {
                out->zernike_refine = false;
            } else if (std::strcmp(v, "1") == 0 || std::strcmp(v, "true") == 0) {
                out->zernike_refine = true;
            } else {
                std::cerr << "Unknown --zernike-refine value (use 0|1|true|false)\n";
                Usage(argv[0]);
                return false;
            }
        } else if (std::strcmp(argv[i], "--sobel-only") == 0) {
            out->zernike_refine = false;
        } else if (std::strcmp(argv[i], "--regression") == 0 && i + 1 < argc) {
            if (!parse_regression_kind(argv[++i], out)) {
                std::cerr << "Unknown --regression (use tls | ols | ridge | ransac)\n";
                Usage(argv[0]);
                return false;
            }
        } else if (std::strcmp(argv[i], "--ridge-lambda") == 0 && i + 1 < argc) {
            out->ridge_lambda = std::stod(argv[++i]);
        } else if (std::strcmp(argv[i], "--ransac-residual-threshold") == 0 && i + 1 < argc) {
            out->ransac_residual_threshold = std::stod(argv[++i]);
        } else if (std::strcmp(argv[i], "--ransac-max-iterations") == 0 && i + 1 < argc) {
            out->ransac_max_iterations = std::stoi(argv[++i]);
        } else if (std::strcmp(argv[i], "--ransac-min-samples") == 0 && i + 1 < argc) {
            out->ransac_min_samples = std::stoi(argv[++i]);
        } else if (std::strcmp(argv[i], "--help") == 0) {
            g_help_requested = true;
            Usage(argv[0]);
            return false;  // caller should exit 0
        } else {
            std::cerr << "Unknown or missing value for: " << argv[i] << "\n";
            Usage(argv[0]);
            return false;
        }
    }

    // Validation by mode
    if (out->pipeline_mode == PipelineMode::kDistance) {
        if (out->edges_file.empty()) {
            std::cerr << "Pipeline mode 'distance' requires --edges-file\n";
            return false;
        }
        if (out->image_width <= 0 || out->image_height <= 0) {
            std::cerr << "Pipeline mode 'distance' requires --width and --height\n";
            return false;
        }
    }

    // Validation for regression options
    if (out->regression == RegressionKind::kRidge && out->ridge_lambda < 0) {
        std::cerr << "--ridge-lambda must be non-negative\n";
        return false;
    }
    if (out->regression == RegressionKind::kRansac) {
        if (out->ransac_max_iterations <= 0) {
            std::cerr << "--ransac-max-iterations must be positive\n";
            return false;
        }
        if (out->ransac_min_samples < 0) {
            std::cerr << "--ransac-min-samples must be non-negative\n";
            return false;
        }
    }

    return (out->pipeline_mode == PipelineMode::kDistance) || !out->image_path.empty();
}

}  // namespace pipeline
