#!/usr/bin/env python3
"""
Plot edge-detection results from ``scripts/edge/simulation.py`` CSV rows.

Overlays **detected** edges (pipeline) and **true** limb geometry
(``true_edge_points_json`` from ``points_from_row``). Full frame plus zoom with
pixel grid so subpixel offsets are obvious.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.image import imread

_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


def edge_points_from_row(row: pd.Series) -> np.ndarray:
    """Parse ``edge_points_json`` into (N, 2) float64."""
    raw = row["edge_points_json"]
    if pd.isna(raw) or raw == "":
        return np.zeros((0, 2), dtype=np.float64)
    data = json.loads(str(raw))
    return np.asarray(data, dtype=np.float64).reshape(-1, 2)


def true_edge_points_from_row(row: pd.Series) -> np.ndarray:
    """Parse ``true_edge_points_json`` from an edge-simulation CSV row."""
    if "true_edge_points_json" not in row.index:
        return np.zeros((0, 2), dtype=np.float64)
    raw = row["true_edge_points_json"]
    if pd.isna(raw) or raw == "":
        return np.zeros((0, 2), dtype=np.float64)
    data = json.loads(str(raw))
    return np.asarray(data, dtype=np.float64).reshape(-1, 2)


def resolve_rendered_image(
    row: pd.Series,
    *,
    base_dir: Path | None = None,
) -> Path:
    """Resolve ``rendered_image`` from an edge-simulation CSV row to an existing file."""
    p = Path(str(row["rendered_image"]))
    if p.is_file():
        return p.resolve()
    if base_dir is not None:
        q = (base_dir / p).resolve()
        if q.is_file():
            return q
        q2 = (Path(base_dir) / p.name).resolve()
        if q2.is_file():
            return q2
    raise FileNotFoundError(
        f"Could not find image for row: {p} (try base_dir= CSV directory or repo root)"
    )


def _image_to_grayscale(img: np.ndarray) -> tuple[np.ndarray, int, int]:
    """Return (2D array, width, height) matching limb edge_plot convention."""
    if img.ndim == 3:
        h, w = int(img.shape[0]), int(img.shape[1])
        return np.mean(img, axis=2), w, h
    h, w = int(img.shape[0]), int(img.shape[1])
    return img, w, h


def _pick_zoom_center(points: np.ndarray, mode: str, index: int) -> np.ndarray:
    if points.shape[0] == 0:
        raise ValueError("No edge points to center the zoom window.")
    if mode == "index":
        return np.asarray(points[int(index) % points.shape[0]], dtype=np.float64)
    if mode == "median":
        return np.median(points, axis=0)
    if mode == "mean":
        return np.mean(points, axis=0)
    raise ValueError("mode must be 'index', 'median', or 'mean'")


def _plot_x_markers(
    ax: plt.Axes,
    x: np.ndarray,
    y: np.ndarray,
    *,
    outer_ms: float,
    outer_mew: float,
    inner_ms: float,
    inner_mew: float,
    color: str,
    label: str | None,
    z: int = 5,
) -> None:
    """Draw 'x' markers with a white halo for contrast on variable backgrounds."""
    kwargs_outer = {
        "linestyle": "None",
        "marker": "x",
        "color": "white",
        "markersize": outer_ms,
        "markeredgewidth": outer_mew,
        "zorder": z,
    }
    kwargs_inner = {
        "linestyle": "None",
        "marker": "x",
        "color": color,
        "markersize": inner_ms,
        "markeredgewidth": inner_mew,
        "zorder": z + 1,
    }
    if label is not None:
        kwargs_inner["label"] = label
    ax.plot(x, y, **kwargs_outer)
    ax.plot(x, y, **kwargs_inner)


def plot_edge_simulation_row(
    row: pd.Series,
    *,
    base_dir: Path | None = None,
    zoom_window: float = 28.0,
    zoom_center: str = "median",
    zoom_center_index: int = 0,
    show_true_edges: bool = True,
    figsize: tuple[float, float] = (11.0, 5.5),
    dpi: int = 150,
    save_path: str | Path | None = None,
    show: bool = True,
) -> plt.Figure:
    """
    Plot **detected** (Zernike+Sobel) and **true** geometry limb points on the
    rendered image for one CSV row.

    **Left:** full frame. Detected points use ``'+'`` (blue + white outline).
    True geometry uses ``'x'`` (orangered + white outline) when present.

    **Right:** zoom with pixel grid; same markers at larger size.

    Parameters
    ----------
    row
        One row from edge simulation CSV (``rendered_image``, ``edge_points_json``;
        optional ``true_edge_points_json``).
    base_dir
        Directory used to resolve a relative ``rendered_image`` path
        (typically the directory containing the CSV).
    zoom_window
        Side length in **pixels** of the square zoom (image coordinates).
    zoom_center
        ``'median'`` | ``'mean'`` | ``'index'`` — how to pick the zoom center;
        with ``'index'``, use ``zoom_center_index`` into the point list.
    zoom_center_index
        Point index when ``zoom_center='index'`` (into detected points if any,
        else true points).
    show_true_edges
        Plot ``true_edge_points_json`` when the column exists and is non-empty.
    """
    img_path = resolve_rendered_image(row, base_dir=base_dir)
    raw = imread(str(img_path))
    gray, width, height = _image_to_grayscale(np.asarray(raw))

    pts_det = edge_points_from_row(row)
    pts_true = true_edge_points_from_row(row) if show_true_edges else np.zeros((0, 2))
    if pts_det.shape[0] == 0 and pts_true.shape[0] == 0:
        raise ValueError(
            "Row has no detected or true edge points; need edge_points_json and/or "
            "true_edge_points_json."
        )

    center_ref = pts_det if pts_det.shape[0] else pts_true
    center = _pick_zoom_center(center_ref, zoom_center, zoom_center_index)
    half = float(zoom_window) / 2.0
    cx, cy = float(center[0]), float(center[1])
    x0 = max(0, int(np.floor(cx - half)))
    x1 = min(width, int(np.ceil(cx + half)))
    y0 = max(0, int(np.floor(cy - half)))
    y1 = min(height, int(np.ceil(cy + half)))
    if x1 <= x0 or y1 <= y0:
        raise ValueError("Zoom window is empty; check image size and center.")

    crop = gray[y0:y1, x0:x1]

    fig, (ax_full, ax_zoom) = plt.subplots(
        1, 2, figsize=figsize, dpi=dpi, constrained_layout=True
    )

    # Full frame: image y increases downward (pixel rows)
    if raw.ndim == 3:
        ax_full.imshow(
            raw,
            extent=[0, width, height, 0],
            aspect="equal",
            interpolation="nearest",
        )
    else:
        ax_full.imshow(
            gray,
            extent=[0, width, height, 0],
            aspect="equal",
            interpolation="nearest",
            cmap="gray",
        )
    ax_full.set_xlim(0, width)
    ax_full.set_ylim(height, 0)
    ax_full.set_title("Full frame (use toolbar zoom for subpixel detail)")
    ax_full.set_xlabel("x (pixels)")
    ax_full.set_ylabel("y (pixels)")

    if pts_true.shape[0]:
        _plot_x_markers(
            ax_full,
            pts_true[:, 0],
            pts_true[:, 1],
            outer_ms=10.0,
            outer_mew=2.6,
            inner_ms=7.5,
            inner_mew=1.3,
            color="orangered",
            label="true limb (geometry)",
            z=3,
        )

    if pts_det.shape[0]:
        ax_full.plot(
            pts_det[:, 0],
            pts_det[:, 1],
            "+",
            color="white",
            markersize=9,
            markeredgewidth=2.4,
            linestyle="None",
            zorder=5,
        )
        ax_full.plot(
            pts_det[:, 0],
            pts_det[:, 1],
            "+",
            color="deepskyblue",
            markersize=7,
            markeredgewidth=1.0,
            linestyle="None",
            label="detected (pipeline)",
            zorder=6,
        )
    ax_full.legend(loc="upper right", fontsize=8)

    # Zoom panel: grayscale + pixel grid (matches limb.simulation.analysis.plot.edge_plot)
    ax_zoom.imshow(
        crop,
        extent=[x0, x1, y1, y0],
        aspect="equal",
        interpolation="nearest",
        cmap="gray",
    )
    ax_zoom.set_xlim(x0, x1)
    ax_zoom.set_ylim(y1, y0)
    ax_zoom.set_title(
        f"Zoom {zoom_window:g}×{zoom_window:g}px @ ({cx:.3f}, {cy:.3f}) ({zoom_center})"
    )
    ax_zoom.set_xlabel("x (pixels)")
    ax_zoom.set_ylabel("y (pixels)")

    ax_zoom.set_xticks(np.arange(x0, x1 + 1))
    ax_zoom.set_yticks(np.arange(y0, y1 + 1))
    ax_zoom.set_xticklabels([])
    ax_zoom.set_yticklabels([])
    ax_zoom.grid(True, color="black", linewidth=0.45, alpha=0.55)
    ax_zoom.minorticks_on()
    ax_zoom.grid(True, which="minor", color="gray", linewidth=0.25, alpha=0.35)

    def _in_window(p: np.ndarray) -> np.ndarray:
        return (
            (p[:, 0] >= x0)
            & (p[:, 0] <= x1)
            & (p[:, 1] >= y0)
            & (p[:, 1] <= y1)
        )

    n_true_in = 0
    if pts_true.shape[0]:
        m = _in_window(pts_true)
        n_true_in = int(np.count_nonzero(m))
        txz, tyz = pts_true[m, 0], pts_true[m, 1]
        if txz.size:
            _plot_x_markers(
                ax_zoom,
                txz,
                tyz,
                outer_ms=15.0,
                outer_mew=3.2,
                inner_ms=12.0,
                inner_mew=1.4,
                color="orangered",
                label=None,
                z=3,
            )

    n_det_in = 0
    if pts_det.shape[0]:
        m = _in_window(pts_det)
        n_det_in = int(np.count_nonzero(m))
        zx, zy = pts_det[m, 0], pts_det[m, 1]
        if zx.size:
            ax_zoom.plot(
                zx,
                zy,
                "+",
                color="white",
                markersize=14,
                markeredgewidth=3.0,
                linestyle="None",
                zorder=5,
            )
            ax_zoom.plot(
                zx,
                zy,
                "+",
                color="deepskyblue",
                markersize=11,
                markeredgewidth=1.2,
                linestyle="None",
                zorder=6,
            )

    fig.suptitle(
        f"{img_path.name} — zoom: {n_det_in}/{pts_det.shape[0]} detected, "
        f"{n_true_in}/{pts_true.shape[0]} true",
        fontsize=11,
    )

    if save_path is not None:
        fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)
    return fig


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv", type=Path, help="Edge simulation CSV path.")
    p.add_argument(
        "--row",
        type=int,
        default=0,
        help="DataFrame row index (default: 0).",
    )
    p.add_argument("--zoom-window", type=float, default=28.0, metavar="PX")
    p.add_argument(
        "--zoom-center",
        choices=("median", "mean", "index"),
        default="median",
    )
    p.add_argument("--zoom-center-index", type=int, default=0)
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--save", type=Path, default=None, help="Save figure to this path.")
    p.add_argument(
        "--no-show",
        action="store_true",
        help="Do not open interactive window (useful with --save).",
    )
    p.add_argument(
        "--no-true",
        action="store_true",
        help="Do not plot true_edge_points_json (detected only).",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    if not args.csv.is_file():
        print(f"edge plot: CSV not found: {args.csv}", file=sys.stderr)
        sys.exit(1)
    df = pd.read_csv(args.csv)
    if args.row < 0 or args.row >= len(df):
        print(f"edge plot: row {args.row} out of range [0, {len(df) - 1}]", file=sys.stderr)
        sys.exit(1)
    row = df.iloc[args.row]
    base_dir = args.csv.resolve().parent
    plot_edge_simulation_row(
        row,
        base_dir=base_dir,
        zoom_window=args.zoom_window,
        zoom_center=args.zoom_center,
        zoom_center_index=args.zoom_center_index,
        show_true_edges=not args.no_true,
        dpi=args.dpi,
        save_path=args.save,
        show=not args.no_show,
    )


if __name__ == "__main__":
    main()
