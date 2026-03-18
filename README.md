bash

```
cmake -S . -B build/ && cmake --build build
uv lock --upgrade-package limb
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

