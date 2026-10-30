#!/usr/bin/env python3
import os
import glob
import time
import subprocess

REPO_ROOT = r"D:\DEpinFarm"
STAGE_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "stage_00.txt")

def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def main():
    print("=" * 60)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] STEP 6: STAGE_00 & PART-FILE AGE CHECK")
    print("=" * 60)

    # Sync git
    print("Fetching and merging latest git updates...")
    run_cmd(f'git -C "{REPO_ROOT}" fetch origin main --quiet')
    run_cmd(f'git -C "{REPO_ROOT}" merge --no-edit origin/main --quiet')

    now = time.time()

    # 1. Print stage_00.txt in full
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

    # 2. Print newest part-file age
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
    else:
        print("No part files found.")

    print("=" * 60)

if __name__ == "__main__":
    main()
