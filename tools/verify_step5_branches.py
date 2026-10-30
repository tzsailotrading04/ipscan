#!/usr/bin/env python3
import os
import glob
import time
import subprocess
from tools.fleet_cycle import merge_out_branches

REPO_ROOT = r"D:\DEpinFarm"
STAGE_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "stage_00.txt")

def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def take_reading(label):
    print("=" * 60)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {label}")
    print("=" * 60)

    # 1. Run merge of all out/sh* branches
    print("Merging out/sh* branches into main...")
    merge_out_branches()

    now = time.time()

    # 2. Print stage_00.txt in full
    print("\n--- stage_00.txt FULL CONTENT ---")
    if os.path.exists(STAGE_FILE):
        mtime = os.path.getmtime(STAGE_FILE)
        age = now - mtime
        print(f"mtime: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))} | age: {age:.1f}s ({age/60:.2f}m)")
        print("-" * 40)
        with open(STAGE_FILE, "r", encoding="utf-8", errors="ignore") as f:
            print(f.read().strip())
        print("-" * 40)
    else:
        print(f"File not found: {STAGE_FILE}")

    # 3. Print newest part-file age
    print("\n--- NEWEST PART-FILE CHECK ---")
    part_files = glob.glob(os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive_part_*.txt"))
    newest_file = None
    newest_mtime = 0
    for pf in part_files:
        try:
            m = os.path.getmtime(pf)
            if m > newest_mtime:
                newest_mtime = m
                newest_file = pf
        except Exception:
            pass

    if newest_file:
        newest_name = os.path.basename(newest_file)
        newest_age = now - newest_mtime
        mtime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(newest_mtime))
        print(f"Newest part-file : {newest_name}")
        print(f"Part-file mtime  : {mtime_str}")
        print(f"Part-file age    : {newest_age:.1f}s ({newest_age/60:.2f}m)")
        verdict = "PASSED (< 180s)" if newest_age <= 180 else "PENDING (> 180s)"
        print(f"Status           : {verdict}")
    else:
        print("No part files found.")

    print("=" * 60)
    return newest_age if newest_file else 999999

def main():
    # Reading 1 at 6 minutes (360s)
    print("Starting STEP 5 timer: waiting 360s (6 minutes) for Reading 1...")
    time.sleep(360)
    take_reading("READING 1 AT 6 MINUTES")

    # Reading 2 at 10 minutes (+240s)
    print("\nWaiting 240s (to reach 10 minutes) for Reading 2...")
    time.sleep(240)
    age_10m = take_reading("READING 2 AT 10 MINUTES")

    if age_10m <= 180:
        print(f"\nFINAL VERDICT: PASSED (Age {age_10m:.1f}s is under 180s)")
    else:
        print(f"\nFINAL VERDICT: FAILED (Age {age_10m:.1f}s is above 180s)")

if __name__ == "__main__":
    main()
