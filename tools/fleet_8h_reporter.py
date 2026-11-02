#!/usr/bin/env python3
"""
tools/fleet_8h_reporter.py
Runs every 15 minutes for 8 hours (32 iterations).
For each iteration:
- Prints UTC time
- Prints RUNNING per account
- Executes git fetch origin
- Prints summed scanned and genuine from origin/out/shNN
- Prints new_pool from the last three work/FLEET_CYCLE.txt lines
"""

import os
import sys
import time
import json
import subprocess
import datetime

REPO_ROOT = r"D:\DEpinFarm"
FLEET_CYCLE_FILE = os.path.join(REPO_ROOT, "work", "FLEET_CYCLE.txt")
REPORT_LOG = os.path.join(REPO_ROOT, "work", "fleet_8h_report.log")

FLEET_MAP = {
    "lalthazualasailo": {
        "shards": [0, 1, 2, 3, 16],
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct1", "access_token")
    },
    "zomuanpuia": {
        "shards": [4, 5, 6, 7, 17],
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct2", "access_token")
    },
    "laldinthari": {
        "shards": [8, 9, 10, 11, 18],
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct3", "access_token")
    },
    "lalsangkima": {
        "shards": [12, 13, 14, 15, 19],
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct4", "access_token")
    }
}

KAGGLE_JSON = os.path.expanduser(r"~\.kaggle\kaggle.json")

def set_kaggle_creds(username, token):
    os.makedirs(os.path.dirname(KAGGLE_JSON), exist_ok=True)
    with open(KAGGLE_JSON, "w", encoding="utf-8") as f:
        json.dump({"username": username, "key": token}, f, indent=2)
    os.environ["KAGGLE_USERNAME"] = username
    os.environ["KAGGLE_KEY"] = token
    os.environ["KAGGLE_API_TOKEN"] = token

def run_cmd(cmd):
    res = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        cwd=REPO_ROOT
    )
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def parse_stats(ref, path):
    out, err, code = run_cmd(f'git show "{ref}:{path}"')
    if code != 0 or not out:
        return None
    parts = out.split()
    if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
        return int(parts[1]), int(parts[2])
    if "=" in out:
        kv = dict(l.split("=", 1) for l in out.splitlines() if "=" in l)
        s = int(kv.get("offset", 0)) if kv.get("offset", "").isdigit() else 0
        c = int(kv.get("cands", 0)) if kv.get("cands", "").isdigit() else 0
        return s, c
    return None

def get_running_per_account():
    running_counts = {}
    for uname, info in FLEET_MAP.items():
        with open(info["token_file"], "r", encoding="utf-8") as tf:
            tok = tf.read().strip()
        set_kaggle_creds(uname, tok)
        cnt = 0
        for s in info["shards"]:
            ref = f"{uname}/ipscan-cl-shodan-{s:02d}"
            out, err, _ = run_cmd(f"kaggle kernels status {ref}")
            if "RUNNING" in out:
                cnt += 1
        running_counts[uname] = cnt
    return running_counts

def get_origin_stats():
    run_cmd("git fetch origin --quiet")
    tot_scanned = 0
    tot_genuine = 0
    per_shard = {}

    for i in range(20):
        tag = f"{i:02d}"
        ref = f"origin/out/sh{tag}"

        res0 = parse_stats(ref, f"work/sh{tag}_w0_stats.txt")
        res1 = parse_stats(ref, f"work/sh{tag}_w1_stats.txt")
        if res0 is None or res1 is None:
            res0 = parse_stats(ref, f"ip/harvest/shodan_stats_v98_{tag}_w0.txt")
            res1 = parse_stats(ref, f"ip/harvest/shodan_stats_v98_{tag}_w1.txt")

        w0_s, w0_g = res0 if res0 else (0, 0)
        w1_s, w1_g = res1 if res1 else (0, 0)
        s_sum = w0_s + w1_s
        g_sum = w0_g + w1_g

        tot_scanned += s_sum
        tot_genuine += g_sum
        per_shard[tag] = (s_sum, g_sum)

    return tot_scanned, tot_genuine, per_shard

def get_new_pool_last_three():
    if not os.path.exists(FLEET_CYCLE_FILE):
        return ["FLEET_CYCLE.txt not found"]
    with open(FLEET_CYCLE_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = [l.strip() for l in f if l.strip()]
    return lines[-3:] if len(lines) >= 3 else lines

def report_iteration(iter_idx, max_iters):
    utc_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    running_counts = get_running_per_account()
    tot_s, tot_g, per_shard = get_origin_stats()
    last_three = get_new_pool_last_three()

    running_disp = " | ".join([f"{u}: {cnt}/5" for u, cnt in running_counts.items()])
    
    new_pool_vals = []
    for line in last_three:
        for part in line.split():
            if part.startswith("new_pool="):
                new_pool_vals.append(part)

    report_lines = [
        "",
        "=" * 85,
        f"[{utc_str}] FLEET 15-MINUTE REPORT ({iter_idx}/{max_iters})",
        "=" * 85,
        f"RUNNING per account : {running_disp}",
        f"Summed Scanned      : {tot_s:,} (from origin/out/sh00..sh19)",
        f"Summed Genuine      : {tot_g:,} (from origin/out/sh00..sh19)",
        f"new_pool last 3     : {' | '.join(new_pool_vals) if new_pool_vals else 'none'}",
        "-" * 85,
        "Last 3 lines of work/FLEET_CYCLE.txt:"
    ]
    for l in last_three:
        report_lines.append(f"  {l}")
    report_lines.append("=" * 85)

    full_output = "\n".join(report_lines)
    print(full_output, flush=True)

    with open(REPORT_LOG, "a", encoding="utf-8") as rf:
        rf.write(full_output + "\n")

def main():
    max_iters = 32  # 8 hours / 15 minutes = 32 iterations
    interval_seconds = 900  # 15 minutes

    print(f"[{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] Starting 8-Hour Fleet Monitor (PID {os.getpid()})...", flush=True)

    for i in range(1, max_iters + 1):
        try:
            report_iteration(i, max_iters)
        except Exception as e:
            print(f"Exception during report iteration {i}: {e}", file=sys.stderr, flush=True)

        if i < max_iters:
            time.sleep(interval_seconds)

    print("Completed 8-hour reporting session.", flush=True)

if __name__ == "__main__":
    main()
