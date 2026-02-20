#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${ROOT}/.venv"

GREEN='\033[0;32m'; RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
fail() { echo -e "${RED}  ✗${NC} $*"; exit 1; }
log()  { echo -e "\n${BOLD}── $* ─────────────────────────────────────────────────────${NC}"; }

log "Testing found-tools installation"

# Check venv exists
[[ -d "${VENV}" ]] || fail "Venv not found — run: bash install.sh"
ok "Venv exists: ${VENV}"

# Check found-attitude is installed
[[ -f "${VENV}/bin/found-attitude" ]] || fail "found-attitude not installed — run: bash install.sh"
ok "found-attitude binary exists"

# Test found-attitude --help
log "Running: found-attitude --help"
"${VENV}/bin/found-attitude" --help || fail "found-attitude --help failed"
ok "found-attitude --help succeeded"

# Test actual attitude generation
log "Running: found-attitude --local-attitude 45 0 0 --num-attitude-pairs 2"
OUTPUT=$("${VENV}/bin/found-attitude" --local-attitude 45 0 0 --num-attitude-pairs 2)
echo "${OUTPUT}"

# Verify output contains expected sections
echo "${OUTPUT}" | grep -q "CALIBRATION ATTITUDES" || fail "Missing CALIBRATION ATTITUDES section"
ok "Output contains CALIBRATION ATTITUDES"

echo "${OUTPUT}" | grep -q "DISTANCE ATTITUDES" || fail "Missing DISTANCE ATTITUDES section"
ok "Output contains DISTANCE ATTITUDES"

echo "${OUTPUT}" | grep -q "TEST PAIR 1" || fail "Missing TEST PAIR 1"
ok "Output contains TEST PAIR 1"

echo "${OUTPUT}" | grep -q "TEST PAIR 2" || fail "Missing TEST PAIR 2"
ok "Output contains TEST PAIR 2"

log "Success!"
echo ""
echo "  found-tools is properly installed and found-attitude is working."
echo ""