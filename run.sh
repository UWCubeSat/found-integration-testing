#!/usr/bin/env bash
# =============================================================================
# run.sh — FOUND integration test pipeline
#
#   Step 1: Generates a synthetic Earth image from position + orientation.
#
#   Step 2  Runs edge detection + distance determination on the image.
#
#   Step 3  Analyzes result.json and produces a report.
#             TODO: uncomment once found-tools adds found-analyzer entry point.
#
# Usage:
#   ./run.sh [OPTIONS]
#
# Options:
#   --position     "x y z"        Spacecraft position, meters    (default: "10378137 0 0")
#   --orientation  "de ra roll"   Spacecraft orientation, deg    (default: "140 0 0")
#   --focal-length <m>            Camera focal length            (default: 85e-3)
#   --pixel-size   <m>            Camera pixel size              (default: 20e-6)
#   --x-resolution <px>           Image width                    (default: 512)
#   --y-resolution <px>           Image height                   (default: 512)
#   --image        <path>         Supply image directly, skip Step 1
#   --output-dir   <path>         Where to write results         (default: results/<timestamp>)
# =============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="${ROOT}/build/bin/found_integration"
VENV="${ROOT}/.venv"        # created by install.sh
PYTHON="${VENV}/bin/python3"

# ── defaults ──────────────────────────────────────────────────────────────────
POSITION="10378137 0 0"
ORIENTATION="140 0 0"
FOCAL_LENGTH="85e-3"
PIXEL_SIZE="20e-6"
X_RES="512"
Y_RES="512"
SUPPLIED_IMAGE=""
OUTPUT_DIR="${ROOT}/results/$(date +%Y%m%d_%H%M%S)"

# ── arg parsing ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --position)     POSITION="$2";       shift 2 ;;
        --orientation)  ORIENTATION="$2";    shift 2 ;;
        --focal-length) FOCAL_LENGTH="$2";   shift 2 ;;
        --pixel-size)   PIXEL_SIZE="$2";     shift 2 ;;
        --x-resolution) X_RES="$2";          shift 2 ;;
        --y-resolution) Y_RES="$2";          shift 2 ;;
        --image)        SUPPLIED_IMAGE="$2"; shift 2 ;;
        --output-dir)   OUTPUT_DIR="$2";     shift 2 ;;
        *) echo "Unknown flag: $1"; exit 1 ;;
    esac
done

# ── helpers ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BOLD='\033[1m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
warn() { echo -e "${YELLOW}  ⚠${NC} $*"; }
die()  { echo -e "${RED}  ✗${NC} $*"; exit 1; }
log()  { echo -e "${BOLD}[run.sh]${NC} $*"; }
step() { echo -e "\n${CYAN}${BOLD}── $* ─────────────────────────────────────────────────────${NC}"; }

# Ground truth distance = ||position||
GROUND_TRUTH_M="$("${PYTHON}" -c "
import math
coords = [float(x) for x in '${POSITION}'.split()]
print(math.sqrt(sum(c**2 for c in coords)))
")"

# ── preflight ─────────────────────────────────────────────────────────────────
step "Preflight"

[[ -d "${VENV}" ]] || die "Venv not found at ${VENV} — run: bash install.sh"
[[ -f "${BIN}" ]] || die "Binary not found at ${BIN} — run: bash install.sh"
ok "found_integration binary"

if [[ -n "${SUPPLIED_IMAGE}" ]]; then
    [[ -f "${SUPPLIED_IMAGE}" ]] || die "Supplied image not found: ${SUPPLIED_IMAGE}"
    ok "Using supplied image: ${SUPPLIED_IMAGE}"
fi

mkdir -p "${OUTPUT_DIR}"
IMAGE="${SUPPLIED_IMAGE:-${OUTPUT_DIR}/image.png}"
RESULT="${OUTPUT_DIR}/result.json"
REPORT_DIR="${OUTPUT_DIR}/report"
mkdir -p "${REPORT_DIR}"

log "Output: ${OUTPUT_DIR}"
log "Position:    ${POSITION}"
log "Orientation: ${ORIENTATION}"

# Step 1 — Generate image 
step "Step 1 — Generate image  [found-generator]"

if [[ -n "${SUPPLIED_IMAGE}" ]]; then
    ok "Skipping — using supplied image"

else
    "${PYTHON}" -m found_CLI_tools.generator \
        --position    ${POSITION} \
        --orientation ${ORIENTATION} \
        --focal-length   "${FOCAL_LENGTH}" \
        --pixel-size     "${PIXEL_SIZE}" \
        --x-resolution   "${X_RES}" \
        --y-resolution   "${Y_RES}" \
        --filename       "${IMAGE}"

    [[ -f "${IMAGE}" ]] || die "generator did not produce ${IMAGE}"
    ok "Image generated: ${IMAGE}  ($(du -h "${IMAGE}" | cut -f1))"
fi

# Step 2 — Edge detection + distance
step "Step 2 — Edge detection + distance  [found_integration]"

"${BIN}" \
    --image          "${IMAGE}" \
    --focal-length   "${FOCAL_LENGTH}" \
    --pixel-size     "${PIXEL_SIZE}" \
    --ground-truth   "${GROUND_TRUTH_M}" \
    --output         "${RESULT}"

[[ -f "${RESULT}" ]] || die "found_integration did not produce ${RESULT}"

SUCCESS=$("${PYTHON}" -c "import json; print(json.load(open('${RESULT}'))['success'])")
[[ "${SUCCESS}" == "True" ]] || die "found_integration reported failure — see ${RESULT}"

ok "Result written: ${RESULT}"

# Step 3 — Analyze  [found-analyzer]
step "Step 3 — Analyze results  [found-analyzer]"

if [[ -f "${VENV}/bin/found-analyzer" ]]; then
    "${VENV}/bin/found-analyzer" \
        --result  "${RESULT}" \
        --output  "${REPORT_DIR}"
    ok "Report written: ${REPORT_DIR}/"
else
    warn "found-analyzer not yet in found-tools (coming soon) — skipping"
fi

# Summary
step "Summary"

"${PYTHON}" - "${RESULT}" << 'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
if not d["success"]:
    print(f"  FAILED: {d.get('error','unknown')}")
    sys.exit(1)
print(f"  Edges detected:  {d['num_edges']}")
print(f"  Distance:        {d['distance_m']/1e6:.4f} Mm  ({d['altitude_m']/1e3:.1f} km alt)")
print(f"  Ground truth:    {d['ground_truth_m']/1e6:.4f} Mm")
print(f"  Error:           {d['error_m']/1e3:.2f} km  ({d['error_percent']:.4f}%)")
EOF

echo ""
log "All outputs in: ${OUTPUT_DIR}"