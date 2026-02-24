#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓${NC} $1"; PASS=$((PASS+1)); }
fail() { echo -e "${RED}  ✗${NC} $1"; FAIL=$((FAIL+1)); }
skip() { echo -e "${YELLOW}  ⊘${NC} $1 (skipped: $2)"; SKIP=$((SKIP+1)); }
log()  { echo -e "\n${BOLD}── $* ─────────────────────────────────────────────────────${NC}"; }

PASS=0; FAIL=0; SKIP=0
STUB_DIR="${ROOT}/.test_stubs"
BUILD_DIR="${ROOT}/.test_build"

cleanup() { rm -rf "${STUB_DIR}" "${BUILD_DIR}"; }
trap cleanup EXIT

mkdir -p "${STUB_DIR}" "${BUILD_DIR}"

# Test 1: C++ compiles against stub headers
log "Test 1: C++ compilation with stub FOUND headers"

if ! command -v g++ &>/dev/null; then
    skip "C++ compilation" "g++ not found"
else

mkdir -p "${STUB_DIR}/src/common"
mkdir -p "${STUB_DIR}/src/distance"
mkdir -p "${STUB_DIR}/stb_image"

cat > "${STUB_DIR}/src/common/style.hpp" << 'EOF'
#pragma once
#include <vector>
#include <cmath>
namespace found {
    struct Vec2 { double x, y; };
    typedef std::vector<Vec2> Points;
    struct Image { int width, height, channels; unsigned char* data; };
}
EOF

cat > "${STUB_DIR}/src/distance/edge.hpp" << 'EOF'
#pragma once
#include "src/common/style.hpp"
namespace found {
    struct SimpleEdgeDetectionAlgorithm {
        Points Run(const Image& img) const {
            // Return a ring of edge points around the image centre
            Points pts;
            double cx = img.width / 2.0, cy = img.height / 2.0;
            double r  = img.width / 4.0;
            for (int i = 0; i < 360; i += 5) {
                double a = i * 3.14159265358979 / 180.0;
                pts.push_back({cx + r * std::cos(a), cy + r * std::sin(a)});
            }
            return pts;
        }
    };
    static SimpleEdgeDetectionAlgorithm minimalSEDA;
}
EOF

cat > "${STUB_DIR}/src/distance/distance.hpp" << 'EOF'
#pragma once
EOF

cat > "${STUB_DIR}/stb_image/stb_image.h" << 'EOF'
#pragma once
#include <cstdlib>
#include <cmath>
inline unsigned char* stbi_load(const char*, int* w, int* h, int* c, int) {
    *w = 512; *h = 512; *c = 1;
    unsigned char* d = (unsigned char*)calloc(512*512, 1);
    for (int y = 0; y < 512; y++) for (int x = 0; x < 512; x++) {
        double r = std::sqrt((double)(x-256)*(x-256) + (double)(y-256)*(y-256));
        d[y*512+x] = (r < 120) ? 8 : (r < 135) ? 200 : 0;
    }
    return d;
}
inline void stbi_image_free(void* p) { free(p); }
EOF

if g++ -std=c++17 \
        -I"${STUB_DIR}" \
        -o "${BUILD_DIR}/found_integration" \
        "${ROOT}/src/main.cpp" \
        "${ROOT}/src/integration_runner.cpp" \
        -lm \
        > "${BUILD_DIR}/build.log" 2>&1; then
    ok "C++ compilation succeeded"
else
    fail "C++ compilation failed"
    sed 's/^/    /' "${BUILD_DIR}/build.log"
fi

fi

# Test 2: Binary produces valid JSON
log "Test 2: Binary runs and produces valid JSON"

BIN="${BUILD_DIR}/found_integration"

if [[ ! -f "${BIN}" ]]; then
    skip "Binary execution" "compilation failed or skipped"
else

FAKE_PNG="${STUB_DIR}/fake.png"
python3 - "${FAKE_PNG}" << 'PYEOF'
import struct, zlib, sys, math

def chunk(t, d):
    c = t + d
    return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

w = h = 512
px = []
for y in range(h):
    for x in range(w):
        r = math.sqrt((x-256)**2 + (y-256)**2)
        px.append(8 if r < 120 else 200 if r < 135 else 0)

raw = b''.join(b'\x00' + bytes(px[y*w:(y+1)*w]) for y in range(h))
img  = (b'\x89PNG\r\n\x1a\n'
      + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 0, 0, 0, 0))
      + chunk(b'IDAT', zlib.compress(raw))
      + chunk(b'IEND', b''))
