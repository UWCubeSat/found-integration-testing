#!/usr/bin/env python3
"""
CRA analysis: build simulation grid, generate noisy edge points per row,
run the distance pipeline (edges -> POSITION), and save results to CSV.
"""

from __future__ import annotations

import argparse
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
from limb.utils._camera import Camera

POSITION_LINE_RE = re.compile(
    r"POSITION\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)"
)


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
    conjugate_quaternion: bool = False,
) -> list[str]:
    """Build argv for --pipeline distance (edges file + camera/axes/quat).
    If conjugate_quaternion: pass (qw, -qx, -qy, -qz) to FOUND; else pass df quat as-is.
    """
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
    ]
    # Quaternion from df (qw, qx, qy, qz). If flag set, conjugate before passing to FOUND.
    qw, qx, qy, qz = row.get("qw"), row.get("qx"), row.get("qy"), row.get("qz")
    if pd.notna(qw) and pd.notna(qx) and pd.notna(qy) and pd.notna(qz):
        qw, qx, qy, qz = float(qw), float(qx), float(qy), float(qz)
        if conjugate_quaternion:
            qx, qy, qz = -qx, -qy, -qz
        cmd += ["--quaternion", str(qw), str(qx), str(qy), str(qz)]
    a, b, c = row.get("shape_axis_a"), row.get("shape_axis_b"), row.get("shape_axis_c")
    if pd.notna(a) and pd.notna(b) and pd.notna(c):
        cmd += ["--principle-axes", str(float(a)), str(float(b)), str(float(c))]
    return cmd


def run_distance_pipeline(
    binary: Path,
    row: pd.Series,
    points_xy: np.ndarray,
    *,
    conjugate_quaternion: bool = False,
    edge_decimals: int = 0,
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
        cmd = _build_distance_cmd(binary, path, row, conjugate_quaternion=conjugate_quaternion)
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
        "--conjugate-quaternion",
        action="store_true",
        help="Conjugate quaternion before passing to FOUND; if not set, pass df quaternion as-is.",
    )
    p.add_argument(
        "--edge-decimals",
        type=int,
        default=0,
        metavar="N",
        help="Decimal places for edge point coords (0 = truncate to integer pixels). Default: 0.",
    )
    p.add_argument("--seed", type=int, default=None, help="Random seed for point noise.")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not args.binary.is_file():
        print(f"cra_analysis: binary not found: {args.binary}", file=sys.stderr)
        sys.exit(1)
    if args.edge_decimals < 0:
        print("cra_analysis: --edge-decimals must be >= 0", file=sys.stderr)
        sys.exit(1)

    rng = np.random.default_rng(args.seed)

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

    for idx, row in df_simulation.iterrows():
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
        success, result = run_distance_pipeline(
            args.binary,
            row,
            points,
            conjugate_quaternion=args.conjugate_quaternion,
            edge_decimals=args.edge_decimals,
        )
        if success:
            df_simulation.at[idx, "out_pos_x"] = result["out_pos_x"]
            df_simulation.at[idx, "out_pos_y"] = result["out_pos_y"]
            df_simulation.at[idx, "out_pos_z"] = result["out_pos_z"]
        else:
            df_simulation.at[idx, "out_pos_x"] = np.nan
            df_simulation.at[idx, "out_pos_y"] = np.nan
            df_simulation.at[idx, "out_pos_z"] = np.nan

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df_simulation.to_csv(args.output, index=True)
    print(f"cra_analysis: wrote {args.output}")


if __name__ == "__main__":
    main()
