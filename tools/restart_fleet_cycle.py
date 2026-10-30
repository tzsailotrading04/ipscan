import os
import subprocess
import time

# 1. Kill old fleet_cycle processes
out = subprocess.run(["wmic", "process", "where", "CommandLine like '%fleet_cycle.py%' and not CommandLine like '%restart_fleet_cycle%'", "get", "ProcessId"], capture_output=True, text=True)
pids = [line.strip() for line in out.stdout.splitlines() if line.strip().isdigit()]

for pid in pids:
    print(f"Stopping old fleet_cycle PID: {pid}")
    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)

time.sleep(2)

# 2. Launch new fleet_cycle.py
proc = subprocess.Popen(["python", "tools/fleet_cycle.py"], cwd=r"D:\DEpinFarm", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
print(f"RESTARTED_PID: {proc.pid}")
