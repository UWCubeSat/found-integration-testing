// =============================================================================
// options — implementation
// =============================================================================

#include "options.hpp"
#include <cstring>
#include <iostream>
#include <string>

namespace pipeline {

static void usage_text(const char* prog) {
    std::cout
        << "Usage: " << prog << " --image <path> [OPTIONS]\n\n"
        << "  --image            <path>   Input image (Earth limb)\n"
        << "  --output-file      <path>   Optional: write position line to file\n"
        << "  --focal-length     <m>      Camera focal length  (default: 85e-3)\n"
        << "  --pixel-size       <m>      Camera pixel size    (default: 20e-6)\n"
        << "  --principle-axes   <a> <b> <c>  Spheroid semi-axes (m). Default: WGS84\n"
        << "  --quaternion       <w> <x> <y> <z>  Orientation quaternion (real, i, j, k)\n"
        << "  --gray-threshold   <0-255>  Sobel high threshold, mapped to [0,1] (default: 10)\n"
        << "  --line-count       <n>      (unused with Sobel; kept for CLI compatibility)\n"
        << "  --line-epsilon     <e>      (unused with Sobel; kept for CLI compatibility)\n"
        << "  --window-size      <n>      Zernike window size (default: 7)\n"
        << "  --transition-width <w>      Zernike transition width (default: 1.66)\n"
        << "  --help                     Print this help\n";
}

void Usage(const char* prog) {
    usage_text(prog);
}

bool ParseOptions(int argc, char* argv[], PipelineOptions* out) {
    if (out == nullptr) return false;
    *out = PipelineOptions{};

    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--image") == 0 && i + 1 < argc) {
            out->image_path = argv[++i];
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
        } else if (std::strcmp(argv[i], "--help") == 0) {
            Usage(argv[0]);
            return false;  // caller should exit 0
        } else {
            std::cerr << "Unknown or missing value for: " << argv[i] << "\n";
            Usage(argv[0]);
            return false;
        }
    }

    return !out->image_path.empty();
}

}  // namespace pipeline
