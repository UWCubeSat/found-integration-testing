#!/usr/bin/env python3
"""
Debug specified rows of the CRA results CSV: re-run the distance pipeline
for those rows, print inputs vs outputs, and optionally save edge files,
render limb images, and output the pixel conic and edge points.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from cra_analysis import _build_distance_cmd, _parse_position_stdout
from limb.simulation.edge.conic import _conic_matrix_to_coeffs
from limb.simulation.metadata.orchestrate import (
    _conic_from_row,
    _row_to_pose,
    points_from_row,
)


def run_one_with_verbose(
    binary: Path,
    row: pd.Series,
    points_xy: np.ndarray,
    edges_path: Path | None,
    *,
    conjugate_quaternion: bool = False,
    edge_decimals: int = 0,
) -> tuple[bool, dict, str]:
    """Run distance pipeline for one row; optionally save edges. Return (success, result, full_output)."""
    if points_xy.shape[0] < 3:
        return False, {"success": False}, "(fewer than 3 edge points)"
    points_xy = np.asarray(points_xy, dtype=np.float64)

    if edges_path is not None:
        edges_path.parent.mkdir(parents=True, exist_ok=True)
        path = edges_path
        delete_after = False
    else:
        fd, path_str = tempfile.mkstemp(suffix=".txt", text=True)
        path = Path(path_str)
        delete_after = True

    try:
        with open(path, "w") as f:
            for i in range(points_xy.shape[0]):
                x, y = float(points_xy[i, 0]), float(points_xy[i, 1])
                if edge_decimals > 0:
                    f.write(f"{x:.{edge_decimals}f} {y:.{edge_decimals}f}\n")
                else:
                    f.write(f"{x:.17g} {y:.17g}\n")
        cmd = _build_distance_cmd(
            binary, path, row, conjugate_quaternion=conjugate_quaternion
        )
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60
        )
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        result = _parse_position_stdout(out)
        ok = result.get("success", False) and proc.returncode == 0
        return ok, result, out
    finally:
        if delete_after:
            path.unlink(missing_ok=True)


def position_error_m(row: pd.Series) -> float:
    """Euclidean distance (m) between true and output position."""
    if pd.isna(row.get("out_pos_x")) or pd.isna(row.get("true_pos_x")):
        return float("nan")
    dx = row["out_pos_x"] - row["true_pos_x"]
    dy = row["out_pos_y"] - row["true_pos_y"]
    dz = row["out_pos_z"] - row["true_pos_z"]
    return float(np.sqrt(dx * dx + dy * dy + dz * dz))


def pixel_error_px(row: pd.Series) -> float:
    """Euclidean distance (px) between true and output centroid."""
    for c in ("true_x_centroid", "true_y_centroid", "out_x_centroid", "out_y_centroid"):
        if pd.isna(row.get(c)):
            return float("nan")
    dx = row["out_x_centroid"] - row["true_x_centroid"]
    dy = row["out_y_centroid"] - row["true_y_centroid"]
    return float(np.sqrt(dx * dx + dy * dy))


def render_limb_image(
    row: pd.Series,
    out_dir: Path,
    idx: int,
    *,
    sigma: float = 0.5,
) -> Path | None:
    """Render the limb from row config to out_dir/img_<idx>.png. Returns path or None on failure."""
    try:
        import torch
        from limb.simulation.render.conic import process_simulation
    except ImportError:
        return None
    camera, _shape_matrix, _tpc, rc = _row_to_pose(row)
    pixel_conic_3x3 = _conic_from_row(row)
    coeffs = _conic_matrix_to_coeffs(pixel_conic_3x3)
    w, h = int(row["cam_x_resolution"]), int(row["cam_y_resolution"])
    coeffs_nx6 = torch.from_numpy(np.asarray([coeffs], dtype=np.float32))
    K = torch.from_numpy(np.asarray([camera.calibration_matrix], dtype=np.float32))
    rc_batch = torch.from_numpy(np.asarray([rc], dtype=np.float32))
    process_simulation(
        coeffs_nx6,
        w,
        h,
        str(out_dir),
        K,
        rc_batch,
        batch_size=1,
        sigma=sigma,
        row_indices=np.array([idx], dtype=np.int64),
    )
    return out_dir / f"img_{idx:06d}.png"


def save_pixel_conic(row: pd.Series, out_path: Path) -> np.ndarray:
    """Write pixel conic (3x3 matrix and Ax²+Bxy+Cy²+Dx+Ey+F=0 coeffs) to out_path. Returns coeffs."""
    pixel_conic_3x3 = _conic_from_row(row)
    coeffs = _conic_matrix_to_coeffs(pixel_conic_3x3)
    A, B, C, D, E, F = coeffs
    lines = [
        "# Pixel conic: Ax² + Bxy + Cy² + Dx + Ey + F = 0",
        f"A={A:.10g} B={B:.10g} C={C:.10g} D={D:.10g} E={E:.10g} F={F:.10g}",
        "# 3x3 symmetric matrix (row-major):",
        f"  {pixel_conic_3x3[0,0]:.10g} {pixel_conic_3x3[0,1]:.10g} {pixel_conic_3x3[0,2]:.10g}",
        f"  {pixel_conic_3x3[1,0]:.10g} {pixel_conic_3x3[1,1]:.10g} {pixel_conic_3x3[1,2]:.10g}",
        f"  {pixel_conic_3x3[2,0]:.10g} {pixel_conic_3x3[2,1]:.10g} {pixel_conic_3x3[2,2]:.10g}",
    ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return coeffs


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Debug specified rows of the CRA results CSV by re-running the distance pipeline.",
    )
    p.add_argument(
        "--csv",
        type=Path,
        default=Path("cra_results.csv"),
        help="Path to results CSV (default: cra_results.csv).",
    )
    p.add_argument(
        "rows",
        nargs="+",
        type=int,
        metavar="INDEX",
        help="Row index(es) to debug (CSV index column).",
    )
    p.add_argument(
        "--binary",
        type=Path,
        default=Path("build/bin/pipeline_runner"),
        help="Path to pipeline_runner binary.",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="If set, save edges, conic, pipeline log, and (optionally) rendered image to DIR.",
    )
    p.add_argument(
        "--no-render",
        action="store_true",
        help="Do not render limb image even when --out-dir is set (avoids torch/GPU).",
    )
    p.add_argument(
        "--render-sigma",
        type=float,
        default=0.5,
        metavar="S",
        help="Edge blur sigma (px) for rendered limb image. Default: 0.5.",
    )
    p.add_argument(
        "--edge-decimals",
        type=int,
        default=0,
        metavar="N",
        help="Decimal places for edge coordinates (0 = integer pixels). Default: 0.",
    )
    p.add_argument(
        "--conjugate-quaternion",
        action="store_true",
        help="Conjugate quaternion before passing to pipeline (match cra_analysis if used there).",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Only print one-line summary per row; do not print full pipeline output.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not args.csv.is_file():
        print(f"debug_trouble_rows: CSV not found: {args.csv}", file=sys.stderr)
        sys.exit(1)
    if not args.binary.is_file():
        print(f"debug_trouble_rows: binary not found: {args.binary}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(args.csv, index_col=0)
    try:
        from limb.simulation.analysis.metrics import fill_pixel_metrics
        metric_cols = [
            "true_x_centroid", "true_y_centroid", "true_r_apparent",
            "out_x_centroid", "out_y_centroid", "out_r_apparent",
        ]
        for c in metric_cols:
            if c not in df.columns:
                df[c] = float("nan")
        df = fill_pixel_metrics(df)
    except Exception:
        pass  # optional: centroids may be missing

    n = len(df)
    for idx in args.rows:
        if idx < 0 or idx >= n:
            print(f"Row {idx}: index out of range [0, {n})", file=sys.stderr)
            continue
        row = df.loc[idx]
        sigma = row.get("atmosphere_blur")
        if pd.isna(sigma):
            sigma = 0.0
        sigma = float(sigma)
        points = np.asarray(
            points_from_row(
                row,
                gaussian_sigma=sigma,
                n_false_points=0,
                truncate=args.edge_decimals,
            ),
            dtype=np.float64,
        )
        edges_path = None
        if args.out_dir is not None:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            edges_path = args.out_dir / f"edges_{idx}.txt"

        success, result, full_output = run_one_with_verbose(
            args.binary,
            row,
            points,
            edges_path,
            conjugate_quaternion=args.conjugate_quaternion,
            edge_decimals=args.edge_decimals,
        )

        # Summary
        true_pos = (row["true_pos_x"], row["true_pos_y"], row["true_pos_z"])
        out_pos_csv = (row["out_pos_x"], row["out_pos_y"], row["out_pos_z"])
        pos_err_csv = position_error_m(row)
        pix_err = pixel_error_px(row) if "true_x_centroid" in row else float("nan")

        print(f"\n{'='*60}")
        print(f"Row index: {idx}")
        qw, qx, qy, qz = row.get("qw"), row.get("qx"), row.get("qy"), row.get("qz")
        q_str = ", ".join(
            f"{v:.6g}" if pd.notna(v) and v is not None else "nan"
            for v in (qw, qx, qy, qz)
        )
        print(f"  Quaternion (qw,qx,qy,qz): ({q_str})")
        print(f"  True position (m):     ({true_pos[0]:.2f}, {true_pos[1]:.2f}, {true_pos[2]:.2f})")
        print(f"  Output (from CSV):      ({out_pos_csv[0]:.2f}, {out_pos_csv[1]:.2f}, {out_pos_csv[2]:.2f})")
        if success:
            out_pos_run = (result["out_pos_x"], result["out_pos_y"], result["out_pos_z"])
            print(f"  Output (re-run):        ({out_pos_run[0]:.2f}, {out_pos_run[1]:.2f}, {out_pos_run[2]:.2f})")
            re_run_err = np.sqrt(
                (out_pos_run[0] - true_pos[0]) ** 2
                + (out_pos_run[1] - true_pos[1]) ** 2
                + (out_pos_run[2] - true_pos[2]) ** 2
            )
            print(f"  Position error (CSV):   {pos_err_csv:.2f} m")
            print(f"  Position error (re-run): {re_run_err:.2f} m")
        else:
            print(f"  Re-run: FAILED")
            print(f"  Position error (CSV):   {pos_err_csv:.2f} m")
        if not np.isnan(pix_err):
            print(f"  Pixel error (centroid): {pix_err:.2f} px")
        if "true_x_centroid" in row and pd.notna(row.get("true_x_centroid")):
            print(f"  True centroid (px):     ({row['true_x_centroid']:.2f}, {row['true_y_centroid']:.2f})")
            if pd.notna(row.get("out_x_centroid")):
                print(f"  Out centroid (px):      ({row['out_x_centroid']:.2f}, {row['out_y_centroid']:.2f})")
        print(f"  Edge points:            {len(points)}")
        if edges_path is not None:
            print(f"  Edges saved:            {edges_path}")

        # Pixel conic and edge points output (always when out_dir set; conic printed either way for debugging)
        pixel_conic_coeffs = None
        if args.out_dir is not None:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            conic_path = args.out_dir / f"conic_{idx}.txt"
            pixel_conic_coeffs = save_pixel_conic(row, conic_path)
            print(f"  Pixel conic saved:       {conic_path}")
            if not args.quiet:
                A, B, C, D, E, F = pixel_conic_coeffs
                print(f"  Pixel conic (Ax²+Bxy+Cy²+Dx+Ey+F=0): A={A:.6g} B={B:.6g} C={C:.6g} D={D:.6g} E={E:.6g} F={F:.6g}")
            # Edge points: print first 5 and reference file
            head = 5
            if len(points) <= head:
                print(f"  Edge points (px):        {[(float(p[0]), float(p[1])) for p in points]}")
            else:
                print(f"  Edge points (first {head}): {[(float(p[0]), float(p[1])) for p in points[:head]]} ... {len(points)} total (see {edges_path})")
            # Rendered limb image
            img_path = None
            if not args.no_render:
                img_path = render_limb_image(
                    row, args.out_dir, idx, sigma=args.render_sigma
                )
                if img_path is not None and img_path.is_file():
                    print(f"  Rendered image:          {img_path}")
                    # Overlay edge points on image (windowed plot from limb.simulation.analysis.plot)
                    if len(points) > 0:
                        try:
                            from limb.simulation.analysis.plot import edge_plot
                            w, h = int(row["cam_x_resolution"]), int(row["cam_y_resolution"])
                            window_length = min(400, min(w, h) // 2)
                            center_point = len(points) // 2
                            edge_plot_path = args.out_dir / f"edge_plot_{idx}.png"
                            edge_plot(
                                str(img_path),
                                np.asarray(points, dtype=np.float64),
                                center_point,
                                float(window_length),
                                true_points=None,
                                save_path=str(edge_plot_path),
                            )
                            print(f"  Edge plot (overlay):      {edge_plot_path}")
                        except Exception as e:
                            print(f"  Edge plot:               (skip: {e})")
                else:
                    print(f"  Rendered image:          (skip: install torch/limb render or use --no-render)")
            run_log = args.out_dir / f"run_{idx}.txt"
            # Header: all row columns (name = value), then pipeline output
            row_lines = [f"# Row index: {idx}", "# All columns (name = value):"]
            for col in row.index:
                val = row[col]
                if pd.isna(val):
                    row_lines.append(f"  {col} = nan")
                else:
                    row_lines.append(f"  {col} = {val}")
            row_lines.append("")
            row_lines.append("# --- Pipeline stdout/stderr ---")
            run_log.write_text("\n".join(row_lines) + "\n" + full_output, encoding="utf-8")
            print(f"  Pipeline log saved:     {run_log}")
        else:
            # No out_dir: still print conic and edge points to stdout
            pixel_conic_3x3 = _conic_from_row(row)
            coeffs = _conic_matrix_to_coeffs(pixel_conic_3x3)
            A, B, C, D, E, F = coeffs
            print(f"  Pixel conic (Ax²+Bxy+Cy²+Dx+Ey+F=0): A={A:.6g} B={B:.6g} C={C:.6g} D={D:.6g} E={E:.6g} F={F:.6g}")
            if len(points) <= 5:
                print(f"  Edge points (px):        {[(float(p[0]), float(p[1])) for p in points]}")
            else:
                print(f"  Edge points (first 5):   {[(float(p[0]), float(p[1])) for p in points[:5]]} ... {len(points)} total")

        if not args.quiet:
            print(f"\n--- Pipeline stdout/stderr ---\n{full_output}\n---")

    print(f"\nDone. Processed {len(args.rows)} row(s).")


if __name__ == "__main__":
    main()
