#!/usr/bin/env python3
"""
Edge analysis: same simulation grid as comprehensive/distance, render limb
images, run ``pipeline_runner --pipeline edge`` (Zernike + Sobel), and save
detected edge points, **geometry true edge points** (``limb`` ``points_from_row``),
and image paths to CSV.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from limb.simulation.analysis.metrics import fill_pixel_metrics
from limb.simulation.metadata.orchestrate import _setup_simulation, points_from_row

_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.comprehensive.simulation import (
    _apply_simulation_config,
    _load_simulation_config,
    _validate_render_options,
    build_render_noise_config,
    image_path_for_row_index,
    render_limb_images_like_simulation_main,
)
from scripts.debug_trouble_rows import run_edge_pipeline


def _edge_points_to_json(pts: np.ndarray) -> str:
    """Serialize (N,2) edge points as a JSON array of [x, y] pairs (CSV-safe)."""
    pts = np.asarray(pts, dtype=np.float64)
    pairs = [[float(pts[i, 0]), float(pts[i, 1])] for i in range(pts.shape[0])]
    return json.dumps(pairs, separators=(",", ":"))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Simulation grid → render limb images → edge pipeline "
            "(Zernike + Sobel); CSV includes rendered_image, true_edge_points_json, "
            "and edge_points_json."
        ),
    )
    p.add_argument(
        "--semi-axes",
        nargs=3,
        type=float,
        default=(6378137.0, 6378137.0, 6356752.31424518),
        metavar=("A", "B", "C"),
        help="Ellipsoid semi-axes a,b,c (m).",
    )
    p.add_argument("--fovs", nargs="+", type=float, default=[10.0], metavar="FOV")
    p.add_argument("--resolutions", nargs="+", type=int, default=[512], metavar="N")
    p.add_argument("--distances", nargs="+", type=float, default=[7e6], metavar="D")
    p.add_argument("--num-earth-points", type=int, default=1)
    p.add_argument("--num-positions-per-point", type=int, default=3)
    p.add_argument("--num-spins-per-position", type=int, default=4)
    p.add_argument("--num-radials-per-spin", type=int, default=2)
    p.add_argument(
        "--binary",
        type=Path,
        default=Path("build/bin/pipeline_runner"),
        help="Path to pipeline_runner (supports --pipeline edge).",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path("edge_results.csv"),
        help="Output CSV path.",
    )
    p.add_argument(
        "--images-dir",
        type=Path,
        default=None,
        help="Directory for rendered PNGs (default: <output_stem>_images next to --output).",
    )
    p.add_argument(
        "--render-sigma",
        type=float,
        default=0.5,
        help="Gaussian edge blur σ (pixels) for limb render.",
    )
    p.add_argument(
        "--render-batch-size",
        type=int,
        default=500,
        help="Images per render batch.",
    )
    p.add_argument(
        "--noise-gaussian",
        nargs=2,
        type=float,
        metavar=("MEAN", "SIGMA"),
        default=None,
    )
    p.add_argument("--noise-stars", type=float, metavar="PROB", default=None)
    p.add_argument(
        "--noise-dead-pixels",
        nargs=2,
        type=float,
        metavar=("SALT", "PEPPER"),
        default=None,
    )
    p.add_argument("--noise-discretization", type=int, metavar="LEVELS", default=None)
    p.add_argument("--noise-motion-blur", type=int, metavar="KERNEL", default=None)
    p.add_argument(
        "--noise-salt-pepper",
        nargs=2,
        type=float,
        metavar=("SALT", "PEPPER"),
        dest="noise_dead_pixels",
        help="Alias for --noise-dead-pixels.",
    )
    p.add_argument("--noise-config-json", type=Path, default=None, metavar="PATH")
    p.add_argument(
        "--gray-threshold",
        type=int,
        default=10,
        help="Sobel high threshold 0–255 for edge stage (see main.cpp kEdge).",
    )
    p.add_argument("--window-size", type=int, default=7, help="Zernike window size.")
    p.add_argument(
        "--transition-width",
        type=float,
        default=1.66,
        help="Zernike transition width.",
    )
    p.add_argument(
        "--sobel-only",
        action="store_true",
        help="Sobel edges only; skip Zernike (passes --sobel-only to pipeline_runner).",
    )
    p.add_argument(
        "--true-edge-decimals",
        type=int,
        default=10,
        metavar="N",
        help=(
            "Decimal places when rounding limb geometry edge points "
            "(points_from_row, no noise; see limb generate_edge_points truncate)."
        ),
    )
    p.add_argument("--seed", type=int, default=None, help="Random seed for render noise.")
    p.add_argument(
        "--pipeline-timeout",
        type=int,
        default=120,
        help="Subprocess timeout (seconds) per row for --pipeline edge.",
    )
    p.add_argument(
        "--time-pipeline",
        action="store_true",
        help="Record wall time per edge pipeline in runtime_sec.",
    )
    p.add_argument(
        "--simulation-file",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to simulations.txt; use with --simulation-name.",
    )
    p.add_argument(
        "--simulation-name",
        type=str,
        default=None,
        metavar="NAME",
        help="Section name in --simulation-file (e.g. baseline).",
    )
    args = p.parse_args()
    args.zernike_refine = True
    if args.simulation_file is not None and args.simulation_name is not None:
        if not args.simulation_file.is_file():
            print(f"edge_simulation: simulation file not found: {args.simulation_file}", file=sys.stderr)
            sys.exit(1)
        config = _load_simulation_config(args.simulation_file, args.simulation_name)
        if not config:
            print(
                f"edge_simulation: no section [{args.simulation_name}] in {args.simulation_file}",
                file=sys.stderr,
            )
            sys.exit(1)
        _apply_simulation_config(args, config)
        for k, v in config.items():
            if k == "true_edge_decimals":
                args.true_edge_decimals = int(v.strip())
    if args.sobel_only:
        args.zernike_refine = False
    return args


def main() -> None:
    args = parse_args()

    if not args.binary.is_file():
        print(f"edge_simulation: binary not found: {args.binary}", file=sys.stderr)
        sys.exit(1)
    if args.true_edge_decimals < 0:
        print("edge_simulation: --true-edge-decimals must be >= 0", file=sys.stderr)
        sys.exit(1)

    try:
        _validate_render_options(args)
    except ValueError as e:
        print(f"edge_simulation: {e}", file=sys.stderr)
        sys.exit(1)

    images_dir = args.images_dir
    if images_dir is None:
        images_dir = args.output.parent / f"{args.output.stem}_images"

    try:
        from limb.simulation.render import conic as _render_conic_check  # noqa: F401

        _ = _render_conic_check.torch
    except ImportError as e:
        print(
            "edge_simulation: rendering requires PyTorch (limb.simulation.render).",
            file=sys.stderr,
        )
        print(str(e), file=sys.stderr)
        sys.exit(1)

    try:
        noise_config = build_render_noise_config(args)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"edge_simulation: render noise config: {e}", file=sys.stderr)
        sys.exit(1)

    df_simulation = _setup_simulation(
        semi_axes=list(args.semi_axes),
        fovs=args.fovs,
        resolutions=args.resolutions,
        distances=args.distances,
        num_earth_points=args.num_earth_points,
        num_positions_per_point=args.num_positions_per_point,
        num_spins_per_position=args.num_spins_per_position,
        num_radials_per_spin=args.num_radials_per_spin,
    )

    n = len(df_simulation)
    print(
        f"edge_simulation: rendering {n} images → {images_dir}; "
        f"edge pipeline (binary={args.binary})"
    )

    df_simulation["rendered_image"] = ""
    df_simulation["true_edge_points_json"] = ""
    df_simulation["n_true_edge_points"] = 0
    df_simulation["edge_points_json"] = ""
    df_simulation["n_detected_edge_points"] = 0
    df_simulation["edge_pipeline_returncode"] = np.nan
    df_simulation["runtime_sec"] = np.nan

    if args.seed is not None:
        np.random.seed(args.seed)

    render_limb_images_like_simulation_main(
        df_simulation,
        images_dir,
        sigma=args.render_sigma,
        batch_size=args.render_batch_size,
        noise_config=noise_config,
    )

    for idx, row in df_simulation.iterrows():
        img_path = image_path_for_row_index(images_dir, int(idx))
        if not img_path.is_file():
            raise FileNotFoundError(f"expected rendered image missing: {img_path}")
        rel = img_path
        try:
            rel = img_path.relative_to(Path.cwd())
        except ValueError:
            pass
        df_simulation.at[idx, "rendered_image"] = str(rel)

        true_pts = np.asarray(
            points_from_row(
                row,
                gaussian_sigma=None,
                n_false_points=0,
                truncate=int(args.true_edge_decimals),
            ),
            dtype=np.float64,
        )
        df_simulation.at[idx, "true_edge_points_json"] = _edge_points_to_json(true_pts)
        df_simulation.at[idx, "n_true_edge_points"] = int(true_pts.shape[0])

        t0 = time.perf_counter()
        pts, _out, rc = run_edge_pipeline(
            args.binary,
            img_path,
            gray_threshold=args.gray_threshold,
            window_size=args.window_size,
            transition_width=args.transition_width,
            zernike_refine=args.zernike_refine,
            timeout_s=args.pipeline_timeout,
        )
        elapsed = time.perf_counter() - t0
        if args.time_pipeline:
            df_simulation.at[idx, "runtime_sec"] = float(elapsed)

        df_simulation.at[idx, "edge_points_json"] = _edge_points_to_json(pts)
        df_simulation.at[idx, "n_detected_edge_points"] = int(pts.shape[0])
        df_simulation.at[idx, "edge_pipeline_returncode"] = int(rc)

    df_simulation = fill_pixel_metrics(df_simulation)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df_simulation.to_csv(args.output, index=True)
    print(f"edge_simulation: wrote {args.output} ({n} rows); images in {images_dir}")


if __name__ == "__main__":
    main()
