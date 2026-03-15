#!/usr/bin/env bash
# install.sh — Installs deps (uv, git, cmake, g++/gcc), then found-tools via uv and builds pipeline_runner (UWCubeSat/found via CMake FetchContent).

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

# Fail if not running Linux
if [ "$(uname -s)" != "Linux" ]; then
    echo "Error: This script requires Linux. Detected: $(uname -s)"
    exit 1
fi

# Detect if running as root (UID 0)
if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
fi

# -----------------------------------------------------------------------------
# Detect package manager and set INSTALL + PACKAGES 
# -----------------------------------------------------------------------------

# Detect the package manager
if command -v apt-get &> /dev/null; then
    PM="$SUDO apt-get"
    execute_cmd $SUDO apt-get -y update
    execute_cmd $SUDO apt-get -y dist-upgrade
elif command -v yum &> /dev/null; then
    PM="$SUDO yum"
    execute_cmd $SUDO yum -y update
else
    echo "No known package manager found"
    exit 1
fi
INSTALL="$PM install -y"
# List of packages to install
PACKAGES="git g++ make valgrind"

# Install each package and echo the command
for PACKAGE in $PACKAGES; do
    CMD="$INSTALL $PACKAGE"
    execute_cmd $CMD
done

# found-tools (Python) — installed via uv into .venv
FOUND_TOOLS_REPO="${FOUND_TOOLS_REPO:-https://github.com/UWCubeSat/found-tools.git}"
FOUND_TOOLS_BRANCH="${FOUND_TOOLS_BRANCH:-main}"

# Default VENV to current-dir .venv if unset (e.g. in Docker or first run)
VENV="${VENV:-$(pwd)/.venv}"
if [[ ! -d "${VENV}" ]]; then
    execute_cmd uv venv "$VENV"
fi

execute_cmd uv pip install --python "${VENV}/bin/python" "git+${FOUND_TOOLS_REPO}@${FOUND_TOOLS_BRANCH}"

printf "\n============Done.============\n"
