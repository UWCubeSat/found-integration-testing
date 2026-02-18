# found-integration

End-to-end integration testing for FOUND. Wires the Python image generator, the C++ FOUND library, and the Python analyzer into a single pipeline via bash.

## Usage

```bash
# One-time setup
bash install.sh

# Run with defaults
./run.sh

# Run with custom parameters
./run.sh --position "10378137 0 0" --orientation "140 0 0" --focal-length 85e-3
```

## How it works

```
Step 1  tools.generator  (found-tools, generator_env)
        python3 -m tools.generator --position 10378137 0 0 --orientation 140 0 0 ...
        → results/<timestamp>/image.png

Step 2  found_integration  (C++ binary, links found::found_lib)
        ./build/bin/found_integration --image image.png --ground-truth 10378137 ...
        → results/<timestamp>/result.json

Step 3  tools.analysis  (found-tools, analyzer_env)
        python3 -m tools.analysis --result result.json --output report/
        → results/<timestamp>/report/
```

`run.sh` is the only file you need to touch day-to-day. `install.sh` runs once.

## Architecture

**`CMakeLists.txt`** pulls in the `found` repo using the FetchContent pattern from FOUND's own README, and links against `found::found_lib`. The integration binary calls `minimalSEDA.Run()` and the distance algorithm directly — no subprocess, no CLI.

**`src/integration_runner.cpp`** is the bridge: it loads the image, calls FOUND's edge detection, calls FOUND's distance determination, and writes a `result.json` that the analyzer reads.

**`run.sh`** is the orchestrator. It calls `tools.generator` via `micromamba run -n generator_env`, then the C++ binary, then `tools.analysis` via `micromamba run -n analyzer_env`.

**`install.sh`** clones both repos into `vendor/`, runs `found-tools/setup-tools-envs.sh`, and builds the binary with CMake.

## Files

```
found-integration/
├── CMakeLists.txt         # links found::found_lib via FetchContent
├── install.sh             # clone deps, setup envs, build binary
├── run.sh                 # generator → found_integration → analyzer
├── src/
│   ├── main.cpp
│   ├── integration_runner.hpp
│   └── integration_runner.cpp
└── vendor/                # populated by install.sh (gitignored)
    ├── found/
    └── found-tools/
```

## Options

```
./run.sh
  --position     "x y z"        meters      (default: "10378137 0 0")
  --orientation  "de ra roll"   degrees     (default: "140 0 0")
  --focal-length <m>                        (default: 85e-3)
  --pixel-size   <m>                        (default: 20e-6)
  --x-resolution <px>                       (default: 512)
  --y-resolution <px>                       (default: 512)
  --output-dir   <path>                     (default: results/<timestamp>)
```

## Pin versions

```bash
FOUND_VERSION=v2.1.0 FOUND_TOOLS_VERSION=v1.3.0 bash install.sh
```