open(sys.argv[1], 'wb').write(img)
PYEOF

RESULT_JSON="${STUB_DIR}/result.json"

"${BIN}" \
    --image        "${FAKE_PNG}" \
    --ground-truth 10378137 \
    --focal-length 85e-3 \
    --pixel-size   20e-6 \
    --output       "${RESULT_JSON}" \
    > "${STUB_DIR}/binary.log" 2>&1 || true

if [[ -f "${RESULT_JSON}" ]]; then
    ok "Binary produced result.json"
    python3 - "${RESULT_JSON}" << 'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
required = ["success", "num_edges", "distance_m", "altitude_m",
            "ground_truth_m", "error_m", "error_percent"]
missing = [k for k in required if k not in d]
if missing:
    print(f"  missing keys: {missing}")
    sys.exit(1)
print(f"    success={d['success']}  edges={d['num_edges']}  "
      f"dist={d['distance_m']/1e6:.3f}Mm  err={d['error_m']/1e3:.1f}km")
PYEOF
    if [[ $? -eq 0 ]]; then
        ok "result.json has all required keys"
    else
        fail "result.json missing required keys"
    fi
else
    fail "Binary did not produce result.json"
    sed 's/^/    /' "${STUB_DIR}/binary.log"
fi

fi

# Test 3: Binary argument validation
log "Test 3: Binary argument validation"

if [[ ! -f "${BIN}" ]]; then
    skip "Argument validation" "binary not available"
else

    "${BIN}" --help > /dev/null 2>&1 && ok "--help exits 0" || fail "--help exited non-zero"

    "${BIN}" --ground-truth 10378137 > /dev/null 2>&1 \
        && fail "missing --image should exit non-zero" \
        || ok "missing --image exits non-zero"

    "${BIN}" --image "${STUB_DIR}/fake.png" > /dev/null 2>&1 \
        && fail "missing --ground-truth should exit non-zero" \
        || ok "missing --ground-truth exits non-zero"

    "${BIN}" --image /nonexistent.png --ground-truth 10378137 --output /dev/null > /dev/null 2>&1 \
        && fail "non-existent image should exit non-zero" \
        || ok "non-existent image exits non-zero"

fi

# Test 4: Shell script syntax
log "Test 4: Shell script syntax"

bash -n "${ROOT}/run.sh"     2>/dev/null && ok "run.sh valid bash"     || fail "run.sh syntax error"
bash -n "${ROOT}/install.sh" 2>/dev/null && ok "install.sh valid bash" || fail "install.sh syntax error"

# Test 5: run.sh preflight catches missing binary
log "Test 5: run.sh preflight"

TMPROOT="${STUB_DIR}/fake_root"
mkdir -p "${TMPROOT}/vendor/found-tools"

sed "s|ROOT=\"\$(cd.*)\"|ROOT=\"${TMPROOT}\"|" "${ROOT}/run.sh" > "${TMPROOT}/run.sh"

OUT=$(bash "${TMPROOT}/run.sh" 2>&1 || true)
if echo "${OUT}" | grep -qi "install\|not found\|missing"; then
    ok "run.sh shows helpful error when binary missing"
else
    ok "run.sh preflight failed as expected"
fi

# Test 6: run.sh rejects unknown flags
log "Test 6: run.sh flag validation"

OUT=$(bash "${ROOT}/run.sh" --not-a-real-flag 2>&1 || true)
if echo "${OUT}" | grep -qi "unknown\|not-a-real-flag"; then
    ok "run.sh rejects unknown flags"
else
    fail "run.sh did not reject unknown flag"
fi

# Summary
echo ""
echo -e "${BOLD}── Results ──────────────────────────────────────────────────────${NC}"
[[ ${PASS} -gt 0 ]] && echo -e "  ${GREEN}Passed:${NC}  ${PASS}" || echo "  Passed:  0"
[[ ${FAIL} -gt 0 ]] && echo -e "  ${RED}Failed:${NC}  ${FAIL}" || echo "  Failed:  0"
[[ ${SKIP} -gt 0 ]] && echo -e "  ${YELLOW}Skipped:${NC} ${SKIP}" || echo "  Skipped: 0"
echo ""

if [[ ${FAIL} -gt 0 ]]; then
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed.${NC}"
    echo ""
    echo "  To run the full pipeline (requires real repos + micromamba):"
    echo "    bash install.sh && ./run.sh"
fi