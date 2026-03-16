// =============================================================================
// zernike-sobel — Edge-only: Zernike + Sobel, output edge points
//
// Runs the same edge detection as pipeline_runner (Sobel + Zernike) but does
// not run distance. Output: one line per edge point "x y" (image coordinates)
// to stdout. Used with plot_edges.py to visualize detected edges on the image.
// =============================================================================

#include "../zernike-cra/options.hpp"

#include <iostream>
#include <memory>

#include "common/decimal.hpp"
#include "common/style.hpp"
#include "distance/edge.hpp"
#include <stb_image/stb_image.h>

int main(int argc, char* argv[]) {
    pipeline::PipelineOptions opts;
    if (!pipeline::ParseOptions(argc, argv, &opts)) {
        return opts.image_path.empty() ? 1 : 0;
    }

    int width = 0, height = 0, channels = 0;
    unsigned char* data = stbi_load(opts.image_path.c_str(), &width, &height, &channels, 0);
    if (!data) {
        std::cerr << "Failed to load image: " << opts.image_path << "\n";
        return 1;
    }

    found::Image image{width, height, channels, data};

    decimal sobel_high = DECIMAL(opts.gray_threshold) / DECIMAL(255.0);
    auto sobel_edge_algo = std::make_unique<found::SobelEdgeDetectionAlgorithm>(sobel_high);
    found::ZernikeEdgeDetectionAlgorithm edge_algo(
        std::move(sobel_edge_algo), opts.window_size, DECIMAL(opts.transition_width));

    found::Points points = edge_algo.Run(image);
    stbi_image_free(data);

    for (const found::Vec2& p : points) {
        std::cout << static_cast<double>(p.x()) << " " << static_cast<double>(p.y()) << "\n";
    }
    return 0;
}
