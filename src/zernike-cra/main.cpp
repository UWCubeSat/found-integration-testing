// =============================================================================
// zernike-cra main — Multi-mode pipeline (edge | distance | full)
//
// Modes (--pipeline):
//   edge    — Input: --image. Output: lines "x y" (edge points).
//   distance — Input: --edges-file, --width, --height, camera/axes/quat. Output: "POSITION x y z".
//   full    — Input: --image, camera/axes/quat. Output: "POSITION x y z".
// =============================================================================

#include "options.hpp"

#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>

#include "common/decimal.hpp"
#include "common/pipeline/pipelines.hpp"
#include "common/style.hpp"
#include "common/spatial/attitude-utils.hpp"
#include "common/spatial/camera.hpp"
#include "distance/distance.hpp"
#include "distance/vectorize.hpp"
#include "distance/edge.hpp"
#include <stb_image/stb_image.h>

namespace {

void write_position_line(double x, double y, double z, std::ostream& out) {
    out << "POSITION " << x << " " << y << " " << z << "\n";
}

/** Load Points from file with one "x y" per line. */
found::Points load_points_from_file(const std::string& path) {
    std::ifstream f(path);
    if (!f) {
        std::cerr << "Failed to open edges file: " << path << "\n";
        return {};
    }
    found::Points points;
    std::string line;
    while (std::getline(f, line)) {
        double x = 0, y = 0;
        std::istringstream ss(line);
        if (ss >> x >> y)
            points.push_back(found::Vec2(DECIMAL(x), DECIMAL(y)));
    }
    return points;
}

/** Build regression function for distance stage from CLI options. nullptr = use TLS. */
found::RegressionFunc make_regression(
    const pipeline::PipelineOptions& opts) {
    using found::MatXX;
    using found::OLS;
    using found::RANSAC;
    using found::Ridge;
    using found::TLS;
    using found::VecX;
    switch (opts.regression) {
        case pipeline::RegressionKind::kTls:
            return nullptr;
        case pipeline::RegressionKind::kOls:
            return [](const MatXX& data) { return OLS(data); };
        case pipeline::RegressionKind::kRidge:
            return [lambda = opts.ridge_lambda](const MatXX& data) {
                return Ridge(data, lambda);
            };
        case pipeline::RegressionKind::kRansac:
            return [thr = opts.ransac_residual_threshold,
                    maxit = opts.ransac_max_iterations,
                    minsamp = opts.ransac_min_samples](const MatXX& data) {
                return RANSAC(data, thr, maxit,
                              static_cast<Eigen::Index>(minsamp));
            };
        default:
            return nullptr;
    }
}

}  // namespace

