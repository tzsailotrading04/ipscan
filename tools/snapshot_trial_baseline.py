"""
snapshot_trial_baseline.py
Snapshots the exact state of verified proxies, offsets, and candidates
at the start of the 1-hour 2W trial.
"""
import glob
import json
import os
import time

REPO = r"D:\DEpinFarm"
OUT_JSON = os.path.join(REPO, "work", "trial_2w_baseline.json")

def main():
    part_files = glob.glob(os.path.join(REPO, "ip", "harvest", "verified_alive_part_*.txt"))
    per_file = {}
    total_part_lines = 0
    unique_candidates = set()

    for pf in part_files:
        cnt = 0
        fname = os.path.basename(pf)
        with open(pf, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line and ":" in line:
                    cnt += 1
                    unique_candidates.add(line.split()[0].split("\t")[0])
        per_file[fname] = cnt
        total_part_lines += cnt

    real_pool_path = os.path.join(REPO, "ip", "harvest", "real_pool.txt")
    real_pool_count = sum(1 for line in open(real_pool_path, errors="ignore") if line.strip() and ":" in line)

    # Check total offsets across progress files
    prog_files = glob.glob(os.path.join(REPO, "ip", "harvest", "shodan_progress_*.txt"))
    total_offset = 0
    for prog in prog_files:
        try:
            line = open(prog).readline().strip()
            if line.isdigit():
                total_offset += int(line)
        except Exception:
            pass

    data = {
        "start_time_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "start_time_local": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "start_epoch": time.time(),
        "total_part_lines": total_part_lines,
        "unique_candidates": len(unique_candidates),
        "real_pool_count": real_pool_count,
        "total_offset": total_offset,
        "part_files_count": len(part_files),
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print("=== BASELINE SNAPSHOT RECORDED ===")
    print(f"Start Time (UTC)   : {data['start_time_utc']}")
    print(f"Start Time (Local) : {data['start_time_local']}")
    print(f"Total Part Lines   : {data['total_part_lines']:,}")
    print(f"Unique Candidates  : {data['unique_candidates']:,}")
    print(f"Master Real Pool   : {data['real_pool_count']:,}")
    print(f"Total IP Offset    : {data['total_offset']:,}")
    print(f"Saved snapshot to  : {OUT_JSON}")

if __name__ == "__main__":
    main()
