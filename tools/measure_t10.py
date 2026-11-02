import subprocess
import datetime
import json
import os
import sys

def main():
    if not os.path.exists("work/fleet_10m_t0.json"):
        print("Error: work/fleet_10m_t0.json not found!")
        return

    with open("work/fleet_10m_t0.json") as f:
        t0_data = json.load(f)

    subprocess.run(["git", "fetch", "origin", "--quiet"])

    t0_ts = t0_data["t0_ts"]
    now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
    dt = max(1.0, now_ts - t0_ts)
    utc_now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print("\n==================== 10-MINUTE FLEET MEASUREMENT (T10) ====================")
    print("Baseline T0 UTC Time :", t0_data["t0_utc"])
    print("Current T10 UTC Time  :", utc_now)
    print(f"Elapsed Interval     : {dt:.1f}s ({dt/60:.2f} min)\n")

    hdr = f"{'Shard':<6} | {'T0 Scan':<11} | {'T10 Scan':<11} | {'Delta Scan':<10} | {'Addr/sec':<9} | {'T0 Gen':<7} | {'T10 Gen':<8} | {'Delta Gen':<9} | {'Gen/1,000':<9}"
    print(hdr)
    print("-" * 105)

    tot_d_scan = 0
    tot_d_gen = 0

    for i in range(20):
        tag = f"{i:02d}"
        ref = f"origin/out/sh{tag}:work/sh{tag}_stats.txt"
        res = subprocess.run(["git", "show", ref], capture_output=True, text=True)
        raw = res.stdout.strip()
        parts = raw.split()
        scanned_10 = 0
        gen_10 = 0
        if res.returncode == 0 and len(parts) >= 3 and parts[1].isdigit():
            scanned_10 = int(parts[1])
            gen_10 = int(parts[2])
        else:
            ref2 = f"origin/out/sh{tag}:ip/harvest/shodan_stats_v98_{tag}.txt"
            res2 = subprocess.run(["git", "show", ref2], capture_output=True, text=True)
            if res2.returncode == 0:
                kv = dict(l.split("=", 1) for l in res2.stdout.splitlines() if "=" in l)
                scanned_10 = int(kv.get("offset", 0))
                gen_10 = int(kv.get("cands", 0))

        s0 = t0_data["shards"].get(f"sh{tag}", {})
        scanned_0 = s0.get("scanned", 0)
        gen_0 = s0.get("genuine", 0)

        d_scan = scanned_10 - scanned_0
        d_gen = gen_10 - gen_0

        tot_d_scan += max(0, d_scan)
        tot_d_gen += max(0, d_gen)

        rate_scan = d_scan / dt
        gen_per_1k = (d_gen / max(1, d_scan)) * 1000.0

        row = f"sh{tag:<4} | {scanned_0:<11} | {scanned_10:<11} | {d_scan:<10} | {rate_scan:<9.2f} | {gen_0:<7} | {gen_10:<8} | {d_gen:<9} | {gen_per_1k:<9.3f}"
        print(row)

    print("-" * 105)
    fleet_rate = tot_d_scan / dt
    fleet_per_1k = (tot_d_gen / max(1, tot_d_scan)) * 1000.0
    print(f"{'TOTAL':<6} | {'-':<11} | {'-':<11} | {tot_d_scan:<10} | {fleet_rate:<9.2f} | {'-':<7} | {'-':<8} | {tot_d_gen:<9} | {fleet_per_1k:<9.3f}\n")

    print("==================== NEWEST PART-FILE PER SHARD BRANCH ====================")
    hdr2 = f"{'Shard':<6} | {'Newest Part File':<42} | {'Line Count':<10}"
    print(hdr2)
    print("-" * 65)

    for i in range(20):
        tag = f"{i:02d}"
        ref = f"origin/out/sh{tag}"
        cmd = ["git", "ls-tree", "-r", "--name-only", ref, "ip/harvest/"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        parts = [f for f in res.stdout.splitlines() if "verified_alive_part" in f]
        best_file = None
        best_ts = -1
        for p in parts:
            if f"_{tag}.txt" in p or f"_{tag}_" in p:
                log_res = subprocess.run(["git", "log", "-1", "--format=%ct", ref, "--", p], capture_output=True, text=True)
                ts = int(log_res.stdout.strip()) if log_res.stdout.strip().isdigit() else 0
                if ts > best_ts:
                    best_ts = ts
                    best_file = p
        if not best_file and parts:
            best_file = parts[0]

        lc = 0
        if best_file:
            show_res = subprocess.run(["git", "show", f"{ref}:{best_file}"], capture_output=True, text=True, errors="ignore")
            lc = len([l for l in show_res.stdout.splitlines() if l.strip()])
        print(f"sh{tag:<4} | {best_file:<42} | {lc:<10}")

    print("\n==================== HARVESTER DAEMON STATUS ====================")
    # Check fleet_cycle.py process
    ps_cmd = ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Process -Filter \"CommandLine like '%fleet_cycle.py%'\" | Select-Object ProcessId, CommandLine"]
    ps_res = subprocess.run(ps_cmd, capture_output=True, text=True)
    print("Harvester Process:")
    print(ps_res.stdout.strip() if ps_res.stdout.strip() else "No active process found!")

    if os.path.exists("work/FLEET_CYCLE.txt"):
        with open("work/FLEET_CYCLE.txt", "r", encoding="utf-8", errors="ignore") as f:
            last_lines = [l.strip() for l in f if l.strip()][-3:]
        print("\nRecent FLEET_CYCLE.txt Entries:")
        for l in last_lines:
            print(f"  {l}")

if __name__ == "__main__":
    main()
