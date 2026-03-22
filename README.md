bash

```
cmake -S . -B build/ && cmake --build build
uv lock --upgrade-package limb
```

The pipeline binary supports choosing the distance-stage regression via `--regression <alg>` (`tls` | `ols` | `ridge` | `ransac`; default: `tls`). For `ridge` use `--ridge-lambda <λ>`; for `ransac` use `--ransac-residual-threshold`, `--ransac-max-iterations`, and optionally `--ransac-min-samples`. Run `build/bin/pipeline_runner --help` for details.

### run_batch.py

Example CLI calls for each regression option. Required: `--csv`, `--images-dir`, `--binary`, `--output`. Optional: `--max-rows`, `--with-memory`.

**TLS (default):**

```bash
uv run python run_batch.py --csv sim_metadata.csv --images-dir sim_images --binary build/bin/pipeline_runner --output results_tls.csv --regression tls
```

**OLS:**

```bash
uv run python run_batch.py --csv sim_metadata.csv --images-dir sim_images --binary build/bin/pipeline_runner --output results_ols.csv --regression ols
```

**Ridge (default λ = 1e-6):**

```bash
uv run python run_batch.py --csv sim_metadata.csv --images-dir sim_images --binary build/bin/pipeline_runner --output results_ridge.csv --regression ridge
```

With custom λ:

```bash
uv run python run_batch.py --csv sim_metadata.csv --images-dir sim_images --binary build/bin/pipeline_runner --output results_ridge.csv --regression ridge --ridge-lambda 1e-5
```

**RANSAC (defaults: τ=1e-4, max_iter=100, min_samples=0):**

```bash
uv run python run_batch.py --csv sim_metadata.csv --images-dir sim_images --binary build/bin/pipeline_runner --output results_ransac.csv --regression ransac
```

With custom RANSAC options:

```bash
uv run python run_batch.py --csv sim_metadata.csv --images-dir sim_images --binary build/bin/pipeline_runner --output results_ransac.csv --regression ransac --ransac-residual-threshold 5e-5 --ransac-max-iterations 200 --ransac-min-samples 3
```

cra analysis comand

```
uv run python cra_analysis.py \
  --semi-axes 6378137.0 6378137.0 6356752.31424518 \
  --fovs 10.0 \
  --resolutions 512 \
  --distances 7e6 \
  --num-earth-points 1 \
  --num-positions-per-point 3 \
  --num-spins-per-position 4 \
  --num-radials-per-spin 2 \
  --atmosphere-blur 0.0 \
  --false-points 0 \
  --binary build/bin/pipeline_runner \
  --output cra_results.csv \
  --conjugate-quaternion \
  --edge-decimals 0 \
  --seed 42
```

cra analysis comand real

```
uv run python cra_analysis.py \
  --fovs 10.0 40 70 80\
  --resolutions 512 1024 \
  --distances 6.8e6 6.9e6 7e6 7.2e6 7.6e6 8e6\
  --num-earth-points 5 \
  --num-positions-per-point 5 \
  --num-spins-per-position 5 \
  --num-radials-per-spin 3 \
  --atmosphere-blur 0.0 \
  --false-points 0 \
  --output cra_results.csv \
  --edge-decimals 0 \
  --seed 42
```

```
[my-ransac-run]
# ... other keys ...
regression = ransac
ransac_residual_threshold = 5e-5
ransac_max_iterations = 200
ransac_min_samples = 3
Example for ridge:

regression = ridge
ridge_lambda = 1e-5
```

```
uv run python scripts/distance/simulation.py \
  --simulation-file scripts/distance/simulations.txt \
  --simulation-name huge-multi-camera-leo-geo \
  --output results/huge-multi-cam.csv
```

debug

```
uv run scripts/debug_trouble_rows.py 11 --csv results/huge-mulit-cam-angle-noise.csv --edge-decimals 1 --out-dir output
```

image

```
uv run python scripts/csv_to_images.py \
  --csv results/multi-cam-image.csv \
  --output results/plots/multi-cam/pngs \
  --max-rows 200

uv run python scripts/csv_to_images.py \
  --csv results/multi-cam.csv \
  --output results/plots/multi-cam/edges_only \
  --rows 0 42 100 \
  --matplotlib
```

