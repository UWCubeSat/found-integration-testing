# Metrics collection for large-scale FOUND simulation

This document describes how **runtime**, **CPU instructions**, and **dynamic memory** are collected when running the batch driver (`run_batch.py`) on Linux.

## Requirements (Linux)

- **perf** — for instruction counts. Install: `sudo apt install linux-tools-common linux-tools-$(uname -r)` (or equivalent). You may need `kernel.perf_event_paranoid` set to allow user-space counting (e.g. `sysctl kernel.perf_event_paranoid=1` or run with appropriate capabilities).
- **Valgrind** (optional) — for `bytes_allocated` and `allocations` when using `--with-memory`. Install: `sudo apt install valgrind`. Runs are much slower (10–30x) when enabled.
- **Python 3** with **pandas** — the batch driver uses pandas for CSV I/O. Use the repo `.venv` (from `install.sh`) which includes found-tools and pandas.

## How metrics are collected

| Metric | Method | Notes |
|--------|--------|--------|
| **runtime_sec** | `time.perf_counter()` around the subprocess run | Wall-clock seconds per image. |
| **instructions** | `perf stat -e instructions -- <binary> ...` | Parsed from perf stderr (e.g. `123456789  instructions`). |
| **bytes_allocated** | Valgrind `--tool=memcheck --stats` (optional) | Only when `--with-memory` is passed. Parsed from Valgrind summary. |
| **allocations** | Same Valgrind run | Alloc/free count from Valgrind summary. |

## Running the batch pipeline

1. **Generate images and metadata** with found-tools `limb_simulation` (from this repo’s venv or a found-tools environment):

   ```bash
   .venv/bin/limb_simulation \
     --fovs 80 70 \
     --resolutions 512 1024 \
     --distances 7000000 8000000 \
     --num-positions-per-point 2 \
     --num-spins-per-position 2 \
     --num-radials-per-spin 2 \
     --output-csv sim_metadata.csv \
     --output-folder sim_images
   ```

2. **Run the batch driver** (from this repo, after `bash install.sh` and building the binary):

   ```bash
   .venv/bin/python run_batch.py \
     --csv sim_metadata.csv \
     --images-dir sim_images \
     --binary build/bin/pipeline_runner \
     --output results.csv
   ```

   For a quick test with a few rows:

   ```bash
   .venv/bin/python run_batch.py --csv sim_metadata.csv --images-dir sim_images \
     --binary build/bin/pipeline_runner --output results.csv --max-rows 5
   ```

   To also collect memory metrics (slower):

   ```bash
   .venv/bin/python run_batch.py ... --with-memory
   ```

## Output CSV

The merged CSV has one row per image (same index as `sim_metadata.csv`). Columns include all simulation inputs, outputs (`out_pos_x/y/z` when the binary provides them), and the runtime metric columns: `runtime_sec`, `instructions`, `bytes_allocated`, `allocations`. On run failure, result and optional metric cells are left blank per the plan.

## Troubleshooting

- **perf: Permission denied** — Adjust `kernel.perf_event_paranoid` or run with `cap_sys_admin` (e.g. `sudo` for testing only).
- **Valgrind not found** — Install valgrind or omit `--with-memory`.
- **pandas not found** — Use the repo venv: `.venv/bin/python run_batch.py ...`.
