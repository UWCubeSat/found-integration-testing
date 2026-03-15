#!/usr/bin/env bash
# =============================================================================
# run_batch.sh — Thin wrapper for run_batch.py (large-scale simulation)
#
# Optional flags to locate inputs and output (defaults under ROOT):
#   --csv         <path>  Path to sim_metadata.csv (default: ${ROOT}/sim_metadata.csv)
#   --images-dir  <path>  Directory of img_000000.png, ... (default: ${ROOT}/sim_images)
#   --output      <path>  Output merged CSV (default: ${ROOT}/results.csv)
#
# Remaining args are passed to run_batch.py (e.g. --with-memory, --max-rows 5).
# Prerequisites: run limb_simulation to produce CSV and images; see docs/METRICS.md.
# =============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="${ROOT}/build/bin/pipeline_runner"

# Default paths (overridable via flags)
CSV="${ROOT}/sim_metadata.csv"
IMAGES="${ROOT}/sim_images"
OUTPUT="${ROOT}/results.csv"

# Parse flags that locate CSV, images dir, and output
EXTRA=()
i=1
while [[ $i -le $# ]]; do
    case "${!i}" in
        --csv)
            ((i++))
            [[ $i -le $# ]] && CSV="${!i}"
            ((i++))
            ;;
        --images-dir)
            ((i++))
            [[ $i -le $# ]] && IMAGES="${!i}"
            ((i++))
            ;;
        --output)
            ((i++))
            [[ $i -le $# ]] && OUTPUT="${!i}"
            ((i++))
            ;;
        *)
            EXTRA+=("${!i}")
            ((i++))
            ;;
    esac
done

if ! command -v uv &>/dev/null; then
    echo "run_batch.sh: uv not found — install uv or run: bash install.sh" >&2
    exit 1
fi
if [[ ! -f "${BIN}" ]]; then
    echo "run_batch.sh: binary not found at ${BIN} — run: bash install.sh" >&2
    exit 1
fi
if [[ ! -f "${CSV}" ]]; then
    echo "run_batch.sh: CSV not found: ${CSV} — run limb_simulation first (see README)" >&2
    exit 1
fi
if [[ ! -d "${IMAGES}" ]]; then
    echo "run_batch.sh: images dir not found: ${IMAGES} — run limb_simulation first" >&2
    exit 1
fi

exec uv run --project "${ROOT}" "${ROOT}/run_batch.py" \
    --csv "${CSV}" \
    --images-dir "${IMAGES}" \
    --binary "${BIN}" \
    --output "${OUTPUT}" \
    "${EXTRA[@]}"
