#!/usr/bin/env bash
# =============================================================================
# run_batch.sh — Thin wrapper for run_batch.py (large-scale simulation)
#
# Uses default paths; pass extra flags (e.g. --with-memory, --max-rows 5).
#
# Prerequisites: run limb_simulation to produce sim_metadata.csv and sim_images/.
# See docs/METRICS.md and README "Large-scale simulation".
# =============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${ROOT}/.venv"
PYTHON="${VENV}/bin/python"
BIN="${ROOT}/build/bin/pipeline_runner"
CSV="${ROOT}/sim_metadata.csv"
IMAGES="${ROOT}/sim_images"
OUTPUT="${ROOT}/results.csv"

if [[ ! -d "${VENV}" ]]; then
    echo "run_batch.sh: venv not found at ${VENV} — run: bash install.sh" >&2
    exit 1
fi
if [[ ! -f "${PYTHON}" ]]; then
    echo "run_batch.sh: python not found in venv — run: bash install.sh" >&2
    exit 1
fi
if [[ ! -f "${CSV}" ]]; then
    echo "run_batch.sh: ${CSV} not found — run limb_simulation first (see README)" >&2
    exit 1
fi
if [[ ! -d "${IMAGES}" ]]; then
    echo "run_batch.sh: images dir not found: ${IMAGES} — run limb_simulation first" >&2
    exit 1
fi
if [[ ! -f "${BIN}" ]]; then
    echo "run_batch.sh: binary not found at ${BIN} — run: bash install.sh" >&2
    exit 1
fi

exec "${PYTHON}" "${ROOT}/run_batch.py" \
    --csv "${CSV}" \
    --images-dir "${IMAGES}" \
    --binary "${BIN}" \
    --output "${OUTPUT}" \
    "$@"
