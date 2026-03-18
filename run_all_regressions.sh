#!/usr/bin/env bash
# Run run_batch.py for each distance-stage regression; write CSVs into distance-stage/.

set -e

CSV="sim_metadata.csv"
IMAGES_DIR="sim_images"
BINARY="build/bin/pipeline_runner"
OUT_DIR="distance-stage"

mkdir -p "$OUT_DIR"

echo "Running TLS..."
uv run python run_batch.py --csv "$CSV" --images-dir "$IMAGES_DIR" --binary "$BINARY" --output "$OUT_DIR/results_tls.csv" --regression tls

echo "Running OLS..."
uv run python run_batch.py --csv "$CSV" --images-dir "$IMAGES_DIR" --binary "$BINARY" --output "$OUT_DIR/results_ols.csv" --regression ols

echo "Running Ridge..."
uv run python run_batch.py --csv "$CSV" --images-dir "$IMAGES_DIR" --binary "$BINARY" --output "$OUT_DIR/results_ridge.csv" --regression ridge

echo "Running RANSAC..."
uv run python run_batch.py --csv "$CSV" --images-dir "$IMAGES_DIR" --binary "$BINARY" --output "$OUT_DIR/results_ransac.csv" --regression ransac

echo "Done. Outputs in $OUT_DIR/"
