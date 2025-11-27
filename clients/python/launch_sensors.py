import subprocess
import time
import pathlib

# Correct: go up two levels to reach repo root
ROOT = pathlib.Path(__file__).resolve().parents[2]

sensors = [
    ("voltage", "sensor-voltage"),
    ("current", "sensor-current"),
    ("gas_flow", "sensor-gasflow"),
    ("temperature", "sensor-temperature"),
    ("pressure", "sensor-pressure"),
]

procs = []

print("Launching sensors...\n")

for sensor, cn in sensors:
    script_path = pathlib.Path(__file__).parent / "sensor_client.py"
    cmd = [
        "python3",
        str(script_path),
        "--sensor", sensor,
        "--cn", cn
    ]
    print(f"Starting: {sensor}  (path = {script_path})")
    p = subprocess.Popen(cmd)
    procs.append(p)
    time.sleep(0.2)

print("\nAll sensors launched. Press Ctrl+C to stop.")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping sensors...")
    for p in procs:
        p.terminate()
