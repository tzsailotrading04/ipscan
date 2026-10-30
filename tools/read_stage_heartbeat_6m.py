#!/usr/bin/env python3
import os
import glob
import time
import subprocess

REPO_ROOT = r"D:\DEpinFarm"

def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def main():
    print("=" * 60)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] STEP 5: STAGE HEARTBEAT READ (SHARDS 00, 17, 33)")
    print("=" * 60)

    # Sync from git
    print("Pulling latest updates from origin/main...")
    run_cmd(f'git -C "{REPO_ROOT}" fetch origin main --quiet')
    run_cmd(f'git -C "{REPO_ROOT}" merge --no-edit origin/main --quiet')

    now = time.time()

    # 1. Print stage file for shards 00, 17, 33
    target_shards = ["00", "17", "33"]
    for stag in target_shards:
        stage_file = os.path.join(REPO_ROOT, "ip", "harvest", f"stage_{stag}.txt")
        print(f"\n--- STAGE FILE: stage_{stag}.txt ---")
        if os.path.exists(stage_file):
            mtime = os.path.getmtime(stage_file)
            age = now - mtime
            print(f"(mtime: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))} | age: {age:.1f}s)")
            try:
                with open(stage_file, "r", encoding="utf-8", errors="ignore") as f:
                    print(f.read().strip())
            except Exception as e:
                print(f"Error reading {stage_file}: {e}")
        else:
            print(f"File not found: {stage_file}")

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
        newest_age = now - newest_mtime
        newest_name = os.path.basename(newest_file)
        mtime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(newest_mtime))
        print(f"Newest part file : {newest_name}")
        print(f"mtime            : {mtime_str}")
        print(f"Age              : {newest_age:.1f}s ({newest_age/60:.2f} minutes)")
    else:
        print("No part files found.")

    print("=" * 60)

if __name__ == "__main__":
    main()
