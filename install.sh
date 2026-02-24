#!/usr/bin/env bash
# =============================================================================
# install.sh
#
# Clones found, installs found-tools into a venv, builds the binary.
#
# Usage:
#   bash install.sh
# =============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${ROOT}/.venv"

FOUND_REPO="https://github.com/UWCubeSat/found.git"
FOUND_VERSION="${FOUND_VERSION:-main}"

GREEN='\033[0;32m'; RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'
ok()  { echo -e "${GREEN}  ✓${NC} $*"; }
die() { echo -e "${RED}  ✗${NC} $*"; exit 1; }
log() { echo -e "\n${BOLD}── $* ───────────────────────────────────────────────────${NC}"; }

# ─────────────────────────────────────────────────────────────────────────────
log "System dependencies"
# ─────────────────────────────────────────────────────────────────────────────

for cmd in git cmake python3; do
    command -v "$cmd" &>/dev/null || die "$cmd not found — please install it"
    ok "$cmd: $(command -v "$cmd")"
done

CMAKE_VERSION=$(cmake --version | grep -oE '[0-9]+\.[0-9]+' | head -1)
awk -v v="$CMAKE_VERSION" 'BEGIN{exit(v>=3.16?0:1)}' \
    || die "cmake $CMAKE_VERSION too old — need >= 3.16"
ok "cmake $CMAKE_VERSION >= 3.16"

if command -v g++ &>/dev/null;       then CXX=g++;
elif command -v clang++ &>/dev/null; then CXX=clang++;
else die "No C++ compiler found — install g++ or clang++"; fi
ok "C++ compiler: $CXX"

# ─────────────────────────────────────────────────────────────────────────────
log "Python venv + found-tools"
# ─────────────────────────────────────────────────────────────────────────────

# Create venv — or recreate it if a previous run left it broken
if [[ ! -f "${VENV}/bin/pip" ]]; then
    rm -rf "${VENV}"   # wipe any incomplete venv
    python3 -m venv "${VENV}"
    ok "Created venv: ${VENV}"
else
    ok "Reusing venv: ${VENV}"
fi

# Install found-tools from the add-noise-generator-module branch
# This branch has the actual generator implementation
# Use --ignore-requires-python to bypass Python 3.14 requirement
"${VENV}/bin/pip" install --quiet --ignore-requires-python \
    "git+https://github.com/UWCubeSat/found-tools.git@add-noise-generator-module"
ok "found-tools installed"

# Verify the entry point exists
"${VENV}/bin/found-attitude" --help > /dev/null 2>&1 \
    || die "found-attitude not working — check found-tools install"
ok "found-attitude available"

# ─────────────────────────────────────────────────────────────────────────────
log "Clone vendor/found  (C++ library)"
# ─────────────────────────────────────────────────────────────────────────────

FOUND_DIR="${ROOT}/vendor/found"

if [[ -d "${FOUND_DIR}/.git" ]]; then
    git -C "${FOUND_DIR}" fetch --quiet origin
    git -C "${FOUND_DIR}" checkout --quiet "${FOUND_VERSION}"
else
    mkdir -p "${ROOT}/vendor"
    git clone --branch "${FOUND_VERSION}" "${FOUND_REPO}" "${FOUND_DIR}"
fi
ok "vendor/found @ $(git -C "${FOUND_DIR}" rev-parse --short HEAD)"

# ─────────────────────────────────────────────────────────────────────────────
log "Build found_integration binary  (CMake)"
# ─────────────────────────────────────────────────────────────────────────────

cmake \
    -S "${ROOT}" \
    -B "${ROOT}/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_COMPILER="${CXX}" \
    -DFETCHCONTENT_SOURCE_DIR_FOUND="${FOUND_DIR}"

cmake --build "${ROOT}/build" --parallel "$(nproc 2>/dev/null || echo 4)"

BIN="${ROOT}/build/bin/found_integration"
[[ -f "${BIN}" ]] || die "Build succeeded but binary not found at ${BIN}"
ok "Binary: ${BIN}"

# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "  Done. Run the integration test with:"
echo ""
echo "    ./run.sh --image vendor/found/test/common/assets/example_earth1.png \\"
echo "             --position \"10378137 0 0\" --orientation \"140 0 0\""
echo ""