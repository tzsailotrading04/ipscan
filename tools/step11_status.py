#!/usr/bin/env python3
r"""
STEP 11 Metric Verification & work/MORNING.txt Report (v98.180)
Gathers and prints:
- queue files and queue lines
- res, mob, dc subnet counts
- req_s for shards 00 and 20
- real_pool size
- RUNNING sessions per account
Appends cleanly to work/MORNING.txt
"""
import os
import sys
import json
import time
import subprocess
import glob

REPO_ROOT = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser("~/.kaggle/kaggle.json")

FLEET_MAPPING = [
    ("remruata", os.path.join(REPO_ROOT, "kaggle", "acct5", "access_token"), ["00", "01", "20", "21"], True),
    ("lalthazualasailo", os.path.join(REPO_ROOT, "kaggle", "acct1", "access_token"), ["02", "03", "04", "05", "22"], False),
    ("zomuanpuia", os.path.join(REPO_ROOT, "kaggle", "acct2", "access_token"), ["06", "07", "08", "09", "23"], False),
    ("laldinthari", os.path.join(REPO_ROOT, "kaggle", "acct3", "access_token"), ["10", "11", "12", "13", "24"], False),
    ("lalsangkima", os.path.join(REPO_ROOT, "kaggle", "acct4", "access_token"), ["15", "16", "17", "25", "26"], False),
    ("spectatorlone", os.path.join(REPO_ROOT, "kaggle", "acct6", "access_token"), ["14", "18", "19", "27", "28"], False),
    ("stephen34", os.path.join(REPO_ROOT, "kaggle", "stephen34", "access_token"), ["29", "30", "31", "32", "33"], False),
]

def set_credentials(username, token_file):
    with open(token_file, "r", encoding="utf-8") as f:
        token = f.read().strip()
    os.environ["KAGGLE_API_TOKEN"] = token
    os.environ["KAGGLE_USERNAME"] = username
    os.environ["KAGGLE_KEY"] = token
    os.makedirs(os.path.dirname(KAGGLE_JSON), exist_ok=True)
    with open(KAGGLE_JSON, "w", encoding="utf-8") as f:
        json.dump({"username": username, "key": token}, f, indent=2)

def main():
    print("=" * 80)
    print("  STEP 11 METRICS & SYSTEM HEALTH VERIFICATION (v98.180)")
    print("=" * 80)

    # 1. Queue files & lines
    q_dir = os.path.join(REPO_ROOT, "ip", "harvest", "queue")
    q_files = glob.glob(os.path.join(q_dir, "q_*.txt"))
    q_lines = 0
    for qf in q_files:
        try:
            with open(qf, "r", encoding="utf-8", errors="ignore") as f:
                q_lines += sum(1 for line in f if line.strip())
        except Exception:
            pass

    # 2. Subnet counts
    res_file = os.path.join(REPO_ROOT, "data", "res_subnets.txt")
    mob_file = os.path.join(REPO_ROOT, "data", "mob_subnets.txt")
    dc_file = os.path.join(REPO_ROOT, "data", "dc_subnets.txt")

    def count_lines(fp):
        if not os.path.exists(fp): return 0
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for line in f if line.strip() and not line.startswith("#"))

    res_subnets = count_lines(res_file)
    mob_subnets = count_lines(mob_file)
    dc_subnets = count_lines(dc_file)

    # 3. req_s for shards 00 and 20
    def get_req_s(tag):
        sf = os.path.join(REPO_ROOT, "ip", "harvest", f"shodan_stats_v98_{tag}.txt")
        if not os.path.exists(sf): return "N/A"
        try:
            for line in open(sf, errors="ignore"):
                if line.startswith("req_s="):
                    return line.strip().split("=")[1]
        except Exception:
            pass
        return "N/A"

    req_s_00 = get_req_s("00")
    req_s_20 = get_req_s("20")

    # 4. Pool size
    pool_file = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
    pool_size = count_lines(pool_file)

    # 5. Check RUNNING counts per account
    print("Checking Kaggle running session counts per account...")
    running_by_acct = {}
    for username, token_file, shards, has_feed in FLEET_MAPPING:
        set_credentials(username, token_file)
        run_cnt = 0
        for s in shards:
            kernel_id = f"{username}/ipscan-cl-shodan-{s}"
            res = subprocess.run(["kaggle", "kernels", "status", kernel_id], capture_output=True, text=True)
            if "RUNNING" in res.stdout or "QUEUED" in res.stdout:
                run_cnt += 1
        if has_feed:
            feed_res = subprocess.run(["kaggle", "kernels", "status", f"{username}/ipscan-cl-feed"], capture_output=True, text=True)
            if "RUNNING" in feed_res.stdout or "QUEUED" in feed_res.stdout:
                run_cnt += 1
        running_by_acct[username] = run_cnt

    # Print summary
    print("\n--- METRIC REPORT ---")
    print(f"  Queue Files:            {len(q_files)}")
    print(f"  Queue Lines:            {q_lines:,}")
    print(f"  Residential Subnets:    {res_subnets:,}")
    print(f"  Mobile Subnets:         {mob_subnets:,}")
    print(f"  Datacenter Subnets:     {dc_subnets:,}")
    print(f"  req_s Shard 00:         {req_s_00}")
    print(f"  req_s Shard 20:         {req_s_20}")
    print(f"  Verified Pool Size:     {pool_size:,}")
    print("\n  RUNNING per Account:")
    for username, _, _, _ in FLEET_MAPPING:
        print(f"    {username:<18}: {running_by_acct.get(username, 0)}/5")

    # Append to work/MORNING.txt
    morning_file = os.path.join(REPO_ROOT, "work", "MORNING.txt")
    ts_now = time.strftime("%Y-%m-%d %H:%M:%S")
    report_block = f"""
================================================================================
BRIEF v98.180 15-MINUTE SYSTEM PROOF - {ts_now}
================================================================================
Queue Files:         {len(q_files)}
Queue Lines:         {q_lines}
Residential Subnets: {res_subnets:,}
Mobile Subnets:      {mob_subnets:,}
Datacenter Subnets:  {dc_subnets:,}
req_s Shard 00:      {req_s_00}
req_s Shard 20:      {req_s_20}
Verified Pool Size:  {pool_size:,}
RUNNING Sessions:
"""
    for username, _, _, _ in FLEET_MAPPING:
        report_block += f"  {username:<18}: {running_by_acct.get(username, 0)}/5\n"
    report_block += "================================================================================\n"

    with open(morning_file, "a", encoding="utf-8") as mf:
        mf.write(report_block)

    print(f"\nAppended proof report to {morning_file}.")
    print("DONE")

if __name__ == "__main__":
    main()
