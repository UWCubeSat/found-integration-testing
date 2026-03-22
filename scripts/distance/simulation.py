#!/usr/bin/env python3
"""
CRA analysis: build simulation grid, generate noisy edge points per row,
run the distance pipeline (edges -> POSITION), and save results to CSV.
"""

from __future__ import annotations

import argparse
from typing import Callable
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial.transform import Rotation as R

from limb.simulation.metadata.orchestrate import _setup_simulation, points_from_row
from limb.simulation.edge.conic import add_point_noise
from limb.simulation.analysis.metrics import fill_pixel_metrics
from limb.utils._camera import Camera

POSITION_LINE_RE = re.compile(
    r"POSITION\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)"
)

# Per-axis Gaussian σ (radians) for quaternion rotation-vector noise when 3σ = 1 arcsecond:
# σ = (1/3) × (1/3600)° × (π/180).
QUATERNION_NOISE_SIGMA_RAD_DEFAULT = (1.0 / 3.0) * (np.pi / (180.0 * 3600.0))

# Section header in simulations.txt: [name]
SIMULATION_SECTION_RE = re.compile(r"^\[\s*([^\]]+)\s*\]$")


def _load_simulation_config(file_path: Path, simulation_name: str) -> dict[str, str]:
    """Parse simulations.txt; return key=value dict for the given [simulation_name] section."""
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
    """Overlay config from simulations.txt onto args (mutates args)."""
    def flist(s: str) -> list[float]:
        return [float(x) for x in s.split()]
    def ilist(s: str) -> list[int]:
        return [int(x) for x in s.split()]
    def f3(s: str) -> tuple[float, float, float]:
        a = flist(s)
        if len(a) != 3:
            raise ValueError(f"semi_axes must have 3 values, got {len(a)}")
        return (a[0], a[1], a[2])
    def truth(s: str) -> bool:
        return s.strip().lower() in ("1", "true", "yes")

    key_handlers: dict[str, Callable[[str], None]] = {
        "semi_axes": lambda v: setattr(args, "semi_axes", f3(v)),
        "fovs": lambda v: setattr(args, "fovs", flist(v)),
        "resolutions": lambda v: setattr(args, "resolutions", ilist(v)),
        "distances": lambda v: setattr(args, "distances", flist(v)),
        "num_earth_points": lambda v: setattr(args, "num_earth_points", int(v)),
        "num_positions_per_point": lambda v: setattr(args, "num_positions_per_point", int(v)),
        "num_spins_per_position": lambda v: setattr(args, "num_spins_per_position", int(v)),
        "num_radials_per_spin": lambda v: setattr(args, "num_radials_per_spin", int(v)),
        "atmosphere_blur": lambda v: setattr(args, "atmosphere_blur", float(v)),
        "false_points": lambda v: setattr(args, "n_false_points", int(v)),
        "conjugate_quaternion": lambda v: setattr(args, "conjugate_quaternion", truth(v)),
        "edge_decimals": lambda v: setattr(args, "edge_decimals", int(v)),
        "regression": lambda v: setattr(args, "regression", v.strip().lower()),
        "ridge_lambda": lambda v: setattr(args, "ridge_lambda", float(v)),
        "ransac_residual_threshold": lambda v: setattr(args, "ransac_residual_threshold", float(v)),
        "ransac_max_iterations": lambda v: setattr(args, "ransac_max_iterations", int(v)),
        "ransac_min_samples": lambda v: setattr(args, "ransac_min_samples", int(v)),
        "quaternion_noise_sigma_rad": lambda v: setattr(
            args, "quaternion_noise_sigma_rad", float(v)
        ),
    }
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
    Apply small isotropic attitude noise: rotation vector θ with θ_i ~ N(0, σ²),
    composed with the body quaternion (SciPy xyzw internally; returns w,x,y,z).
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
    """Parse 'POSITION x y z' from pipeline stdout."""
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


