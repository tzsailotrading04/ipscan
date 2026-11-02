import subprocess
import datetime
import json
import os
import re

def parse_worker_file_stats(ref, path):
    res = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True, errors="ignore")
    if res.returncode != 0:
        return None
    raw = res.stdout.strip()
    if not raw:
        return None
    
    parts = raw.split()
    if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
        return int(parts[1]), int(parts[2])
    
    if "=" in raw:
        kv = dict(l.split("=", 1) for l in raw.splitlines() if "=" in l)
        scanned = int(kv.get("offset", 0)) if kv.get("offset", "").isdigit() else 0
        cands = int(kv.get("cands", 0)) if kv.get("cands", "").isdigit() else 0
        return scanned, cands

    return None

def main():
    if not os.path.exists("work/workers_10m_t0.json"):
        print("Error: work/workers_10m_t0.json not found!")
        return

    with open("work/workers_10m_t0.json") as f:
        t0_data = json.load(f)

    subprocess.run(["git", "fetch", "origin", "--quiet"])

    t0_ts = t0_data["t0_ts"]
    now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
    dt = max(1.0, now_ts - t0_ts)
    utc_now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print("\n==================== 10-MINUTE WORKER-SUMMED FLEET MEASUREMENT (T10) ====================")
    print("Baseline T0 UTC Time :", t0_data["t0_utc"])
    print("Current T10 UTC Time  :", utc_now)
    print(f"Elapsed Interval     : {dt:.1f}s ({dt/60:.2f} min)\n")

    hdr = f"{'Shard':<6} | {'T0 Sum Scan':<12} | {'T10 Sum Scan':<12} | {'Delta Scan':<10} | {'Addr/sec':<9} | {'T0 Gen':<7} | {'T10 Gen':<8} | {'Delta Gen':<9} | {'Gen/1,000':<9}"
    print(hdr)
    print("-" * 105)

    tot_d_scan = 0
    tot_d_gen = 0

    for i in range(20):
        tag = f"{i:02d}"
        ref = f"origin/out/sh{tag}"

        res0 = parse_worker_file_stats(ref, f"work/sh{tag}_w0_stats.txt")
        res1 = parse_worker_file_stats(ref, f"work/sh{tag}_w1_stats.txt")

        if res0 is None or res1 is None:
            res0 = parse_worker_file_stats(ref, f"ip/harvest/shodan_stats_v98_{tag}_w0.txt")
            res1 = parse_worker_file_stats(ref, f"ip/harvest/shodan_stats_v98_{tag}_w1.txt")

        w0_s, w0_g = res0 if res0 else (0, 0)
        w1_s, w1_g = res1 if res1 else (0, 0)

        sum_s10 = w0_s + w1_s
        sum_g10 = w0_g + w1_g

        s0 = t0_data["shards"].get(f"sh{tag}", {})
        sum_s0 = s0.get("sum_scanned", 0)
        sum_g0 = s0.get("sum_genuine", 0)

        d_scan = sum_s10 - sum_s0
        d_gen = sum_g10 - sum_g0

        tot_d_scan += max(0, d_scan)
        tot_d_gen += max(0, d_gen)

        rate_scan = d_scan / dt
        gen_per_1k = (d_gen / max(1, d_scan)) * 1000.0

        row = f"sh{tag:<4} | {sum_s0:<12,d} | {sum_s10:<12,d} | {d_scan:<10,d} | {rate_scan:<9.2f} | {sum_g0:<7,d} | {sum_g10:<8,d} | {d_gen:<9,d} | {gen_per_1k:<9.3f}"
        print(row)

    print("-" * 105)
    fleet_rate = tot_d_scan / dt
    fleet_per_1k = (tot_d_gen / max(1, tot_d_scan)) * 1000.0
    print(f"{'TOTAL':<6} | {'-':<12} | {'-':<12} | {tot_d_scan:<10,d} | {fleet_rate:<9.2f} | {'-':<7} | {'-':<8} | {tot_d_gen:<9,d} | {fleet_per_1k:<9.3f}\n")

    print("==================== LAST THREE FLEET_CYCLE.TXT ENTRIES ====================")
    if os.path.exists("work/FLEET_CYCLE.txt"):
        with open("work/FLEET_CYCLE.txt", "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f if l.strip()]
        last3 = lines[-3:] if len(lines) >= 3 else lines
        for l in last3:
            # Extract new_pool
            m = re.search(r"new_pool=(\d+)", l)
            new_pool_val = m.group(1) if m else "N/A"
            print(f"Entry   : {l}")
            print(f"new_pool: {new_pool_val}\n")
    else:
        print("work/FLEET_CYCLE.txt not found!")

if __name__ == "__main__":
    main()
