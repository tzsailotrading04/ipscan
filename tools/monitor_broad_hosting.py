"""
monitor_broad_hosting.py
Pulls the latest fleet metrics and computes:
1. Fleet aggregate scan speed (IPs/s)
2. Total errno99 across all shards (triggers backoff warning if > 0)
3. Total genuine proxies found in the 35M broad hosting pass
4. Yield per provider (ranking dead vs producing providers)
5. Revised hours to reach 30,000 genuine proxies
"""
import glob
import os
import subprocess
import time
from collections import Counter

ROOT = r"D:\DEpinFarm"

def pull_latest():
    subprocess.run(["git", "-C", ROOT, "fetch", "origin", "main", "--quiet"], capture_output=True)
    subprocess.run(["git", "-C", ROOT, "pull", "--no-edit", "-s", "ort", "-X", "ours", "origin", "main", "--quiet"], capture_output=True)

def main():
    pull_latest()
    
    total_offset = 0
    total_ips = 35060992
    total_req_s = 0.0
    total_errno99 = 0
    total_cands = 0
    active_shards = 0
    workers_per_shard = {}

    for i in range(20):
        stag = f"{i:02d}"
        s_path = os.path.join(ROOT, "ip", "harvest", f"shodan_stats_v98_{stag}.txt")
        if os.path.exists(s_path):
            active_shards += 1
            for line in open(s_path, errors="ignore"):
                if line.startswith("offset="): total_offset += int(line.split("=")[1])
                elif line.startswith("cands="): total_cands += int(line.split("=")[1])
                elif line.startswith("errno99="): total_errno99 += int(line.split("=")[1])
                elif line.startswith("req_s="): total_req_s += float(line.split("=")[1])
                elif line.startswith("workers="): workers_per_shard[stag] = int(line.split("=")[1])

    # Convert raw requests/sec to IPs/sec (since DIRECT_PORTS = 5)
    # req_s was offset * 5 / dt, so IPs/sec = req_s / 5
    # or if req_s is measured in IP/s, compute accordingly:
    fleet_ips_per_sec = total_req_s / 5.0 if total_req_s > 0 else 0.0

    # Parse yield per provider from newly added lines in verified_alive_part_*.txt
    cmd = ["git", "-C", ROOT, "diff", "787775c67..HEAD", "--", "ip/harvest/verified_alive_part_*.txt"]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout

    provider_counts = Counter()
    total_new_proxies = 0

    for line in out.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            parts = line[1:].strip().split("\t")
            if parts and ":" in parts[0]:
                total_new_proxies += 1
                prov = parts[4].strip() if len(parts) >= 5 else "UNKNOWN"
                provider_counts[prov] += 1

    # Also check existing part files for broad hosting format
    if total_new_proxies == 0:
        for pf in glob.glob(os.path.join(ROOT, "ip", "harvest", "verified_alive_part_*_w*.txt")):
            for line in open(pf, errors="ignore"):
                parts = line.strip().split("\t")
                if parts and ":" in parts[0]:
                    total_new_proxies += 1
                    prov = parts[4].strip() if len(parts) >= 5 else "UNKNOWN"
                    provider_counts[prov] += 1

    # Yield metrics
    yield_per_1k = (total_new_proxies / max(1, total_offset)) * 1000 if total_offset > 0 else 0.0
    
    # Hours to 30,000 genuine proxies:
    # Rate of finding proxies per second = fleet_ips_per_sec * (yield_per_1k / 1000)
    proxies_per_sec = fleet_ips_per_sec * (yield_per_1k / 1000.0)
    remaining_to_30k = max(0, 30000 - 3420 - total_new_proxies)
    hours_to_30k = (remaining_to_30k / max(0.001, proxies_per_sec)) / 3600.0 if proxies_per_sec > 0 else 999.0

    print("=" * 70)
    print("35M BROAD HOSTING PASS - SPEEDUP & YIELD MONITOR")
    print("=" * 70)
    print(f"Total Broad Hosting IPs Scanned: {total_offset:,} / {total_ips:,} ({total_offset/total_ips*100:.2f}%)")
    print(f"Fleet Aggregate Scan Speed:      {fleet_ips_per_sec:,.1f} IPs/s ({total_req_s:,.1f} req/s)")
    print(f"Total Errno 99 (Port Exhaustion):{total_errno99}")
    print(f"Active Worker Processes:         {sum(workers_per_shard.values())} processes across {active_shards} shards")
    print(f"Total Genuine Proxies Found:     {total_new_proxies:,}")
    print(f"Live Genuine Yield:              {yield_per_1k:.4f} proxies / 1,000 IPs")
    print(f"Revised Time to 30,000 Proxies:  {hours_to_30k:.1f} hours ({remaining_to_30k:,} needed)")
    print("-" * 70)
    print("YIELD PER PROVIDER (Dead vs Producing):")
    if provider_counts:
        for prov, cnt in provider_counts.most_common(15):
            print(f"  {prov:<24}: {cnt:4,} proxies ({(cnt/total_new_proxies)*100:5.1f}%)")
    else:
        print("  Collecting first batch of provider results from shards...")
    print("=" * 70)

if __name__ == "__main__":
    main()
