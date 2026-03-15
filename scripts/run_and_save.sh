#!/usr/bin/env bash
# =============================================================================
# run_and_save.sh — Example: run pipeline_runner and save position to a file
#
# pipeline_runner prints one line to stdout: "POSITION x y z"
# This script captures that and writes to position.txt (or $OUT_FILE).
#
# Usage:
#   ./scripts/run_and_save.sh [--image <path>] [--output <file>]
#   Or set OUT_FILE and pass remaining args to pipeline_runner.
# =============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="${ROOT}/build/bin/pipeline_runner"
OUT_FILE="${OUT_FILE:-${ROOT}/position.txt}"

if [[ ! -f "${BIN}" ]]; then
    echo "Binary not found: ${BIN} — run: bash install.sh" >&2
    exit 1
fi

# Parse optional --output (script output file) and --image; pass rest to binary
EXTRA=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output) OUT_FILE="$2"; shift 2 ;;
        --image)  IMAGE="$2";   shift 2 ;;
        *)        EXTRA+=("$1"); shift ;;
    esac
done

if [[ -z "${IMAGE:-}" ]] && [[ -f "${ROOT}/vendor/found/test/common/assets/example_earth1.png" ]]; then
    IMAGE="${ROOT}/vendor/found/test/common/assets/example_earth1.png"
fi
if [[ -z "${IMAGE:-}" ]]; then
    echo "Pass --image <path> (or set IMAGE); no default image found." >&2
    exit 1
fi

output=$("${BIN}" --image "${IMAGE}" "${EXTRA[@]}")
echo "${output}" > "${OUT_FILE}"
echo "Wrote position to ${OUT_FILE}:"
echo "  ${output}"
