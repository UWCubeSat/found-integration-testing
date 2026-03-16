#!/usr/bin/env python3
# =============================================================================
# plot_edges.py — Run edge_runner on image(s), plot edge points, save to output/
#
# Usage:
#   python plot_edges.py --image sim_images/img_000000.png --binary build/bin/edge_runner --output-dir output
#   python plot_edges.py --images-dir sim_images --csv sim_metadata.csv --binary build/bin/edge_runner --output-dir output
#
# With --image: uses default focal length and pixel size (or pass --focal-length, --pixel-size).
# With --images-dir and --csv: uses per-row camera/quaternion from CSV (same as run_batch).
# =============================================================================

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run edge_runner on image(s), plot edge points on images, save to output directory.",
    )
    p.add_argument("--binary", type=Path, default=Path("build/bin/edge_runner"), help="Path to edge_runner binary")
    p.add_argument("--output-dir", type=Path, default=Path("output"), help="Directory for plotted images")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--image", type=Path, help="Single image path")
    g.add_argument("--images-dir", type=Path, help="Directory of images (use with --csv for metadata)")
    p.add_argument("--csv", type=Path, default=None, help="sim_metadata.csv for --images-dir (focal, quaternion, etc.)")
    p.add_argument("--focal-length", type=float, default=85e-3, help="Default focal length (m) for single --image")
    p.add_argument("--pixel-size", type=float, default=1.0, help="Default pixel size for single --image")
    p.add_argument("--max-images", type=int, default=None, help="Limit number of images (for testing)")
    return p.parse_args()


def build_edge_cmd(
    binary: Path,
    image_path: Path,
    row: pd.Series | None,
    default_focal: float = 85e-3,
    default_pixel: float = 1.0,
) -> list[str]:
    """Build edge_runner argv. If row is None, use default_focal and default_pixel."""
    if row is not None:
        cmd = [
            str(binary),
            "--image", str(image_path),
            "--focal-length", str(float(row["cam_focal_length"])),
            "--pixel-size", str(float(row["cam_x_pixel_pitch"])),
        ]
        qw, qx, qy, qz = row.get("qw"), row.get("qx"), row.get("qy"), row.get("qz")
        if pd.notna(qw) and pd.notna(qx) and pd.notna(qy) and pd.notna(qz):
            cmd += ["--quaternion", str(float(qw)), str(float(qx)), str(float(qy)), str(float(qz))]
        a, b, c = row.get("shape_axis_a"), row.get("shape_axis_b"), row.get("shape_axis_c")
        if pd.notna(a) and pd.notna(b) and pd.notna(c):
            cmd += ["--principle-axes", str(float(a)), str(float(b)), str(float(c))]
        return cmd
    return [
        str(binary),
        "--image", str(image_path),
        "--focal-length", str(default_focal),
        "--pixel-size", str(default_pixel),
    ]


EDGE_LINE_RE = re.compile(r"^\s*([-\d.eE+]+)\s+([-\d.eE+]+)\s*$")


def run_edge_runner(
    binary: Path,
    image_path: Path,
    row: pd.Series | None,
    default_focal: float = 85e-3,
    default_pixel: float = 1.0,
) -> list[tuple[float, float]]:
    """Run edge_runner, return list of (x, y) edge points."""
    cmd = build_edge_cmd(binary, image_path, row, default_focal, default_pixel)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    points: list[tuple[float, float]] = []
    for line in (proc.stdout or "").splitlines():
        m = EDGE_LINE_RE.match(line)
        if m:
            points.append((float(m.group(1)), float(m.group(2))))
    if proc.returncode != 0 and not points:
        print(f"  warning: edge_runner exited {proc.returncode} for {image_path}", file=sys.stderr)
    return points


def save_points(points: list[tuple[float, float]], out_path: Path) -> None:
    """Write edge points to a CSV file (columns: x, y)."""
    if not points:
        return
    df = pd.DataFrame(points, columns=["x", "y"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)


def plot_and_save(image_path: Path, points: list[tuple[float, float]], out_path: Path) -> None:
    """Load image, scatter edge points, save to out_path."""
    import matplotlib.pyplot as plt
    import numpy as np
    img = plt.imread(image_path)
    h, w = img.shape[:2]
    fig, ax = plt.subplots(1, 1, figsize=(w / 80, h / 80))
    if np.issubdtype(img.dtype, np.floating):
        ax.imshow(img, vmin=0, vmax=1, origin="upper")
    else:
        ax.imshow(img, vmin=0, vmax=255, origin="upper")
    if points:
        xs, ys = zip(*points)
        ax.scatter(
            xs, ys,
            s=80,
            c="#ff0000",
            alpha=0.95,
            edgecolors="white",
            linewidths=1.5,
            zorder=5,
        )
    ax.set_axis_off()
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)
    fig.tight_layout(pad=0)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight", pad_inches=0, dpi=100)
    plt.close(fig)


def main() -> int:
    global args
    args = parse_args()
    if not args.binary.is_file():
        print(f"plot_edges: binary not found: {args.binary}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.image is not None:
        if not args.image.is_file():
            print(f"plot_edges: image not found: {args.image}", file=sys.stderr)
            return 1
        points = run_edge_runner(args.binary, args.image, None, args.focal_length, args.pixel_size)
        out_path = args.output_dir / args.image.name
        points_path = args.output_dir / f"{args.image.stem}_edges.csv"
        save_points(points, points_path)
        plot_and_save(args.image, points, out_path)
        print(f"  {args.image.name} -> {out_path}, {points_path} ({len(points)} points)")
        return 0

    if not args.images_dir.is_dir():
        print(f"plot_edges: images dir not found: {args.images_dir}", file=sys.stderr)
        return 1
    df = pd.read_csv(args.csv, index_col=0) if args.csv and args.csv.is_file() else None
    if df is None and args.csv:
        print(f"plot_edges: CSV not found: {args.csv}", file=sys.stderr)
        return 1
    if df is None:
        print("plot_edges: --images-dir requires --csv for per-image metadata", file=sys.stderr)
        return 1

    images = sorted(args.images_dir.glob("img_*.png"))
    if args.max_images is not None:
        images = images[: args.max_images]
    print(f"plot_edges: processing {len(images)} images -> {args.output_dir}")

    for i, image_path in enumerate(images):
        idx = int(image_path.stem.split("_")[1])
        row = df.loc[idx] if idx in df.index else None
        points = run_edge_runner(args.binary, image_path, row)
        out_path = args.output_dir / image_path.name
        points_path = args.output_dir / f"{image_path.stem}_edges.csv"
        save_points(points, points_path)
        plot_and_save(image_path, points, out_path)
        if (i + 1) % 10 == 0 or (i + 1) == len(images):
            print(f"  {i + 1}/{len(images)}")

    print(f"plot_edges: wrote {len(images)} images and CSV point files to {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
