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

## Pipeline 1:

```
Step 1  tools.generator  (found-tools, generator_env)
        python3 -m tools.generator --position 10378137 0 0 --orientation 140 0 0 ...
        → results/<timestamp>/image.png

Step 2  pipeline_runner  (C++ binary, links found::found_lib)
        ./build/bin/pipeline_runner --image image.png ...
        → results/<timestamp>/result.json

Step 3  tools.analysis  (found-tools, analyzer_env)
        python3 -m tools.analysis --result result.json --output report/
        → results/<timestamp>/report/
```

## pipeline_runner (position output for scripts)

A second binary **pipeline_runner** uses found’s edge + distance pipeline and prints position on a single line for easy capture by bash:

```bash
./build/bin/pipeline_runner --image path/to/earth.png
# stdout: POSITION x y z

# Capture and save
output=$(./build/bin/pipeline_runner --image path/to/earth.png)
echo "$output" > position.txt

# Or use the example script
./scripts/run_and_save.sh --image path/to/earth.png --output position.txt
```

Options: `--image` (required), `--focal-length`, `--pixel-size`, `--radius`, `--output-file`. See `./build/bin/pipeline_runner --help`.

## Files

```
found-integration/
├── CMakeLists.txt         # links found::found_lib via FetchContent
├── install.sh             # clone deps, setup envs, build binary
├── run.sh                 # generator → found_integration → analyzer
├── run_batch.py           # batch driver: CSV + perf/time/valgrind → merged results CSV
├── scripts/
│   └── run_and_save.sh    # example: run pipeline_runner, save position to file
├── docs/
│   └── METRICS.md         # how metrics are collected, Linux requirements
├── src/
│   ├── main.cpp
│   ├── integration_runner.hpp
│   ├── integration_runner.cpp
│   ├── main.cpp                   # edge → distance → POSITION x y z
│   └── options.hpp / options.cpp  # CLI options
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

## Large-scale simulation

For parameter sweeps and metrics (CPU instructions, runtime, optional memory), use [found-tools limb_simulation](https://github.com/UWCubeSat/found-tools) to generate a CSV and images, then run the batch driver in this repo:

1. **Generate CSV + images** (from this repo’s venv after `install.sh`):

   ```bash
   .venv/bin/limb_simulation \
     --fovs 80 70 \
     --resolutions 512 1024 \
     --distances 7000000 8000000 \
     --num-positions-per-point 2 --num-spins-per-position 2 --num-radials-per-spin 2 \
     --output-csv sim_metadata.csv \
     --output-folder sim_images
   ```

2. **Run the batch driver** (Linux; requires `perf` for instruction counts):

   ```bash
   .venv/bin/python run_batch.py \
     --csv sim_metadata.csv \
     --images-dir sim_images \
     --binary build/bin/pipeline_runner \
     --output results.csv
   ```

   Optional: `--with-memory` to collect Valgrind memory stats (slow); `--max-rows N` to limit rows for testing.

   Or use the wrapper (default paths: `sim_metadata.csv`, `sim_images/`, `results.csv`):

   ```bash
   ./run_batch.sh
   ./run_batch.sh --with-memory --max-rows 10
   ```

See [docs/METRICS.md](docs/METRICS.md) for how metrics are collected (perf, time, Valgrind) and Linux requirements.

## Pin versions

```bash
FOUND_VERSION=v2.1.0 FOUND_TOOLS_VERSION=v1.3.0 bash install.sh
```