def _build_distance_cmd(
    binary: Path,
    edges_file: Path,
    row: pd.Series,
    *,
    regression: str = "tls",
    ridge_lambda: float = 1e-6,
    ransac_residual_threshold: float = 1e-4,
    ransac_max_iterations: int = 100,
    ransac_min_samples: int = 0,
    conjugate_quaternion: bool = False,
    quaternion_wxyz: tuple[float, float, float, float] | None = None,
) -> list[str]:
    """Build argv for --pipeline distance (edges file + camera/axes/quat + regression)."""
    w = int(row["cam_x_resolution"])
    h = int(row["cam_y_resolution"])
    cmd = [
        str(binary),
        "--pipeline", "distance",
        "--edges-file", str(edges_file),
        "--width", str(w),
        "--height", str(h),
        "--focal-length", str(float(row["cam_focal_length"])),
        "--pixel-size", str(float(row["cam_x_pixel_pitch"])),
        "--regression", regression,
    ]
    if regression == "ridge":
        cmd += ["--ridge-lambda", str(ridge_lambda)]
    elif regression == "ransac":
        cmd += [
            "--ransac-residual-threshold", str(ransac_residual_threshold),
            "--ransac-max-iterations", str(ransac_max_iterations),
        ]
        if ransac_min_samples > 0:
            cmd += ["--ransac-min-samples", str(ransac_min_samples)]
    if quaternion_wxyz is not None:
        qw, qx, qy, qz = quaternion_wxyz
        cmd += ["--quaternion", str(float(qw)), str(float(qx)), str(float(qy)), str(float(qz))]
    else:
        qw, qx, qy, qz = row.get("qw"), row.get("qx"), row.get("qy"), row.get("qz")
        if pd.notna(qw) and pd.notna(qx) and pd.notna(qy) and pd.notna(qz):
            cmd += ["--quaternion", str(float(qw)), str(float(qx)), str(float(qy)), str(float(qz))]
    a, b, c = row.get("shape_axis_a"), row.get("shape_axis_b"), row.get("shape_axis_c")
    if pd.notna(a) and pd.notna(b) and pd.notna(c):
        cmd += ["--principle-axes", str(float(a)), str(float(b)), str(float(c))]
    return cmd


def run_distance_pipeline(
    binary: Path,
    row: pd.Series,
    points_xy: np.ndarray,
    *,
    edge_decimals: int = 0,
    regression: str = "tls",
    ridge_lambda: float = 1e-6,
    ransac_residual_threshold: float = 1e-4,
    ransac_max_iterations: int = 100,
    ransac_min_samples: int = 0,
    quaternion_wxyz: tuple[float, float, float, float] | None = None,
) -> tuple[bool, dict]:
    """Write edge points to a temp file, run distance pipeline, return (success, result_dict)."""
    if points_xy.shape[0] < 3:
        return False, {"success": False}
    points_xy = np.asarray(points_xy, dtype=np.float64)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        delete=False,
    ) as f:
        for i in range(points_xy.shape[0]):
            x, y = float(points_xy[i, 0]), float(points_xy[i, 1])
            if edge_decimals > 0:
                f.write(f"{x:.{edge_decimals}f} {y:.{edge_decimals}f}\n")
            else:
                f.write(f"{x:.17g} {y:.17g}\n")
        path = Path(f.name)
    try:
        cmd = _build_distance_cmd(
            binary, path, row,
            regression=regression,
            ridge_lambda=ridge_lambda,
            ransac_residual_threshold=ransac_residual_threshold,
            ransac_max_iterations=ransac_max_iterations,
            ransac_min_samples=ransac_min_samples,
            quaternion_wxyz=quaternion_wxyz,
        )
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        result = _parse_position_stdout(out)
        result["success"] = result.get("success", False) and proc.returncode == 0
        return result.get("success", False), result
    finally:
        path.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="CRA analysis: simulation setup, noisy edge points, distance pipeline, save CSV.",
    )
    # Simulation grid (mirror limb_simulation / orchestrate)
    p.add_argument(
        "--semi-axes",
        nargs=3,
        type=float,
        default=(6378137.0, 6378137.0, 6356752.31424518),
        metavar=("A", "B", "C"),
        help="Ellipsoid semi-axes a,b,c (m).",
    )
    p.add_argument(
        "--fovs",
        nargs="+",
        type=float,
        default=[10.0],
        metavar="FOV",
        help="Field-of-view values (degrees).",
    )
    p.add_argument(
        "--resolutions",
        nargs="+",
        type=int,
        default=[512],
        metavar="N",
        help="Sensor resolutions (pixels, square).",
    )
    p.add_argument(
        "--distances",
        nargs="+",
        type=float,
        default=[7e6],
        metavar="D",
        help="Distances from ellipsoid center to satellite (m).",
    )
    p.add_argument("--num-earth-points", type=int, default=1)
    p.add_argument("--num-positions-per-point", type=int, default=3)
    p.add_argument("--num-spins-per-position", type=int, default=4)
    p.add_argument("--num-radials-per-spin", type=int, default=2)
    # Point noise (for add_point_noise)
    p.add_argument(
        "--atmosphere-blur",
        type=float,
        default=0.0,
        help="Gaussian sigma (pixels) for edge point noise.",
    )
    p.add_argument(
        "--false-points",
        type=int,
        default=0,
        dest="n_false_points",
        help="Number of random false/outlier points to add.",
    )
    # Pipeline and I/O
    p.add_argument(
        "--binary",
        type=Path,
        default=Path("build/bin/pipeline_runner"),
        help="Path to pipeline_runner (supports --pipeline distance).",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path("cra_results.csv"),
        help="Output CSV path.",
    )
    p.add_argument(
        "--edge-decimals",
        type=int,
        default=0,
        metavar="N",
        help="Decimal places for edge point coords (0 = truncate to integer pixels). Default: 0.",
    )
    p.add_argument(
        "--regression",
        type=str,
        default="tls",
        choices=("tls", "ols", "ridge", "ransac"),
        help="Distance-stage regression (default: tls).",
    )
    p.add_argument(
        "--ridge-lambda",
        type=float,
        default=1e-6,
        metavar="L",
        help="Ridge L2 regularization (for --regression ridge).",
    )
    p.add_argument(
        "--ransac-residual-threshold",
        type=float,
        default=1e-4,
        metavar="T",
        help="RANSAC max residual for inlier (for --regression ransac).",
    )
    p.add_argument(
        "--ransac-max-iterations",
        type=int,
        default=100,
        metavar="N",
        help="RANSAC max iterations (for --regression ransac).",
    )
    p.add_argument(
        "--ransac-min-samples",
        type=int,
        default=0,
        metavar="N",
        help="RANSAC min samples per trial (0 = M-1, for --regression ransac).",
    )
    p.add_argument("--seed", type=int, default=None, help="Random seed for point noise.")
    p.add_argument(
        "--quaternion-noise-sigma-rad",
        type=float,
        default=QUATERNION_NOISE_SIGMA_RAD_DEFAULT,
        metavar="σ",
        help=(
            "Per-axis Gaussian σ (radians) for rotation-vector quaternion noise "
            f"(default: {QUATERNION_NOISE_SIGMA_RAD_DEFAULT:.6e}, i.e. 3σ = 1 arcsec per axis). "
            "Use 0 to disable."
        ),
    )
    p.add_argument(
        "--simulation-file",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to simulations.txt; use with --simulation-name to load constants from file.",
    )
    p.add_argument(
        "--simulation-name",
        type=str,
        default=None,
        metavar="NAME",
        help="Simulation section name in --simulation-file (e.g. baseline).",
    )
    args = p.parse_args()
    if args.simulation_file is not None and args.simulation_name is not None:
        if not args.simulation_file.is_file():
            print(f"distance_analysis: simulation file not found: {args.simulation_file}", file=sys.stderr)
            sys.exit(1)
        config = _load_simulation_config(args.simulation_file, args.simulation_name)
        if not config:
            print(f"distance_analysis: no section [{args.simulation_name}] in {args.simulation_file}", file=sys.stderr)
            sys.exit(1)
        _apply_simulation_config(args, config)
    return args


