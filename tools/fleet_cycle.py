#!/usr/bin/env python3
"""
Fleet Cycle - 15-Minute Fleet Supervisor & Harvest Aggregator
Supervises all 34 Kaggle shards across 7 accounts every 900 seconds.
Revives dead/completed shards (with 10-minute cooldown).
Deduplicates verified_alive_part_*.txt into real_pool.txt against harvest_seen_set.txt.
Never touches work/STOP_SHODAN.
"""
import os
import sys
import glob
import json
import time
import subprocess

REPO_ROOT = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser("~/.kaggle/kaggle.json")
CYCLE_LOG = os.path.join(REPO_ROOT, "work", "FLEET_CYCLE.txt")
SEEN_FILE = os.path.join(REPO_ROOT, "cache", "harvest_seen_set.txt")
QUEUE_FILE = os.path.join(REPO_ROOT, "cache", "candidate_queue.txt")
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")

# Account Shard Assignments (All 34 shards, max 5 per account)
FLEET_MAP = {
    "remruata": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct5", "access_token"),
        "shards": [0, 1, 20, 21]
    },
    "lalthazualasailo": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct1", "access_token"),
        "shards": [2, 3, 4, 5, 22]
    },
    "zomuanpuia": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct2", "access_token"),
        "shards": [6, 7, 8, 9, 23]
    },
    "laldinthari": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct3", "access_token"),
        "shards": [10, 11, 12, 13, 24]
    },
    "lalsangkima": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct4", "access_token"),
        "shards": [15, 16, 17, 25, 26]
    },
    "spectatorlone": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct6", "access_token"),
        "shards": [14, 18, 19, 27, 28]
    },
    "stephen34": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "stephen34", "access_token"),
        "shards": [29, 30, 31, 32, 33]
    }
}

pushed_timestamps = {}

def set_kaggle_creds(username, token):
    os.makedirs(os.path.dirname(KAGGLE_JSON), exist_ok=True)
    with open(KAGGLE_JSON, "w", encoding="utf-8") as f:
        json.dump({"username": username, "key": token}, f, indent=2)
    os.environ["KAGGLE_USERNAME"] = username
    os.environ["KAGGLE_KEY"] = token
    os.environ["KAGGLE_API_TOKEN"] = token

def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def load_seen_set():
    seen = set()
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line:
                    seen.add(line.split("\t")[0].split()[0])
    return seen

def harvest_and_dedupe(seen):
    new_entries = []
    part_files = glob.glob(os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive_part_*.txt"))
    
    for pf in part_files:
        try:
            with open(pf, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    endpoint = raw.split("\t")[0].split()[0]
                    if endpoint not in seen:
                        seen.add(endpoint)
                        new_entries.append(raw)
        except Exception:
            pass

    if new_entries:
        # Append new part-file lines to cache/candidate_queue.txt instead of real_pool.txt
        os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)
        with open(QUEUE_FILE, "a", encoding="utf-8") as qf:
            for entry in new_entries:
                qf.write(entry + "\n")

        # Keep the seen-set dedupe: append to cache/harvest_seen_set.txt
        os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
        with open(SEEN_FILE, "a", encoding="utf-8") as sf:
            for entry in new_entries:
                endpoint = entry.split("\t")[0].split()[0]
                sf.write(endpoint + "\n")

    # Get total lines in pool
    pool_total = 0
    if os.path.exists(POOL_FILE):
        with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as pf:
            pool_total = sum(1 for line in pf if line.strip())

    return len(new_entries), pool_total

def run_single_cycle(cycle_num, seen):
    now = time.time()
    dead_count = 0
    repushed_count = 0

    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] === STARTING FLEET CYCLE {cycle_num} ===")

    for uname, info in FLEET_MAP.items():
        tpath = info["token_file"]
        if not os.path.exists(tpath):
            print(f"Warning: Token file missing for {uname} at {tpath}")
            continue

        with open(tpath, "r", encoding="utf-8") as tf:
            token = tf.read().strip()

        set_kaggle_creds(uname, token)

        for s in info["shards"]:
            s_tag = f"{s:02d}"
            ref = f"{uname}/ipscan-cl-shodan-{s_tag}"
            shard_dir = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{s_tag}")

            out, err, code = run_cmd(f"kaggle kernels status {ref}")
            is_running = ("RUNNING" in out)

            if not is_running:
                dead_count += 1
                status_short = out.split("\n")[-1] if out else (err or "NOT RUNNING")
                print(f"NOT RUNNING: Shard {s_tag} ({uname}) -> {status_short}")

                # Check 10-minute cooldown
                last_pushed = pushed_timestamps.get(s, 0)
                if (now - last_pushed) < 600:
                    print(f"  Skipping repush for Shard {s_tag}: pushed {(now - last_pushed):.0f}s ago (< 600s)")
                else:
                    push_out, push_err, pcode = run_cmd(f'kaggle kernels push -p "{shard_dir}"')
                    if pcode == 0:
                        pushed_timestamps[s] = now
                        repushed_count += 1
                        print(f"  Repushed Shard {s_tag} successfully on {uname}.")
                    else:
                        print(f"  Failed to repush Shard {s_tag}: {push_err or push_out}")

    # Harvest and deduplicate
    new_pool, pool_total = harvest_and_dedupe(seen)

    log_line = f"cycle={cycle_num} dead={dead_count} repushed={repushed_count} new_pool={new_pool} pool_total={pool_total}"
    print(f"RESULT: {log_line}")

    # Append to work/FLEET_CYCLE.txt
    os.makedirs(os.path.dirname(CYCLE_LOG), exist_ok=True)
    with open(CYCLE_LOG, "a", encoding="utf-8") as lf:
        lf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {log_line}\n")

    return log_line

def main():
    seen = load_seen_set()
    cycle = 1

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_single_cycle(cycle, seen)
        return

    while True:
        try:
            run_single_cycle(cycle, seen)
            cycle += 1
            time.sleep(900)
        except KeyboardInterrupt:
            print("Stopping fleet cycle.")
            break
        except Exception as e:
            print(f"Cycle exception: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
