#!/usr/bin/env python3
"""Call limb's _setup_simulation with hardcoded args."""

from limb.simulation.metadata.orchestrate import setup_simulation

df = setup_simulation(
    semi_axes=[6378137.0, 6378137.0, 6356752.31424518],
    fovs=[5.0, 10.0, 40.0, 60.0, 80.0],
    resolutions=[512, 1024, 2048],
    distances=[6.8e6, 6.9e6, 7.1e6, 7.3e6, 7.7e6, 7.9e6, 8.6e6, 9.4e6, 11e6, 12.6e6, 16e6, 20e6, 25e6, 30e6, 40e6],
    num_earth_points=9,
    num_positions_per_point=7,
    num_spins_per_position=5,
    num_radials_per_spin=2,
    output_path="multi_camera.csv",
)
print(df.shape)
print(df.head())
