import csv
import subprocess
import time
import os

csv_path = "results/comprehensive/baseline.csv"
img_dir = "results/comprehensive/baseline_images"
binary = "./pipeline_runner"

with open(csv_path, mode='r') as f:
    reader = csv.DictReader(f)
    print(f"{'Index':<6} | {'Status':<10} | {'Time (s)':<10} | {'Position'}")
    print("-" * 60)

    for i, row in enumerate(reader):
        img_path = os.path.join(img_dir, f"img_{i}.png")
        
        # Updated keys in testing.py
        cmd = [
            binary,
            "--pipeline", "full",
            "--image", img_path,
            "--quat", row['noisy_qw'], row['noisy_qx'], row['noisy_qy'], row['noisy_qz'],
            "--focal-length", row['cam_focal_length'],
            "--pixel-size", row['cam_x_pixel_pitch'],
            "--zernike-refine", "1"  # Change 'true' to '1'
        ]

        start = time.perf_counter()
        result = subprocess.run(cmd, capture_output=True, text=True)
        end = time.perf_counter()

        status = "OK" if result.returncode == 0 else "FAIL"
        print(f"{i:<6} | {status:<10} | {end-start:<10.4f} | {result.stdout.strip()}")