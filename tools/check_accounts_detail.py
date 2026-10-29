import json
import os
import glob
import time
from datetime import datetime

ROOT = r"D:\DEpinFarm"
SHARDS = [
    ("acct5", ["cl_shodan_00", "cl_shodan_01"]),
    ("acct1", ["cl_shodan_02", "cl_shodan_03", "cl_shodan_04", "cl_shodan_05"]),
    ("acct2", ["cl_shodan_06", "cl_shodan_07", "cl_shodan_08", "cl_shodan_09"]),
    ("acct3", ["cl_shodan_10", "cl_shodan_11", "cl_shodan_12", "cl_shodan_13"]),
    ("acct4", ["cl_shodan_15", "cl_shodan_16", "cl_shodan_17"]),
    ("acct6", ["cl_shodan_14", "cl_shodan_18", "cl_shodan_19"]),
]

now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
print(f"================================================================================")
print(f"KAGGLE 6 ACCOUNTS DETAILED STATUS REPORT ({now_str})")
print(f"Fleet Configuration: v98.170 Budget VPS Subnets (OVH, Hetzner, Contabo, etc.)")
print(f"================================================================================\n")

total_shards = 0
total_alive_fleet = 0

for acct, klist in SHARDS:
    print(f"--------------------------------------------------------------------------------")
    print(f"ACCOUNT: {acct.upper()} (Runs {len(klist)} Kernels: {', '.join(klist)})")
    print(f"--------------------------------------------------------------------------------")
    for k in klist:
        total_shards += 1
        idx = k.split("_")[-1]
        
        # Check progress
        prog_file = os.path.join(ROOT, "ip", "harvest", f"shodan_progress_v98_{idx}.txt")
        offset = "N/A"
        mtime_str = "N/A"
        if os.path.exists(prog_file):
            try:
                offset = open(prog_file).read().strip()
                mt = os.path.getmtime(prog_file)
                age_s = time.time() - mt
                mtime_str = f"{age_s:.0f}s ago"
            except Exception: pass
            
        # Check stats & rate
        stats_file = os.path.join(ROOT, "ip", "harvest", f"shodan_stats_v98_{idx}.txt")
        rate_info = "N/A"
        scanned_ips = "N/A"
        if os.path.exists(stats_file):
            try:
                for line in open(stats_file):
                    line = line.strip()
                    if "rate=" in line or "ips/s" in line:
                        rate_info = line
                    if "ips_scanned=" in line or "scanned=" in line:
                        scanned_ips = line
            except Exception: pass
            
        # Check verified alive proxies found by this shard
        alive_file = os.path.join(ROOT, "ip", "harvest", f"verified_alive_part_{idx}.txt")
        alive_count = 0
        latest_hit = ""
        if os.path.exists(alive_file):
            try:
                lines = [l.strip() for l in open(alive_file) if l.strip()]
                alive_count = len(lines)
                if lines:
                    latest_hit = lines[-1].split()[0]
            except Exception: pass
            
        total_alive_fleet += alive_count
        hit_str = f" | Last Hit: {latest_hit}" if latest_hit else ""
        print(f"  * {k}: Offset: {offset:<10} (Updated {mtime_str}) | Alive Found: {alive_count:<3} {hit_str}")
    print()

print(f"================================================================================")
print(f"TOTAL FLEET: {total_shards} Kernels Active across 6 Accounts | Verified Shard Hits: {total_alive_fleet}")
print(f"================================================================================")
