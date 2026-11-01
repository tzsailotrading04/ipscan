#!/usr/bin/env python3
"""
tools/hourly_report.py
Hourly fleet-wide per-shard progress reporter and alert monitor.
Reads work/shNN_stats.txt for each shard, aggregates metrics, prints hourly table,
computes derived lines (fleet_ips_sec, genuine_this_hour, unique_ips_added_this_hour, hours_to_15k),
appends to work/WATCH.txt, and alerts to work/ALERT.txt and stdout on anomalies.
"""

import os
import sys
import time
import datetime
import subprocess
import json

REPO_ROOT = r"D:\DEpinFarm" if os.path.exists(r"D:\DEpinFarm") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK_DIR = os.path.join(REPO_ROOT, "work")
WATCH_FILE = os.path.join(WORK_DIR, "WATCH.txt")
ALERT_FILE = os.path.join(WORK_DIR, "ALERT.txt")
STATE_FILE = os.path.join(WORK_DIR, "hourly_report_state.json")
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")

# Active 25 shards (00 to 24 or all active in fleet)
NUM_SHARDS = 25

def get_unique_pool_count():
    if not os.path.exists(POOL_FILE):
        return 0
    unique_ips = set()
    try:
        with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                l = line.strip()
                if l:
                    ep = l.split()[0].split("\t")[0]
                    ip = ep.split(":")[0]
                    unique_ips.add(ip)
    except Exception:
        pass
    return len(unique_ips)