def main() -> None:
    args = parse_args()

    if not args.binary.is_file():
        print(f"cra_analysis: binary not found: {args.binary}", file=sys.stderr)
        sys.exit(1)
    if args.edge_decimals < 0:
        print("cra_analysis: --edge-decimals must be >= 0", file=sys.stderr)
        sys.exit(1)

    # Build simulation DataFrame (no I/O)
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
    if "atmosphere_blur" not in df_simulation.columns:
        df_simulation["atmosphere_blur"] = float("nan")
    df_simulation["atmosphere_blur"] = args.atmosphere_blur

    n = len(df_simulation)
    print(f"cra_analysis: running distance pipeline on {n} rows (binary={args.binary})")

    rng = np.random.default_rng(args.seed)
    for col in ("noisy_qw", "noisy_qx", "noisy_qy", "noisy_qz"):
        df_simulation[col] = np.nan

    for idx, row in df_simulation.iterrows():
        qw, qx, qy, qz = row.get("qw"), row.get("qx"), row.get("qy"), row.get("qz")
        quat_ok = (
            pd.notna(qw) and pd.notna(qx) and pd.notna(qy) and pd.notna(qz)
        )
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

        # Points from row (ideal limb edge); optionally add Gaussian noise + false points
        points = np.asarray(
            points_from_row(
                row,
                gaussian_sigma=args.atmosphere_blur,
                n_false_points=args.n_false_points,
                truncate=args.edge_decimals,
            ),
            dtype=np.float64,
        )
        df_simulation.at[idx, "n_edge_points"] = points.shape[0]
        success, result = run_distance_pipeline(
            args.binary,
            row,
            points,
            edge_decimals=args.edge_decimals,
            regression=args.regression,
            ridge_lambda=args.ridge_lambda,
            ransac_residual_threshold=args.ransac_residual_threshold,
            ransac_max_iterations=args.ransac_max_iterations,
            ransac_min_samples=args.ransac_min_samples,
            quaternion_wxyz=quaternion_wxyz,
        )
        if success:
            df_simulation.at[idx, "out_pos_x"] = result["out_pos_x"]
            df_simulation.at[idx, "out_pos_y"] = result["out_pos_y"]
            df_simulation.at[idx, "out_pos_z"] = result["out_pos_z"]
        else:
            df_simulation.at[idx, "out_pos_x"] = np.nan
            df_simulation.at[idx, "out_pos_y"] = np.nan
            df_simulation.at[idx, "out_pos_z"] = np.nan
        

    df = fill_pixel_metrics(df_simulation)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df_simulation.to_csv(args.output, index=True)
    print(f"cra_analysis: wrote {args.output}")


if __name__ == "__main__":
    main()
