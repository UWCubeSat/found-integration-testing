#!/usr/bin/env python3
"""
Comprehensive analysis: simulation grid, render each row to a limb image (limb /
found-tools render), run the full Found pipeline (edge detection → distance →
position output), and save results CSV plus all rendered images.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from scipy.spatial.transform import Rotation as R

from limb.simulation.analysis.metrics import apparent_radius_pixels
from limb.simulation.metadata.orchestrate import (
    _calculate_conic_coeffs,
    _row_to_pose,
    _setup_simulation,
)

POSITION_LINE_RE = re.compile(
    r"POSITION\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)"
)

QUATERNION_NOISE_SIGMA_RAD_DEFAULT = (1.0 / 3.0) * (np.pi / (180.0 * 3600.0))

SIMULATION_SECTION_RE = re.compile(r"^\[\s*([^\]]+)\s*\]$")

# limb.simulation.render.conic.process_simulation / _apply_noise_pipeline
RENDER_NOISE_TOP_KEYS = frozenset(
    {"gaussian", "stars", "discretization", "motion_blur", "dead_pixels"}
)


def _load_simulation_config(file_path: Path, simulation_name: str) -> dict[str, str]:
    config: dict[str, str] = {}
    current: str | None = None
    with open(file_path, "r") as f:
        for raw in f:
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            m = SIMULATION_SECTION_RE.match(line)
            if m:
                current = m.group(1).strip()
                continue
            if current != simulation_name:
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                config[key.strip()] = val.strip()
    return config


def _apply_simulation_config(args: argparse.Namespace, config: dict[str, str]) -> None:
    def flist(s: str) -> list[float]:
        return [float(x) for x in s.split()]

    def ilist(s: str) -> list[int]:
        return [int(x) for x in s.split()]

    def f3(s: str) -> tuple[float, float, float]:
        a = flist(s)
        if len(a) != 3:
            raise ValueError(f"semi_axes must have 3 values, got {len(a)}")
        return (a[0], a[1], a[2])

    def pair2f(s: str) -> tuple[float, float]:
        a = flist(s)
        if len(a) != 2:
            raise ValueError(f"expected two floats, got {len(a)}")
        return (a[0], a[1])

    key_handlers: dict[str, Callable[[str], None]] = {
        "semi_axes": lambda v: setattr(args, "semi_axes", f3(v)),
        "fovs": lambda v: setattr(args, "fovs", flist(v)),
        "resolutions": lambda v: setattr(args, "resolutions", ilist(v)),
        "distances": lambda v: setattr(args, "distances", flist(v)),
        "num_earth_points": lambda v: setattr(args, "num_earth_points", int(v)),
        "num_positions_per_point": lambda v: setattr(args, "num_positions_per_point", int(v)),
        "num_spins_per_position": lambda v: setattr(args, "num_spins_per_position", int(v)),
        "num_radials_per_spin": lambda v: setattr(args, "num_radials_per_spin", int(v)),
        "regression": lambda v: setattr(args, "regression", v.strip().lower()),
        "ridge_lambda": lambda v: setattr(args, "ridge_lambda", float(v)),
        "ransac_residual_threshold": lambda v: setattr(args, "ransac_residual_threshold", float(v)),
        "ransac_max_iterations": lambda v: setattr(args, "ransac_max_iterations", int(v)),
        "ransac_min_samples": lambda v: setattr(args, "ransac_min_samples", int(v)),
        "quaternion_noise_sigma_rad": lambda v: setattr(
            args, "quaternion_noise_sigma_rad", float(v)
        ),
        "edge_decimals": lambda v: setattr(args, "edge_decimals", int(v)),
        "render_sigma": lambda v: setattr(args, "render_sigma", float(v)),
        "render_batch_size": lambda v: setattr(args, "render_batch_size", int(v)),
        "gray_threshold": lambda v: setattr(args, "gray_threshold", int(v)),
        "window_size": lambda v: setattr(args, "window_size", int(v)),
        "transition_width": lambda v: setattr(args, "transition_width", float(v)),
    }
    truth = lambda s: s.strip().lower() in ("1", "true", "yes")
    key_handlers.update(
        {
            "time_pipeline": lambda v: setattr(args, "time_pipeline", truth(v)),
            "valgrind": lambda v: setattr(args, "valgrind", truth(v)),
            "noise_gaussian": lambda v: setattr(args, "noise_gaussian", pair2f(v)),
            "noise_stars": lambda v: setattr(args, "noise_stars", float(v)),
            "noise_dead_pixels": lambda v: setattr(args, "noise_dead_pixels", pair2f(v)),
            "noise_discretization": lambda v: setattr(args, "noise_discretization", int(v)),
            "noise_motion_blur": lambda v: setattr(args, "noise_motion_blur", int(v)),
            "noise_config_json": lambda v: setattr(args, "noise_config_json", Path(v.strip())),
        }
    )
    for key, val in config.items():
        if key in key_handlers:
            key_handlers[key](val)


def perturb_quaternion_wxyz(
    qw: float,
    qx: float,
    qy: float,
    qz: float,
    sigma_rad: float,
    rng: np.random.Generator,
) -> tuple[float, float, float, float]:
    """
    Same as scripts/distance/simulation.py: small attitude noise via rotation vector
    θ_i ~ N(0, σ²), composed with body quaternion (SciPy xyzw internally; returns w,x,y,z).
    """
    if sigma_rad <= 0.0:
        return (qw, qx, qy, qz)
    q_xyzw = np.array([qx, qy, qz, qw], dtype=np.float64)
    n = np.linalg.norm(q_xyzw)
    if n <= 0.0:
        return (qw, qx, qy, qz)
    q_xyzw /= n
    theta = rng.normal(0.0, sigma_rad, size=3)
    r_orig = R.from_quat(q_xyzw)
    r_delta = R.from_rotvec(theta)
    qn = (r_orig * r_delta).as_quat()
    qx2, qy2, qz2, qw2 = float(qn[0]), float(qn[1]), float(qn[2]), float(qn[3])
    return (qw2, qx2, qy2, qz2)


def _parse_position_stdout(stdout: str) -> dict:
    for line in stdout.splitlines():
        m = POSITION_LINE_RE.match(line.strip())
        if m:
            return {
                "success": True,
                "out_pos_x": float(m.group(1)),
                "out_pos_y": float(m.group(2)),
                "out_pos_z": float(m.group(3)),
            }
    return {"success": False}


def build_render_noise_config(args: argparse.Namespace) -> dict | None:
    """Build ``noise_config`` for ``limb.simulation.render.conic.process_simulation``.

    Order in the renderer: gaussian → stars → discretization → motion_blur → dead_pixels.

    If ``--noise-config-json`` is set, that object is loaded first; any CLI or
    ``simulations.txt`` noise_* settings then override the matching top-level keys.
    """
    cfg: dict[str, dict] = {}
    jp = getattr(args, "noise_config_json", None)
    if jp is not None:
        path = Path(jp)
        if not path.is_file():
            raise FileNotFoundError(f"noise config JSON not found: {path}")
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise ValueError("noise config JSON must be a JSON object at the root")
        for k, v in loaded.items():
            if k not in RENDER_NOISE_TOP_KEYS:
                raise ValueError(
                    f"unknown render noise key {k!r}; allowed: {sorted(RENDER_NOISE_TOP_KEYS)}"
                )
            if not isinstance(v, dict):
                raise ValueError(f"render noise {k!r} must be a JSON object")
            cfg[k] = dict(v)
    if getattr(args, "noise_gaussian", None) is not None:
        ng = args.noise_gaussian
        cfg["gaussian"] = {"mean": float(ng[0]), "sigma": float(ng[1])}
    if getattr(args, "noise_stars", None) is not None:
        cfg["stars"] = {"prob": float(args.noise_stars)}
    if getattr(args, "noise_dead_pixels", None) is not None:
        dp = args.noise_dead_pixels
        cfg["dead_pixels"] = {
            "salt_prob": float(dp[0]),
            "pepper_prob": float(dp[1]),
        }
    if getattr(args, "noise_discretization", None) is not None:
        cfg["discretization"] = {"levels": int(args.noise_discretization)}
    if getattr(args, "noise_motion_blur", None) is not None:
        cfg["motion_blur"] = {"kernel_size": int(args.noise_motion_blur)}
    return cfg if cfg else None


def _validate_render_options(args: argparse.Namespace) -> None:
    """Subset of limb.simulation.main._validate_args for batch render."""
    if args.render_batch_size < 1:
        raise ValueError("--render-batch-size must be >= 1.")
    if args.render_sigma < 0:
        raise ValueError("--render-sigma must be >= 0.")
    if getattr(args, "noise_stars", None) is not None and (
        args.noise_stars < 0 or args.noise_stars > 1
    ):
        raise ValueError("--noise-stars must be in [0, 1].")
    if getattr(args, "noise_discretization", None) is not None and args.noise_discretization < 1:
        raise ValueError("--noise-discretization must be >= 1.")
    if getattr(args, "noise_motion_blur", None) is not None and (
        args.noise_motion_blur < 1 or args.noise_motion_blur % 2 == 0
    ):
        raise ValueError("--noise-motion-blur must be odd and >= 1.")


def render_limb_images_like_simulation_main(
    df: pd.DataFrame,
    output_folder: Path,
    *,
    sigma: float,
    batch_size: int,
    noise_config: dict | None = None,
) -> None:
    """Match limb.simulation.main: _calculate_conic_coeffs + render_conic.process_simulation by resolution."""
    from limb.simulation.render import conic as render_conic

    coeffs_by_resolution = _calculate_conic_coeffs(df)
    output_folder.mkdir(parents=True, exist_ok=True)
    for (width, height), (
        row_indices,
        coeffs,
        K,
        rc,
    ) in coeffs_by_resolution.items():
        render_conic.process_simulation(
            coeffs_nx6=render_conic.torch.from_numpy(coeffs.astype(np.float32)),
            width=width,
            height=height,
            output_folder=str(output_folder),
            K=render_conic.torch.from_numpy(K.astype(np.float32)),
            rc=render_conic.torch.from_numpy(rc.astype(np.float32)),
            batch_size=batch_size,
            sigma=sigma,
            row_indices=row_indices,
            noise_config=noise_config,
        )


def image_path_for_row_index(images_dir: Path, idx: int) -> Path:
    return images_dir / f"img_{int(idx):06d}.png"


def _append_quaternion_cli_args(
    cmd: list[str],
    row: pd.Series,
    quaternion_wxyz: tuple[float, float, float, float] | None,
) -> None:
    """Mirror scripts/distance/simulation._build_distance_cmd quaternion handling.

    Passes ``--quaternion w x y z`` (real, i, j, k). The binary uses this quaternion
    differently by mode: ``--pipeline distance`` conjugates internally for the
    distance stage; ``--pipeline full`` uses it without that conjugation
    (see src/zernike-cra/main.cpp). This script runs ``full``, so the rendered
    image (true attitude from row qw,qx,qy,qz) is paired with the noisy quaternion
    passed here — same tuple layout as the distance simulation would pass.
    """
    if quaternion_wxyz is not None:
        qw, qx, qy, qz = quaternion_wxyz
        cmd += ["--quaternion", str(float(qw)), str(float(qx)), str(float(qy)), str(float(qz))]
        return
    qw, qx, qy, qz = row.get("qw"), row.get("qx"), row.get("qy"), row.get("qz")
    if pd.notna(qw) and pd.notna(qx) and pd.notna(qy) and pd.notna(qz):
        cmd += ["--quaternion", str(float(qw)), str(float(qx)), str(float(qy)), str(float(qz))]


def _build_full_pipeline_cmd(
    binary: Path,
    image_path: Path,
    row: pd.Series,
    *,
    regression: str,
    ridge_lambda: float,
    ransac_residual_threshold: float,
    ransac_max_iterations: int,
    ransac_min_samples: int,
    gray_threshold: int,
    window_size: int,
    transition_width: float,
    quaternion_wxyz: tuple[float, float, float, float] | None,
) -> list[str]:
    cmd = [
        str(binary),
        "--pipeline",
        "full",
        "--image",
        str(image_path),
        "--focal-length",
        str(float(row["cam_focal_length"])),
        "--pixel-size",
        str(float(row["cam_x_pixel_pitch"])),
        "--regression",
        regression,
        "--gray-threshold",
        str(int(gray_threshold)),
        "--window-size",
        str(int(window_size)),
        "--transition-width",
        str(float(transition_width)),
    ]
    if regression == "ridge":
        cmd += ["--ridge-lambda", str(ridge_lambda)]
    elif regression == "ransac":
        cmd += [
            "--ransac-residual-threshold",
            str(ransac_residual_threshold),
            "--ransac-max-iterations",
            str(ransac_max_iterations),
        ]
        if ransac_min_samples > 0:
            cmd += ["--ransac-min-samples", str(ransac_min_samples)]
    _append_quaternion_cli_args(cmd, row, quaternion_wxyz)
    a, b, c = row.get("shape_axis_a"), row.get("shape_axis_b"), row.get("shape_axis_c")
    if pd.notna(a) and pd.notna(b) and pd.notna(c):
        cmd += ["--principle-axes", str(float(a)), str(float(b)), str(float(c))]
    return cmd


def fill_pixel_metrics_lenient(df: pd.DataFrame) -> pd.DataFrame:
    """Like limb fill_pixel_metrics, but skip out_* when projection fails (e.g. behind camera)."""
    if "position_distance_error_m" not in df.columns:
        df["position_distance_error_m"] = np.nan
    for col in ("delta_x_centroid", "delta_y_centroid", "delta_r_apparent"):
        if col not in df.columns:
            df[col] = np.nan

    for idx, row in df.iterrows():
        camera, _, tpc, rc = _row_to_pose(row)
        radius = float(row["shape_axis_a"])
        camera_to_earth_origing = np.array([abs(rc[0]), -rc[1], -rc[2]], dtype=np.float64)
        px, py = camera.camera_to_pixel(camera_to_earth_origing)
        df.at[idx, "true_x_centroid"] = px
        df.at[idx, "true_y_centroid"] = py
        df.at[idx, "true_r_apparent"] = apparent_radius_pixels(rc, radius, camera)

        out_x, out_y, out_z = row.get("out_pos_x"), row.get("out_pos_y"), row.get("out_pos_z")
        if pd.notna(out_x) and pd.notna(out_y) and pd.notna(out_z):
            out_vec = np.array(
                [float(out_x), float(out_y), float(out_z)],
                dtype=np.float64,
            )
            rc_out = np.ravel(np.asarray(tpc @ out_vec, dtype=np.float64))
            camera_to_earth_origing_out = np.array(
                [abs(rc_out[0]), -rc_out[1], -rc_out[2]],
                dtype=np.float64,
            )
            try:
                ox, oy = camera.camera_to_pixel(camera_to_earth_origing_out)
            except AssertionError:
                df.at[idx, "out_x_centroid"] = np.nan
                df.at[idx, "out_y_centroid"] = np.nan
                df.at[idx, "out_r_apparent"] = np.nan
                df.at[idx, "delta_x_centroid"] = np.nan
                df.at[idx, "delta_y_centroid"] = np.nan
                df.at[idx, "delta_r_apparent"] = np.nan
                df.at[idx, "position_distance_error_m"] = np.nan
                continue
            df.at[idx, "out_x_centroid"] = float(ox)
            df.at[idx, "out_y_centroid"] = float(oy)
            out_r = apparent_radius_pixels(rc_out, radius, camera)
            df.at[idx, "out_r_apparent"] = out_r
            df.at[idx, "delta_x_centroid"] = float(ox) - px
            df.at[idx, "delta_y_centroid"] = float(oy) - py
            df.at[idx, "delta_r_apparent"] = float(out_r) - df.at[idx, "true_r_apparent"]
            true_pos = np.array(
                [float(row["true_pos_x"]), float(row["true_pos_y"]), float(row["true_pos_z"])],
                dtype=np.float64,
            )
            df.at[idx, "position_distance_error_m"] = float(
                np.abs(np.linalg.norm(true_pos) - np.linalg.norm(out_vec))
            )

    return df


DEFAULT_VALGRIND_PREFIX = [
    "valgrind",
    "--error-exitcode=1",
    "--leak-check=full",
    "--errors-for-leak-kinds=definite,possible",
]


def run_full_pipeline(
    binary: Path,
    image_path: Path,
    row: pd.Series,
    *,
    regression: str = "tls",
    ridge_lambda: float = 1e-6,
    ransac_residual_threshold: float = 1e-4,
    ransac_max_iterations: int = 100,
    ransac_min_samples: int = 0,
    gray_threshold: int = 10,
    window_size: int = 7,
    transition_width: float = 1.66,
    quaternion_wxyz: tuple[float, float, float, float] | None = None,
    timeout_s: int = 120,
    time_pipeline: bool = False,
    valgrind: bool = False,
    valgrind_prefix: list[str] | None = None,
) -> tuple[bool, dict, int, float | None]:
    cmd = _build_full_pipeline_cmd(
        binary,
        image_path,
        row,
        regression=regression,
        ridge_lambda=ridge_lambda,
        ransac_residual_threshold=ransac_residual_threshold,
        ransac_max_iterations=ransac_max_iterations,
        ransac_min_samples=ransac_min_samples,
        gray_threshold=gray_threshold,
        window_size=window_size,
        transition_width=transition_width,
        quaternion_wxyz=quaternion_wxyz,
    )
    if valgrind:
        prefix = list(valgrind_prefix) if valgrind_prefix is not None else list(DEFAULT_VALGRIND_PREFIX)
        cmd = prefix + cmd
    elapsed: float | None = None
    t0 = time.perf_counter()
    proc: subprocess.CompletedProcess[str]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    finally:
        if time_pipeline:
            elapsed = time.perf_counter() - t0
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    result = _parse_position_stdout(out)
    ok = result.get("success", False) and proc.returncode == 0
    return ok, result, proc.returncode, elapsed


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Simulation grid → render limb images (found-tools) → full pipeline "
            "(edge + distance + position); write CSV and image directory."
        ),
    )
    p.add_argument(
        "--semi-axes",
        nargs=3,
        type=float,
        default=(6378137.0, 6378137.0, 6356752.31424518),
        metavar=("A", "B", "C"),
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
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path("comprehensive_results.csv"),
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
        help="Gaussian edge blur σ (pixels) for limb render; 0 is allowed (sharp edge, per found-tools).",
    )
    p.add_argument(
        "--render-batch-size",
        type=int,
        default=500,
        help="Images per render batch (same as limb.simulation.main --batch-size).",
    )
    p.add_argument(
        "--noise-gaussian",
        nargs=2,
        type=float,
        metavar=("MEAN", "SIGMA"),
        default=None,
        help="Post-render Gaussian noise in pixel units (see limb.simulation.main).",
    )
    p.add_argument(
        "--noise-stars",
        type=float,
        metavar="PROB",
        default=None,
        help="Salt noise fraction for stars (see limb.simulation.main).",
    )
    p.add_argument(
        "--noise-dead-pixels",
        nargs=2,
        type=float,
        metavar=("SALT", "PEPPER"),
        default=None,
        help="Salt-and-pepper after other noise (see limb.simulation.main).",
    )
    p.add_argument(
        "--noise-discretization",
        type=int,
        metavar="LEVELS",
        default=None,
        help="Quantize intensities to LEVELS levels per channel.",
    )
    p.add_argument(
        "--noise-motion-blur",
        type=int,
        metavar="KERNEL",
        default=None,
        help="Horizontal motion blur kernel size (odd, >= 1).",
    )
    p.add_argument(
        "--noise-salt-pepper",
        nargs=2,
        type=float,
        metavar=("SALT", "PEPPER"),
        dest="noise_dead_pixels",
        help="Alias for --noise-dead-pixels (matches limb.simulation.main).",
    )
    p.add_argument(
        "--noise-config-json",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "JSON object passed to render noise_config (keys: gaussian, stars, discretization, "
            "motion_blur, dead_pixels). CLI/file noise_* flags override those keys when set."
        ),
    )
    p.add_argument(
        "--gray-threshold",
        type=int,
        default=10,
        help="Sobel high threshold 0–255 for edge stage.",
    )
    p.add_argument("--window-size", type=int, default=7, help="Zernike window size.")
    p.add_argument(
        "--transition-width",
        type=float,
        default=1.66,
        help="Zernike transition width.",
    )
    p.add_argument(
        "--regression",
        type=str,
        default="tls",
        choices=("tls", "ols", "ridge", "ransac"),
    )
    p.add_argument("--ridge-lambda", type=float, default=1e-6)
    p.add_argument("--ransac-residual-threshold", type=float, default=1e-4)
    p.add_argument("--ransac-max-iterations", type=int, default=100)
    p.add_argument("--ransac-min-samples", type=int, default=0)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument(
        "--quaternion-noise-sigma-rad",
        type=float,
        default=QUATERNION_NOISE_SIGMA_RAD_DEFAULT,
    )
    p.add_argument(
        "--pipeline-timeout",
        type=int,
        default=120,
        help="Subprocess timeout (seconds) per row for pipeline_runner.",
    )
    p.add_argument(
        "--time-pipeline",
        action="store_true",
        help="Record wall time per pipeline invocation in runtime_sec (perf_counter).",
    )
    p.add_argument(
        "--valgrind",
        action="store_true",
        help=(
            "Run pipeline_runner under valgrind (memcheck). Implies much longer runs; "
            "timeout is scaled automatically unless you set --pipeline-timeout high enough."
        ),
    )
    p.add_argument(
        "--valgrind-arg",
        action="append",
        default=[],
        metavar="ARG",
        help="Extra valgrind argv after defaults (repeat for multiple args).",
    )
    p.add_argument(
        "--valgrind-timeout-factor",
        type=int,
        default=25,
        metavar="N",
        help="Multiply --pipeline-timeout by N when --valgrind is set (default: 25).",
    )
    p.add_argument(
        "--edge-decimals",
        type=int,
        default=0,
        help="Unused for full pipeline (reserved for config-file parity with distance scripts).",
    )
    p.add_argument("--simulation-file", type=Path, default=None)
    p.add_argument("--simulation-name", type=str, default=None)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.simulation_file is not None and args.simulation_name is not None:
        if not args.simulation_file.is_file():
            print(f"comprehensive: simulation file not found: {args.simulation_file}", file=sys.stderr)
            sys.exit(1)
        config = _load_simulation_config(args.simulation_file, args.simulation_name)
        if not config:
            print(
                f"comprehensive: no section [{args.simulation_name}] in {args.simulation_file}",
                file=sys.stderr,
            )
            sys.exit(1)
        _apply_simulation_config(args, config)

    if not args.binary.is_file():
        print(f"comprehensive: binary not found: {args.binary}", file=sys.stderr)
        sys.exit(1)

    if args.valgrind and shutil.which("valgrind") is None:
        print("comprehensive: --valgrind requires valgrind on PATH", file=sys.stderr)
        sys.exit(1)

    try:
        _validate_render_options(args)
    except ValueError as e:
        print(f"comprehensive: {e}", file=sys.stderr)
        sys.exit(1)

    images_dir = args.images_dir
    if images_dir is None:
        images_dir = args.output.parent / f"{args.output.stem}_images"

    try:
        from limb.simulation.render import conic as _render_conic_check  # noqa: F401

        _ = _render_conic_check.torch
    except ImportError as e:
        print(
            "comprehensive: rendering requires PyTorch (install torch for limb.simulation.render).",
            file=sys.stderr,
        )
        print(str(e), file=sys.stderr)
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
        f"comprehensive: rendering {n} images → {images_dir} "
        f"(batch like limb.simulation.main); full pipeline (binary={args.binary})"
    )

    rng = np.random.default_rng(args.seed)
    for col in ("noisy_qw", "noisy_qx", "noisy_qy", "noisy_qz"):
        df_simulation[col] = np.nan
    df_simulation["rendered_image"] = ""
    df_simulation["pipeline_returncode"] = np.nan
    if "runtime_sec" not in df_simulation.columns:
        df_simulation["runtime_sec"] = np.nan
    for col in ("out_pos_x", "out_pos_y", "out_pos_z"):
        df_simulation[col] = np.nan

    valgrind_prefix: list[str] | None = None
    if args.valgrind:
        valgrind_prefix = list(DEFAULT_VALGRIND_PREFIX)
        if args.valgrind_arg:
            valgrind_prefix.extend(args.valgrind_arg)

    pipeline_timeout = args.pipeline_timeout
    if args.valgrind:
        pipeline_timeout = max(1, int(args.pipeline_timeout * args.valgrind_timeout_factor))
        print(
            f"comprehensive: valgrind enabled → pipeline timeout {pipeline_timeout}s "
            f"({args.valgrind_timeout_factor}× {args.pipeline_timeout}s)",
            file=sys.stderr,
        )

    pipeline_quat: dict[int, tuple[float, float, float, float] | None] = {}
    for idx, row in df_simulation.iterrows():
        qw, qx, qy, qz = row.get("qw"), row.get("qx"), row.get("qy"), row.get("qz")
        quat_ok = pd.notna(qw) and pd.notna(qx) and pd.notna(qy) and pd.notna(qz)
        quaternion_wxyz: tuple[float, float, float, float] | None = None
        if quat_ok:
            nqw, nqx, nqy, nqz = perturb_quaternion_wxyz(
                float(qw),
                float(qx),
                float(qy),
                float(qz),
                float(args.quaternion_noise_sigma_rad),
                rng,
            )
            df_simulation.at[idx, "noisy_qw"] = nqw
            df_simulation.at[idx, "noisy_qx"] = nqx
            df_simulation.at[idx, "noisy_qy"] = nqy
            df_simulation.at[idx, "noisy_qz"] = nqz
            quaternion_wxyz = (nqw, nqx, nqy, nqz)
        pipeline_quat[int(idx)] = quaternion_wxyz

    if args.seed is not None:
        np.random.seed(args.seed)
    try:
        noise_config = build_render_noise_config(args)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"comprehensive: render noise config: {e}", file=sys.stderr)
        sys.exit(1)
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

        success, result, rc, elapsed = run_full_pipeline(
            args.binary,
            img_path,
            row,
            regression=args.regression,
            ridge_lambda=args.ridge_lambda,
            ransac_residual_threshold=args.ransac_residual_threshold,
            ransac_max_iterations=args.ransac_max_iterations,
            ransac_min_samples=args.ransac_min_samples,
            gray_threshold=args.gray_threshold,
            window_size=args.window_size,
            transition_width=args.transition_width,
            quaternion_wxyz=pipeline_quat[int(idx)],
            timeout_s=pipeline_timeout,
            time_pipeline=args.time_pipeline,
            valgrind=args.valgrind,
            valgrind_prefix=valgrind_prefix,
        )
        df_simulation.at[idx, "pipeline_returncode"] = int(rc)
        if args.time_pipeline and elapsed is not None:
            df_simulation.at[idx, "runtime_sec"] = float(elapsed)
        if success:
            df_simulation.at[idx, "out_pos_x"] = result["out_pos_x"]
            df_simulation.at[idx, "out_pos_y"] = result["out_pos_y"]
            df_simulation.at[idx, "out_pos_z"] = result["out_pos_z"]
        else:
            df_simulation.at[idx, "out_pos_x"] = np.nan
            df_simulation.at[idx, "out_pos_y"] = np.nan
            df_simulation.at[idx, "out_pos_z"] = np.nan

    df = fill_pixel_metrics_lenient(df_simulation)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=True)
    print(f"comprehensive: wrote {args.output} ({n} rows); images in {images_dir}")


if __name__ == "__main__":
    main()
