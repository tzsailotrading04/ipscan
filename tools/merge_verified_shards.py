import os
import glob
import time
import subprocess

ROOT = r"D:\DEpinFarm"
OUT_REL = "ip/harvest/verified_alive.txt"

def atomic_write(filepath, lines):
    tmp_path = filepath + ".tmp"
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
        for line in lines:
            f.write(line + "\n")
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp_path, filepath)

def run_merge():
    # Sync git
    subprocess.run(["git", "-C", ROOT, "fetch", "origin"], capture_output=True)
    subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "origin", "main"], capture_output=True)

    part_files = sorted(glob.glob(os.path.join(ROOT, "ip", "harvest", "verified_alive_part_*.txt")))
    primary_file = os.path.join(ROOT, OUT_REL)

    all_verified = {}

    # Load from primary file
    if os.path.exists(primary_file):
        with open(primary_file, "r", encoding="utf-8", errors="ignore") as f:
            for l in f:
                parts = l.strip().split("\t")
                if len(parts) >= 2:
                    k = parts[0]
                    seen = int(parts[7]) if len(parts) >= 8 and parts[7].isdigit() else 1
                    prefix = "\t".join(parts[:7])
                    all_verified[k] = (prefix, seen)

    # Load and union all part files
    for pf in part_files:
        with open(pf, "r", encoding="utf-8", errors="ignore") as f:
            for l in f:
                parts = l.strip().split("\t")
                if len(parts) >= 2:
                    k = parts[0]
                    seen = int(parts[7]) if len(parts) >= 8 and parts[7].isdigit() else 1
                    prefix = "\t".join(parts[:7])
                    if k not in all_verified or seen > all_verified[k][1]:
                        all_verified[k] = (prefix, seen)

    total_alive = len(all_verified)
    print(f"Total unioned live proxies across {len(part_files)} verify shards: {total_alive:,}")

    # Write unified outputs
    full_lines = sorted(f"{prefix}\t{seen}" for prefix, seen in all_verified.values())
    atomic_write(primary_file, full_lines)

    pub_file = os.path.join(ROOT, "ip", "pub.txt")
    pub_lines = sorted(all_verified.keys())
    atomic_write(pub_file, pub_lines)

    pub_fast_file = os.path.join(ROOT, "ip", "pub_fast.txt")
    fast_rows = [k for k, (prefix, _) in sorted(all_verified.items()) if "\tFAST" in prefix or "\tMED" in prefix]
    atomic_write(pub_fast_file, fast_rows[:1000])

    print(f"Updated verified_alive.txt ({len(full_lines):,}), pub.txt ({len(pub_lines):,}), pub_fast.txt ({len(fast_rows[:1000]):,})")

if __name__ == "__main__":
    run_merge()
