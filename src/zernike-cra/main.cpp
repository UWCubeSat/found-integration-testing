// =============================================================================
// zernike-cra main — Zernike + InertialSymmetry → Spheroid → position (plan)
//
// Pipeline: edge (Zernike over InertialSymmetry) →
// SpheroidDistanceDeterminationAlgorithm → position via SequentialPipeline.
// Output: one parseable line "POSITION x y z"; optional --output-file.
// =============================================================================

#include "options.hpp"

#include <fstream>
#include <iostream>
#include <memory>

#include "common/decimal.hpp"
#include "common/pipeline/pipelines.hpp"
#include "common/style.hpp"
#include "common/spatial/camera.hpp"
#include "distance/distance.hpp"
#include "distance/edge.hpp"
#include <stb_image/stb_image.h>

namespace {

void write_position_line(double x, double y, double z, std::ostream& out) {
    out << "POSITION " << x << " " << y << " " << z << "\n";
}

}  // namespace

int main(int argc, char* argv[]) {
    pipeline::PipelineOptions opts;
    if (!pipeline::ParseOptions(argc, argv, &opts)) {
        return opts.image_path.empty() ? 1 : 0;  // 0 if --help
    }

    int width = 0, height = 0, channels = 0;
    unsigned char* data = stbi_load(opts.image_path.c_str(), &width, &height, &channels, 0);
    if (!data) {
        std::cerr << "Failed to load image: " << opts.image_path << "\n";
        return 1;
    }

    found::Image image{width, height, channels, data};
    using found::PositionVector;
    using found::Camera;

    // Initialize the algorithms
    found::Quaternion orientation(
        DECIMAL(opts.quat_w),
        DECIMAL(opts.quat_x),
        DECIMAL(opts.quat_y),
        DECIMAL(opts.quat_z));
    // Empty mask => library uses default half-plane mask (0,0,0,0,1,1,1,1)
    Eigen::Matrix<decimal, Eigen::Dynamic, 1> empty_mask;
    auto inertial_edge_algo = std::make_unique<found::InertialSymmetryEdgeDetectionAlgorithm>(
        static_cast<uint8_t>(opts.gray_threshold), opts.line_count,
        DECIMAL(opts.line_epsilon), empty_mask,
        DECIMAL(opts.sparseness));
    found::ZernikeEdgeDetectionAlgorithm edge_algo(
        std::move(inertial_edge_algo), opts.window_size, DECIMAL(opts.transition_width));
    found::Camera cam(DECIMAL(opts.focal_length),
                     DECIMAL(opts.pixel_size), width, height);
    found::Vec3 principle_axes(
        DECIMAL(opts.principle_axis_a),
        DECIMAL(opts.principle_axis_b),
        DECIMAL(opts.principle_axis_c));
    found::SpheroidDistanceDeterminationAlgorithm distance_algo(
        std::move(cam), principle_axes, orientation);
    // Create the pipeline
    found::SequentialPipeline<found::Image, PositionVector, 2> pipeline;
    pipeline.AddStage(edge_algo).Complete(distance_algo);
    PositionVector pos = pipeline.Run(image);

    stbi_image_free(data);
    double x = static_cast<double>(pos.x());
    double y = static_cast<double>(pos.y());
    double z = static_cast<double>(pos.z());

    write_position_line(x, y, z, std::cout);
    // if (!opts.output_file.empty()) {
    //     std::ofstream f(opts.output_file);
    //     if (f) write_position_line(x, y, z, f);
    //     else   std::cerr << "Could not write to " << opts.output_file << "\n";
    // }
    return 0;
}
