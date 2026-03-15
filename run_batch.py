#!/usr/bin/env python3
# =============================================================================
# run_batch.py — Large-scale FOUND simulation batch driver
#
# Reads sim_metadata.csv from limb_simulation, runs the FOUND binary per row
# with perf (instructions) and optional Valgrind (memory), records runtime,
# and writes a merged CSV with results and metrics. On run failure, leaves
# result and metric cells blank.
#
# Usage:
#   python run_batch.py --csv sim_metadata.csv --images-dir sim_images \
#       --binary build/bin/found_integration --output results.csv
#   python run_batch.py ... --with-memory --max-rows 10
# =============================================================================

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd

# Canonical column set (plan: CSV column layout final)
INPUT_COLUMNS = [
    "true_pos_x", "true_pos_y", "true_pos_z",
    "qx", "qy", "qz", "qw",
    "shape_axis_a", "shape_axis_b", "shape_axis_c",
    "atmosphere_blur",
]
CAMERA_COLUMNS = [
    "cam_focal_length", "cam_x_pixel_pitch", "cam_y_pixel_pitch",
    "cam_x_resolution", "cam_y_resolution",
    "cam_x_center", "cam_y_center",
]
OUTPUT_COLUMNS = ["out_pos_x", "out_pos_y", "out_pos_z"]
RUNTIME_COLUMNS = ["runtime_sec", "instructions", "bytes_allocated", "allocations"]
GENERATED_COLUMNS = [
    "true_x_centroid", "true_y_centroid", "true_r_apparent",
    "out_x_centroid", "out_y_centroid", "out_r_apparent",
]
CANONICAL_COLUMNS = (
    INPUT_COLUMNS + CAMERA_COLUMNS + OUTPUT_COLUMNS
    + RUNTIME_COLUMNS + GENERATED_COLUMNS
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run FOUND binary on limb_simulation CSV; collect metrics and write merged CSV.",
    )
    p.add_argument("--csv", type=Path, required=True, help="Path to sim_metadata.csv")
    p.add_argument("--images-dir", type=Path, required=True, help="Directory of img_000000.png, ...")
    p.add_argument("--binary", type=Path, required=True, help="Path to found_integration (or custom) binary")
    p.add_argument("--output", type=Path, required=True, help="Output merged CSV path")
    p.add_argument(
        "--with-memory",
        action="store_true",
        help="Run under Valgrind memcheck to collect bytes_allocated / allocations (slow)",
    )
    p.add_argument("--max-rows", type=int, default=None, help="Limit number of rows (for testing)")
    return p.parse_args()


