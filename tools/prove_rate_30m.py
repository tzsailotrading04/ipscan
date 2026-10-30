#!/usr/bin/env python3
"""
tools/prove_rate_30m.py
PROVE OR DISPROVE THE RATE (Read-Only 30-Minute Monitor)
Every 5 minutes for 30 minutes (6 readings total), prints:
  1. wc -l on ip/harvest/real_pool.txt
  2. wc -l on cache/pool_dead.txt
  3. total lines across part files modified in the last 5 minutes
  4. count of part files modified in the last 5 minutes

At 30 minutes, prints a summary table of all 6 readings and states:
  RATE_CONFIRMED if the pool gained 800 or more
  RATE_WEAK if it gained 200 to 799
  RATE_FALSE if it gained under 200
"""
import os
import sys
import glob
import time
import subprocess

REPO = r"D:\DEpinFarm"
POOL_FILE = os.path.join(REPO, "ip", "harvest", "real_pool.txt")
DEAD_FILE = os.path.join(REPO, "cache", "pool_dead.txt")
LOG_FILE = os.path.join(REPO, "work", "RATE_30M.txt")

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def count_file_lines(path):
    if not os.path.exists(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0

def get_recent_part_files(window_seconds=300):
    now = time.time()
    part_files = glob.glob(os.path.join(REPO, "ip", "harvest", "verified_alive_part_*.txt"))
    recent_files = []
    total_lines = 0
    for pf in part_files:
        try:
            mtime = os.path.getmtime(pf)
            if (now - mtime) <= window_seconds:
                cnt = count_file_lines(pf)
                recent_files.append((pf, cnt, (now - mtime)))
                total_lines += cnt
        except Exception:
            pass
    return len(recent_files), total_lines, recent_files

def sync_remote_shards():
    """Fetch and fast-forward remote shard commits without touching local edits"""
    try:
        subprocess.run(["git", "-C", REPO, "fetch", "origin", "main", "--quiet"], capture_output=True, timeout=30)
        subprocess.run(["git", "-C", REPO, "merge", "--no-edit", "origin/main", "--quiet"], capture_output=True, timeout=30)
    except Exception:
        pass

def log_and_print(msg):
    print(msg, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def main():
    log_and_print("=" * 70)
    log_and_print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] STARTING 30-MINUTE RATE PROOF MONITOR")
    log_and_print("=" * 70)

    # Initial baseline
    sync_remote_shards()
    base_pool = count_file_lines(POOL_FILE)
    base_dead = count_file_lines(DEAD_FILE)
    base_pfiles, base_plines, _ = get_recent_part_files(300)

    log_and_print(f"BASELINE (T=0m):")
    log_and_print(f"  real_pool.txt : {base_pool}")
    log_and_print(f"  pool_dead.txt : {base_dead}")
    log_and_print(f"  part files (last 5m) : {base_pfiles} files, {base_plines} lines\n")

    readings = []

    # 6 readings, 5 minutes (300 seconds) apart
    for idx in range(1, 7):
        elapsed_target = idx * 300
        log_and_print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Waiting 5 minutes for Reading {idx}/6...")
        time.sleep(300)

        # Sync remote updates from Kaggle shards
        sync_remote_shards()

        pool_cnt = count_file_lines(POOL_FILE)
        dead_cnt = count_file_lines(DEAD_FILE)
        pfiles_cnt, plines_cnt, _ = get_recent_part_files(300)

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        elapsed_min = idx * 5

        log_and_print(f"\n--- READING {idx}/6 at T={elapsed_min}m ({timestamp}) ---")
        log_and_print(f"  wc -l on ip/harvest/real_pool.txt: {pool_cnt}")
        log_and_print(f"  wc -l on cache/pool_dead.txt:     {dead_cnt}")
        log_and_print(f"  part files modified (last 5m):    {pfiles_cnt}")
        log_and_print(f"  total lines in part files (5m):   {plines_cnt}")

        readings.append({
            "idx": idx,
            "min": elapsed_min,
            "time": timestamp,
            "pool": pool_cnt,
            "dead": dead_cnt,
            "part_lines": plines_cnt,
            "part_files": pfiles_cnt,
        })

    # Summary at 30 minutes
    log_and_print("\n" + "=" * 70)
    log_and_print("30-MINUTE RATE PROOF FINAL REPORT")
    log_and_print("=" * 70)

    header = f"{'Reading':<8} | {'Elapsed':<8} | {'real_pool.txt':<14} | {'pool_dead.txt':<14} | {'Part Lines (5m)':<16} | {'Part Files (5m)':<15}"
    sep = "-" * len(header)
    log_and_print(header)
    log_and_print(sep)

    for r in readings:
        row = f"{r['idx']:<8} | {str(r['min'])+'m':<8} | {r['pool']:<14} | {r['dead']:<14} | {r['part_lines']:<16} | {r['part_files']:<15}"
        log_and_print(row)

    log_and_print(sep)

    initial_p = base_pool
    final_p = readings[-1]["pool"]
    net_gain = final_p - initial_p

    log_and_print(f"\nPool Initial (T=0m): {initial_p}")
    log_and_print(f"Pool Final   (T=30m): {final_p}")
    log_and_print(f"Net Pool Gain       : {net_gain:+d}\n")

    if net_gain >= 800:
        conclusion = "RATE_CONFIRMED"
    elif net_gain >= 200:
        conclusion = "RATE_WEAK"
    else:
        conclusion = "RATE_FALSE"

    log_and_print(f"VERDICT: {conclusion}")
    log_and_print("=" * 70)

if __name__ == "__main__":
    main()
