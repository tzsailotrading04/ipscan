import subprocess
import datetime
import json
import os

def parse_worker_file_stats(ref, path):
    res = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True, errors="ignore")
    if res.returncode != 0:
        return None
    raw = res.stdout.strip()
    if not raw:
        return None
    
    # Format A: space-separated stats line (iso_time scanned genuine per1000 errno99 other queue_left slice_secs)
    parts = raw.split()
    if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
        return int(parts[1]), int(parts[2])
    
    # Format B: key=value lines
    if "=" in raw:
        kv = dict(l.split("=", 1) for l in raw.splitlines() if "=" in l)
        scanned = int(kv.get("offset", 0)) if kv.get("offset", "").isdigit() else 0
        cands = int(kv.get("cands", 0)) if kv.get("cands", "").isdigit() else 0
        return scanned, cands

    return None

def main():
    subprocess.run(["git", "fetch", "origin", "--quiet"])

    utc_now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()

    print("=== T0 WORKER-SUMMED FLEET MEASUREMENT ===")
    print("UTC Time:", utc_now)
    print()
    hdr = f"{'Shard':<6} | {'w0 Scan':<12} | {'w1 Scan':<12} | {'Sum Scanned':<13} | {'w0 Gen':<8} | {'w1 Gen':<8} | {'Sum Genuine':<11} | {'Source'}"
    print(hdr)
    print("-" * 92)

    shards_data = {}
    tot_scanned = 0
    tot_genuine = 0

    for i in range(20):
        tag = f"{i:02d}"
        ref = f"origin/out/sh{tag}"

        # 1. Try work/shNN_w0_stats.txt and w1
        res0 = parse_worker_file_stats(ref, f"work/sh{tag}_w0_stats.txt")
        res1 = parse_worker_file_stats(ref, f"work/sh{tag}_w1_stats.txt")
        src = "work/sh_w*"

        if res0 is None or res1 is None:
            # 2. Try ip/harvest/shodan_stats_v98_NN_w0.txt and w1
            res0 = parse_worker_file_stats(ref, f"ip/harvest/shodan_stats_v98_{tag}_w0.txt")
            res1 = parse_worker_file_stats(ref, f"ip/harvest/shodan_stats_v98_{tag}_w1.txt")
            src = "ip/harvest_w*"

        w0_s, w0_g = res0 if res0 else (0, 0)
        w1_s, w1_g = res1 if res1 else (0, 0)

        sum_s = w0_s + w1_s
        sum_g = w0_g + w1_g

        tot_scanned += sum_s
        tot_genuine += sum_g

        shards_data[f"sh{tag}"] = {
            "w0_scanned": w0_s,
            "w1_scanned": w1_s,
            "sum_scanned": sum_s,
            "w0_genuine": w0_g,
            "w1_genuine": w1_g,
            "sum_genuine": sum_g,
            "source": src
        }

        print(f"sh{tag:<4} | {w0_s:<12,d} | {w1_s:<12,d} | {sum_s:<13,d} | {w0_g:<8,d} | {w1_g:<8,d} | {sum_g:<11,d} | {src}")

    print("-" * 92)
    print(f"{'TOTAL':<6} | {'-':<12} | {'-':<12} | {tot_scanned:<13,d} | {'-':<8} | {'-':<8} | {tot_genuine:<11,d} |")
    print("-" * 92)

    t0_obj = {
        "t0_utc": utc_now,
        "t0_ts": now_ts,
        "shards": shards_data
    }
    os.makedirs("work", exist_ok=True)
    with open("work/workers_10m_t0.json", "w") as f:
        json.dump(t0_obj, f, indent=2)

if __name__ == "__main__":
    main()