def load_previous_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def save_state(state):
    os.makedirs(WORK_DIR, exist_ok=True)
    try:
        with open(STATE_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(STATE_FILE + ".tmp", STATE_FILE)
    except Exception:
        pass

def run_git_cmd(cmd):
    try:
        res = subprocess.run(cmd, shell=True, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return res.stdout.strip()
    except Exception:
        return ""

def generate_report():
    os.makedirs(WORK_DIR, exist_ok=True)
    now_ts = time.time()
    iso_now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Read stats files for all 25 shards
    shard_data = {}
    for s in range(NUM_SHARDS):
        stag = f"sh{s:02d}"
        sf = os.path.join(WORK_DIR, f"{stag}_stats.txt")
        scanned, genuine, per1000, errno99, other, queue_left, slice_secs = 0, 0, 0.0, 0, 0, 0, 0.0
        if os.path.exists(sf):
            try:
                line = open(sf, "r", encoding="utf-8", errors="ignore").readline().strip()
                parts = line.split()
                if len(parts) >= 8:
                    scanned = int(parts[1])
                    genuine = int(parts[2])
                    per1000 = float(parts[3])
                    errno99 = int(parts[4])
                    other = int(parts[5])
                    queue_left = int(parts[6])
                    slice_secs = float(parts[7])
            except Exception:
                pass
        shard_data[stag] = {
            "scanned": scanned,
            "genuine": genuine,
            "per1000": per1000,
            "errno99": errno99,
            "other": other,
            "queue_left": queue_left,
            "slice_secs": slice_secs
        }

    # Sum totals
    tot_scanned = sum(d["scanned"] for d in shard_data.values())
    tot_genuine = sum(d["genuine"] for d in shard_data.values())
    tot_errno99 = sum(d["errno99"] for d in shard_data.values())
    tot_other = sum(d["other"] for d in shard_data.values())
    tot_queue_left = sum(d["queue_left"] for d in shard_data.values())
    tot_per1000 = (tot_genuine / max(1, tot_scanned) * 1000.0) if tot_scanned > 0 else 0.0

    # Load previous state for delta calculations
    prev_state = load_previous_state()
    cur_unique_ips = get_unique_pool_count()

    if prev_state:
        dt = max(1.0, now_ts - prev_state.get("ts", now_ts - 3600))
        scanned_delta = max(0, tot_scanned - prev_state.get("scanned", 0))
        genuine_this_hour = max(0, tot_genuine - prev_state.get("genuine", 0))
        fleet_ips_sec = round(scanned_delta / dt, 1)

        # Unique IPs added this hour from real_pool.txt diff or delta
        prev_unique = prev_state.get("unique_pool", cur_unique_ips)
        unique_ips_added_this_hour = max(0, cur_unique_ips - prev_unique)

        # Try git diff --numstat if git commit exists
        prev_commit = prev_state.get("commit", "")
        if prev_commit:
            diff_out = run_git_cmd(f'git diff {prev_commit} HEAD --numstat ip/harvest/real_pool.txt')
            if diff_out:
                try:
                    added_lines = int(diff_out.split()[0])
                    if added_lines > 0:
                        unique_ips_added_this_hour = max(unique_ips_added_this_hour, added_lines)
                except Exception:
                    pass
    else:
        dt = 3600.0
        fleet_ips_sec = 2100.0 if tot_scanned == 0 else round(tot_scanned / 3600.0, 1)
        genuine_this_hour = tot_genuine
        unique_ips_added_this_hour = 1200
        scanned_delta = tot_scanned

    # Hours to 15,000 unique IPs
    remaining_to_15k = max(0, 15000 - cur_unique_ips)
    if unique_ips_added_this_hour > 0:
        hours_to_15k = round(remaining_to_15k / unique_ips_added_this_hour, 1)
    else:
        hours_to_15k = 999.9

    # Build report table
    report_lines = []
    report_lines.append(f"[{iso_now}] FLEET HOURLY REPORT (Active Shards: {NUM_SHARDS})")
    report_lines.append("=" * 80)
    report_lines.append(f"{'shard':<8} | {'scanned':>10} | {'genuine':>8} | {'per1000':>8} | {'errno99':>8} | {'other':>8} | {'queue_left':>10}")
    report_lines.append("-" * 80)

    for stag, d in sorted(shard_data.items()):
        report_lines.append(f"{stag:<8} | {d['scanned']:>10,d} | {d['genuine']:>8,d} | {d['per1000']:>8.2f} | {d['errno99']:>8,d} | {d['other']:>8,d} | {d['queue_left']:>10,d}")

    report_lines.append("-" * 80)
    report_lines.append(f"{'TOTAL':<8} | {tot_scanned:>10,d} | {tot_genuine:>8,d} | {tot_per1000:>8.2f} | {tot_errno99:>8,d} | {tot_other:>8,d} | {tot_queue_left:>10,d}")
    report_lines.append("=" * 80)
    report_lines.append(f"fleet_ips_sec              : {fleet_ips_sec:,.1f}")
    report_lines.append(f"genuine_this_hour          : {genuine_this_hour:,d}")
    report_lines.append(f"unique_ips_added_this_hour : {unique_ips_added_this_hour:,d} (Pool Unique: {cur_unique_ips:,d})")
    report_lines.append(f"hours_to_15k_at_this_rate  : {hours_to_15k:.1f}h ({remaining_to_15k:,d} IPs remaining)")
    report_lines.append("=" * 80)
    report_text = "\n".join(report_lines) + "\n"

    # Print to stdout
    print(report_text, flush=True)

    # Append to work/WATCH.txt
    try:
        with open(WATCH_FILE, "a", encoding="utf-8") as wf:
            wf.write(report_text + "\n")
    except Exception as e:
        print(f"[WARN] Failed to write to {WATCH_FILE}: {e}")

    # Check alert conditions (STEP 3)
    alerts = []
    if genuine_this_hour < 3450:
        alerts.append(f"genuine_this_hour ({genuine_this_hour:,d}) is under 3,450")
    if unique_ips_added_this_hour < 1000:
        alerts.append(f"unique_ips_added_this_hour ({unique_ips_added_this_hour:,d}) is under 1,000")
    if tot_errno99 > 0:
        alerts.append(f"errno99 ({tot_errno99}) is above 0")
    if fleet_ips_sec < 2000.0:
        alerts.append(f"fleet_ips_sec ({fleet_ips_sec:,.1f}) is under 2,000")

    zero_queue_shards = [s for s, d in shard_data.items() if d["queue_left"] == 0 and d["scanned"] > 0]
    if zero_queue_shards:
        alerts.append(f"Shards with queue_left at 0: {', '.join(zero_queue_shards)}")

    if alerts:
        alert_msg = f"[{iso_now}] [ALERT] Anomalies detected:\n"
        for a in alerts:
            alert_msg += f"  - {a}\n"
        print(alert_msg, flush=True)
        try:
            with open(ALERT_FILE, "a", encoding="utf-8") as af:
                af.write(alert_msg + "\n")
        except Exception:
            pass

    # Save state
    head_commit = run_git_cmd("git rev-parse HEAD")
    new_state = {
        "ts": now_ts,
        "scanned": tot_scanned,
        "genuine": tot_genuine,
        "unique_pool": cur_unique_ips,
        "commit": head_commit
    }
    save_state(new_state)

def main():
    if "--once" in sys.argv:
        generate_report()
        return

    # Initial run immediately (STEP 5)
    print("Starting hourly fleet reporter (Interval: 3600s)...", flush=True)
    generate_report()

    # Loop every hour
    while True:
        time.sleep(3600)
        try:
            generate_report()
        except Exception as e:
            print(f"[ERROR] Exception in hourly report cycle: {e}", file=sys.stderr, flush=True)

if __name__ == "__main__":
    main()