int main(int argc, char* argv[]) {
    pipeline::PipelineOptions opts;
    if (!pipeline::ParseOptions(argc, argv, &opts)) {
        return pipeline::g_help_requested ? 0 : 1;
    }

    using found::PositionVector;
    using found::Camera;
    using found::Points;

    found::Quaternion orientation(
        DECIMAL(opts.quat_w),
        DECIMAL(opts.quat_x),
        DECIMAL(opts.quat_y),
        DECIMAL(opts.quat_z));
    found::Vec3 principle_axes(
        DECIMAL(opts.principle_axis_a),
        DECIMAL(opts.principle_axis_b),
        DECIMAL(opts.principle_axis_c));

    // -------------------------------------------------------------------------
    // Pipeline: edge only — image -> edge points (stdout "x y" per line)
    // -------------------------------------------------------------------------
    if (opts.pipeline_mode == pipeline::PipelineMode::kEdge) {
        int width = 0, height = 0, channels = 0;
        unsigned char* data =
            stbi_load(opts.image_path.c_str(), &width, &height, &channels, 0);
        if (!data) {
            std::cerr << "Failed to load image: " << opts.image_path << "\n";
            return 1;
        }
        found::Image image{width, height, channels, data};
        decimal sobel_high =
            DECIMAL(opts.gray_threshold) / DECIMAL(255.0);
        auto sobel_edge_algo =
            std::make_unique<found::SobelEdgeDetectionAlgorithm>(sobel_high);
        found::ZernikeEdgeDetectionAlgorithm edge_algo(
            std::move(sobel_edge_algo), opts.window_size,
            DECIMAL(opts.transition_width));
        Points points = edge_algo.Run(image);
        stbi_image_free(data);
        std::ostream* out = &std::cout;
        std::ofstream ofile;
        if (!opts.output_file.empty()) {
            ofile.open(opts.output_file);
            if (ofile) out = &ofile;
        }
        for (const found::Vec2& p : points)
            *out << static_cast<double>(p.x()) << " "
                 << static_cast<double>(p.y()) << "\n";
        return 0;
    }

    // -------------------------------------------------------------------------
    // Pipeline: distance only — edges file + camera/axes/quat -> POSITION
    // -------------------------------------------------------------------------
    if (opts.pipeline_mode == pipeline::PipelineMode::kDistance) {
        Points points = load_points_from_file(opts.edges_file);
        if (points.size() < 3) {
            std::cerr << "Need at least 3 edge points; got " << points.size()
                      << "\n";
            return 1;
        }
        found::Camera cam(
            DECIMAL(opts.focal_length),
            DECIMAL(opts.pixel_size),
            opts.image_width,
            opts.image_height);
        found::SpheroidDistanceDeterminationAlgorithm distance_algo(
            std::move(cam), principle_axes, orientation.conjugate(),
            make_regression(opts));
        found::LOSTVectorGenerationAlgorithm vector_algo(orientation);
        found::SequentialPipeline<found::Points, PositionVector, 2> pipeline;
        pipeline.AddStage(distance_algo).Complete(vector_algo);
        PositionVector pos = pipeline.Run(points);
        double x = static_cast<double>(pos.x());
        double y = static_cast<double>(pos.y());
        double z = static_cast<double>(pos.z());
        write_position_line(x, y, z, std::cout);
        if (!opts.output_file.empty()) {
            std::ofstream f(opts.output_file);
            if (f) write_position_line(x, y, z, f);
        }
        return 0;
    }

    // -------------------------------------------------------------------------
    // Pipeline: full — image -> edge -> distance -> POSITION
    // -------------------------------------------------------------------------
    int width = 0, height = 0, channels = 0;
    unsigned char* data =
        stbi_load(opts.image_path.c_str(), &width, &height, &channels, 0);
    if (!data) {
        std::cerr << "Failed to load image: " << opts.image_path << "\n";
        return 1;
    }
    found::Image image{width, height, channels, data};
    decimal sobel_high = DECIMAL(opts.gray_threshold) / DECIMAL(255.0);
    auto sobel_edge_algo =
        std::make_unique<found::SobelEdgeDetectionAlgorithm>(sobel_high);
    found::ZernikeEdgeDetectionAlgorithm edge_algo(
        std::move(sobel_edge_algo), opts.window_size,
        DECIMAL(opts.transition_width));
    found::Camera cam(DECIMAL(opts.focal_length),
                     DECIMAL(opts.pixel_size), width, height);
    found::SpheroidDistanceDeterminationAlgorithm distance_algo(
        std::move(cam), principle_axes, orientation, make_regression(opts));
    found::SequentialPipeline<found::Image, PositionVector, 2> pipeline;
    pipeline.AddStage(edge_algo).Complete(distance_algo);
    PositionVector pos = pipeline.Run(image);

    stbi_image_free(data);
    double x = static_cast<double>(pos.x());
    double y = static_cast<double>(pos.y());
    double z = static_cast<double>(pos.z());

    write_position_line(x, y, z, std::cout);
    if (!opts.output_file.empty()) {
        std::ofstream f(opts.output_file);
        if (f) write_position_line(x, y, z, f);
    }
    return 0;
}