def ensure_canonical_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure all canonical columns exist; add missing with empty/NaN. Preserve extra columns."""
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            if col in ("instructions", "bytes_allocated", "allocations"):
                df[col] = pd.NA  # nullable Int64
            elif col == "runtime_sec":
                df[col] = float("nan")
            else:
                df[col] = float("nan")
    # Column order: canonical first, then any extra from sim CSV
    extra = [c for c in df.columns if c not in CANONICAL_COLUMNS]
    return df[[c for c in CANONICAL_COLUMNS if c in df.columns] + extra]


def ground_truth_m(row: pd.Series) -> float:
    x = float(row["true_pos_x"])
    y = float(row["true_pos_y"])
    z = float(row["true_pos_z"])
    return math.sqrt(x * x + y * y + z * z)


def run_one(
    binary: Path,
    image_path: Path,
    ground_truth_m: float,
    focal_length: float,
    pixel_size: float,
    with_memory: bool,
) -> tuple[bool, dict, float, int | None, int | None, int | None]:
    """
    Run binary once. Returns (success, result_dict, runtime_sec, instructions, bytes_allocated, allocations).
    On failure or parse error, result_dict has success=False; metric values may be None.
    """
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        result_path = Path(f.name)
    try:
        cmd = [
            str(binary),
            "--image", str(image_path),
            "--ground-truth", str(ground_truth_m),
            "--focal-length", str(focal_length),
            "--pixel-size", str(pixel_size),
            "--output", str(result_path),
        ]
        runtime_sec = 0.0
        instructions: int | None = None
        bytes_allocated: int | None = None
        allocations: int | None = None

        if with_memory:
            # Valgrind wraps the binary; parse --stats from stderr
            valgrind_cmd = [
                "valgrind", "--tool=memcheck", "--stats", "--quiet",
                "--", *cmd
            ]
            t0 = time.perf_counter()
            proc = subprocess.run(
                valgrind_cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            runtime_sec = time.perf_counter() - t0
            stderr = proc.stderr or ""
            # Parse "bytes allocated" and alloc/free counts from Valgrind summary
            # e.g. "total heap usage: 1,234 allocs, 1,234 frees, 56,789 bytes allocated"
            m = re.search(r"(\d[\d,]*) allocs", stderr)
            if m:
                allocations = int(m.group(1).replace(",", ""))
            m = re.search(r"(\d[\d,]*) bytes allocated", stderr)
            if m:
                bytes_allocated = int(m.group(1).replace(",", ""))
            ok = proc.returncode == 0
        else:
            # perf stat -e instructions
            perf_cmd = ["perf", "stat", "-e", "instructions", "--", *cmd]
            t0 = time.perf_counter()
            proc = subprocess.run(
                perf_cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            runtime_sec = time.perf_counter() - t0
            # perf writes to stderr: "    123456789  instructions"
            stderr = proc.stderr or ""
            m = re.search(r"[\s]*([\d,]+)\s+instructions", stderr)
            if m:
                instructions = int(m.group(1).replace(",", ""))
            ok = proc.returncode == 0

        result: dict = {"success": False}
        if result_path.exists():
            try:
                with open(result_path) as f:
                    result = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
            result_path.unlink(missing_ok=True)

        return (result.get("success", False), result, runtime_sec, instructions, bytes_allocated, allocations)
    except subprocess.TimeoutExpired:
        result_path.unlink(missing_ok=True)
        return (False, {"success": False}, 0.0, None, None, None)
    except FileNotFoundError as e:
        result_path.unlink(missing_ok=True)
        print(f"run_batch: command not found: {e}", file=sys.stderr)
        raise
    finally:
        result_path.unlink(missing_ok=True)


def main() -> None:
    args = parse_args()
    if not args.csv.exists():
        print(f"run_batch: CSV not found: {args.csv}", file=sys.stderr)
        sys.exit(1)
    if not args.images_dir.is_dir():
        print(f"run_batch: images dir not found: {args.images_dir}", file=sys.stderr)
        sys.exit(1)
    if not args.binary.is_file():
        print(f"run_batch: binary not found: {args.binary}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(args.csv, index_col=0)
    df = ensure_canonical_columns(df)
    if args.max_rows is not None:
        df = df.iloc[: args.max_rows]

    n = len(df)
    print(f"run_batch: processing {n} rows (binary={args.binary}, with_memory={args.with_memory})")

    for i, (idx, row) in enumerate(df.iterrows()):
        image_path = args.images_dir / f"img_{idx:06d}.png"
        if not image_path.exists():
            print(f"  row {idx}: image missing {image_path}", file=sys.stderr)
            continue
        gt = ground_truth_m(row)
        fl = float(row["cam_focal_length"])
        ps = float(row["cam_x_pixel_pitch"])
        success, result, runtime_sec, instructions, bytes_allocated, allocations = run_one(
            args.binary, image_path, gt, fl, ps, args.with_memory
        )
        df.at[idx, "runtime_sec"] = runtime_sec
        df.at[idx, "instructions"] = pd.NA if instructions is None else instructions
        df.at[idx, "bytes_allocated"] = pd.NA if bytes_allocated is None else bytes_allocated
        df.at[idx, "allocations"] = pd.NA if allocations is None else allocations
        if success:
            # Current binary outputs distance_m, not position; leave out_pos_* blank unless in result
            for k in ("out_pos_x", "out_pos_y", "out_pos_z"):
                if k in result and result[k] is not None:
                    df.at[idx, k] = result[k]
        else:
            # Leave result cells blank per plan
            for col in OUTPUT_COLUMNS + GENERATED_COLUMNS:
                if col in df.columns:
                    df.at[idx, col] = pd.NA
        if (i + 1) % 10 == 0 or (i + 1) == n:
            print(f"  {i + 1}/{n}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=True)
    print(f"run_batch: wrote {args.output}")


if __name__ == "__main__":
    main()
