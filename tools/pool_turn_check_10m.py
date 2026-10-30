#!/usr/bin/env python3
import os
import glob
import time
import subprocess

REPO_ROOT = r"D:\DEpinFarm"
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")

def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def take_reading(reading_label):
    print(f"\n==================================================", flush=True)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {reading_label}", flush=True)
    print(f"==================================================", flush=True)

    # Sync git to get newest commits / part files from Kaggle shards
    run_cmd(f'git -C "{REPO_ROOT}" fetch origin main --quiet')
    run_cmd(f'git -C "{REPO_ROOT}" merge --no-edit origin/main --quiet')

    now = time.time()

    # 1. Pool size
    pool_size = 0
    if os.path.exists(POOL_FILE):
        with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
            pool_size = sum(1 for l in f if l.strip())

    # 2. Newest part file and age
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

    newest_name = os.path.basename(newest_file) if newest_file else "None"
    newest_age = (now - newest_mtime) if newest_file else 999999
    mtime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(newest_mtime)) if newest_mtime else "N/A"

    print(f"Pool size (real_pool.txt) : {pool_size}", flush=True)
    print(f"Newest part-file          : {newest_name}", flush=True)
    print(f"Part-file mtime           : {mtime_str}", flush=True)
    print(f"Part-file age             : {newest_age:.1f}s ({newest_age/60:.2f}m)", flush=True)

    return pool_size, newest_age

def main():
    pool_sizes = []
    part_ages = []

    # Reading 1: NOW (T=0m)
    p1, a1 = take_reading("READING 1: NOW (T=0m)")
    pool_sizes.append(p1)
    part_ages.append(a1)

    # Wait 5 minutes (300s)
    print(f"\n[{time.strftime('%H:%M:%S')}] Waiting 5 minutes (300s) for Reading 2...", flush=True)
    time.sleep(300)

    # Reading 2: at 5 minutes (T=5m)
    p2, a2 = take_reading("READING 2: AT 5 MINUTES (T=5m)")
    pool_sizes.append(p2)
    part_ages.append(a2)

    # Wait 5 minutes (300s)
    print(f"\n[{time.strftime('%H:%M:%S')}] Waiting 5 minutes (300s) for Reading 3...", flush=True)
    time.sleep(300)

    # Reading 3: at 10 minutes (T=10m)
    p3, a3 = take_reading("READING 3: AT 10 MINUTES (T=10m)")
    pool_sizes.append(p3)
    part_ages.append(a3)

    # Final verdict
    print(f"\n==================================================", flush=True)
    print(f"10-MINUTE POOL TURN SUMMARY", flush=True)
    print(f"==================================================", flush=True)
    print(f"Reading 1 (T=0m)  : Pool={pool_sizes[0]}, Part Age={part_ages[0]:.1f}s", flush=True)
    print(f"Reading 2 (T=5m)  : Pool={pool_sizes[1]}, Part Age={part_ages[1]:.1f}s", flush=True)
    print(f"Reading 3 (T=10m) : Pool={pool_sizes[2]}, Part Age={part_ages[2]:.1f}s", flush=True)

    pool_rose = (pool_sizes[1] > pool_sizes[0]) or (pool_sizes[2] > pool_sizes[1]) or (pool_sizes[2] > pool_sizes[0])

    if pool_rose:
        verdict = "POOL_TURNING"
    else:
        verdict = "POOL_STILL_FALLING"

    print(f"VERDICT: {verdict}", flush=True)
    print(f"==================================================\n", flush=True)

if __name__ == "__main__":
    main()
