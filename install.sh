#!/usr/bin/env bash
# install.sh — Linux only. Installs found-tools via uv, builds pipeline_runner (depends on UWCubeSat/found via CMake FetchContent).

# Exit on any command failure
set -e

# Executes a command with a banner
execute_cmd() {
    local cmd="$@"
    local middle_line="Command: $cmd"
    local middle_line_len=$(echo -n "$middle_line" | wc -m)
    local extra_chars=20
    local total_length=$((middle_line_len + extra_chars))
    local hash_line=$(printf '%*s' "$total_length" | tr ' ' '=')

    printf "\n"
    printf "%s\n" "$hash_line"
    printf "          %s\n" "$middle_line"
    printf "%s\n" "$hash_line"
    printf "\n"

    # Execute the command and check for errors
    if ! eval "$cmd"; then
        echo "Command failed: $cmd"
        exit 1
    fi
}

# Detect if running as root (UID 0)
if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
fi

# -----------------------------------------------------------------------------
# Defaults (set at top)
# -----------------------------------------------------------------------------
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${ROOT}/.venv"
BUILD_DIR="${ROOT}/build"
BIN="${BUILD_DIR}/bin/pipeline_runner"

# Required software (must be on PATH). See https://github.com/UWCubeSat/found
REQUIRED_CMDS="uv git cmake g++"   # found uses g++ on Linux; cmake >= CMAKE_MIN_VERSION
CMAKE_MIN_VERSION="3.21"           # found's CMake requires 3.21+

# found-tools (Python) — installed via uv into .venv
FOUND_TOOLS_REPO="${FOUND_TOOLS_REPO:-https://github.com/UWCubeSat/found-tools.git}"
FOUND_TOOLS_BRANCH="${FOUND_TOOLS_BRANCH:-main}"

# Detect the operating system using uname
OS="$(uname -s)"

# -----------------------------------------------------------------------------
# Linux only
# -----------------------------------------------------------------------------
case "$OS" in
    Linux*)
        ;;
    *)
        echo "Unknown Operating System $OS"
        echo "install.sh: Linux only"
        exit 1
        ;;
esac

# -----------------------------------------------------------------------------
# Required commands (found uses g++ on Linux: git, cmake 3.21+, g++)
# -----------------------------------------------------------------------------
for cmd in uv git cmake g++; do
    command -v "$cmd" &>/dev/null || { echo "install.sh: required '$cmd' not found"; exit 1; }
done
CMAKE_VER=$(cmake --version | grep -oE '[0-9]+\.[0-9]+' | head -1)
if ! awk -v v="$CMAKE_VER" -v min="${CMAKE_MIN_VERSION}" 'BEGIN{exit(v+0>=min+0?0:1)}'; then
    echo "install.sh: cmake ${CMAKE_MIN_VERSION}+ required (found ${CMAKE_VER})"
    exit 1
fi
CXX=g++

# -----------------------------------------------------------------------------
# Venv + found-tools via uv
# -----------------------------------------------------------------------------
if [ ! -d "${VENV}" ]; then
    execute_cmd uv venv "${VENV}"
fi
execute_cmd uv pip install --python "${VENV}/bin/python" "git+${FOUND_TOOLS_REPO}@${FOUND_TOOLS_BRANCH}"

# -----------------------------------------------------------------------------
# Build (CMake FetchContent pulls UWCubeSat/found; found needs git, cmake, C++ compiler)
# -----------------------------------------------------------------------------
execute_cmd cmake -S "${ROOT}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER="${CXX}"
execute_cmd cmake --build "${BUILD_DIR}" --parallel "$(nproc 2>/dev/null || echo 4)"
[ -f "${BIN}" ] || { echo "install.sh: binary not produced at ${BIN}"; exit 1; }

printf "\n============Done. Binary: %s============\n" "${BIN}"
