#!/usr/bin/env python3
"""
Generate distance vs delta plots from multi-camera CSV results.
Creates 3 plots per camera: Δ(radius), Δ(x_centroid), Δ(y_centroid) vs Range.
Uses limb.simulation.analysis.plot.plot_column_summary (prediction interval, 99% default).
Output: results/plots/<csv_stem>/<camera>/
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from limb.simulation.analysis.plot import plot_column_summary


def _range_m(df: pd.DataFrame) -> np.ndarray:
    """True range (m) from true position."""
    return np.sqrt(
        df["true_pos_x"].astype(float) ** 2
        + df["true_pos_y"].astype(float) ** 2
        + df["true_pos_z"].astype(float) ** 2
    )


def _fov_deg_series(df: pd.DataFrame) -> pd.Series:
    """Horizontal FOV in degrees per row from camera parameters."""
    fl = df["cam_focal_length"].astype(float)
    nx = df["cam_x_resolution"].astype(float)
    px = df["cam_x_pixel_pitch"].astype(float)
    half_sensor = (nx * px) / 2.0
    fov_rad = 2.0 * np.arctan(half_sensor / fl)
    return np.degrees(fov_rad)


def _fov_deg(df: pd.DataFrame) -> float:
    """FOV in degrees for a single-camera subframe (one row or same per group)."""
    return float(_fov_deg_series(df).iloc[0])


def _camera_groups(df: pd.DataFrame):
    """
    Split dataframe by camera type: resolution and FOV (so 5°, 10°, 20°, 40°, etc. each get separate plots).
    Yields (camera_label, sub_df) where camera_label is e.g. "512x512_5deg", "512x512_10deg".
    """
    res_x = df["cam_x_resolution"].astype(int).astype(str)
    res_y = df["cam_y_resolution"].astype(int).astype(str)
    fov = _fov_deg_series(df).round(0).astype(int).astype(str)
    cam_type = (res_x + "x" + res_y + "_" + fov + "deg").values
    for ct in np.unique(cam_type):
        mask = cam_type == ct
        yield ct, df.loc[mask].copy()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv",
        type=Path,
        default=Path("results/multi-cam.csv"),
        nargs="?",
        help="Path to multi-cam CSV",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Base output directory (default: results/plots/<csv_stem>)",
    )
    parser.add_argument(
        "--n-points",
        type=int,
        default=1000,
        help="Max points to show per scatter (default: 1000)",
    )
    parser.add_argument(
        "--ci",
        type=float,
        default=99.0,
        help="Confidence interval percent (default: 99)",
    )
    args = parser.parse_args()

    csv_path = args.csv.resolve()
    if not csv_path.is_file():
        raise SystemExit(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    df["range_m"] = _range_m(df)

    required = ["range_m", "delta_x_centroid", "delta_y_centroid", "delta_r_apparent"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"CSV missing columns: {missing}")

    out_base = args.out_dir or (csv_path.parent / "plots" / csv_path.stem)
    out_base = out_base.resolve()

    confidence = args.ci / 100.0  # e.g. 99 -> 0.99

    for cam_label, sub in _camera_groups(df):
        fov = _fov_deg(sub)
        res_px = int(sub["cam_x_resolution"].iloc[0])
        title_suffix = f"({res_px}px, {fov:.0f}° FOV)"
        cam_dir = out_base / cam_label
        cam_dir.mkdir(parents=True, exist_ok=True)

        fig = plot_column_summary(
            sub,
            "delta_r_apparent",
            n_points=args.n_points,
            n_bins=50,
            confidence=confidence,
            distance_column="range_m",
            title=f"Δr vs Range {title_suffix}",
            xlabel="Range (m)",
            ylabel="Δr (px)",
            save_path=cam_dir / "delta_r_vs_range.png",
        )
        plt.close(fig)
        fig = plot_column_summary(
            sub,
            "delta_x_centroid",
            n_points=args.n_points,
            n_bins=50,
            confidence=confidence,
            distance_column="range_m",
            title=f"Δx_centroid vs Range {title_suffix}",
            xlabel="Range (m)",
            ylabel="Δx_centroid (px)",
            save_path=cam_dir / "delta_x_centroid_vs_range.png",
        )
        plt.close(fig)
        fig = plot_column_summary(
            sub,
            "delta_y_centroid",
            n_points=args.n_points,
            n_bins=50,
            confidence=confidence,
            distance_column="range_m",
            title=f"Δy_centroid vs Range {title_suffix}",
            xlabel="Range (m)",
            ylabel="Δy_centroid (px)",
            save_path=cam_dir / "delta_y_centroid_vs_range.png",
        )
        plt.close(fig)
        print(f"Wrote 3 plots to {cam_dir}")

    print(f"Done. Output base: {out_base}")


if __name__ == "__main__":
    main()
