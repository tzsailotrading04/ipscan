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
import re

REPO_ROOT = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser("~/.kaggle/kaggle.json")
KAGGLE_TOKEN = os.path.expanduser("~/.kaggle/access_token")
CYCLE_LOG = os.path.join(REPO_ROOT, "work", "FLEET_CYCLE.txt")
SEEN_FILE = os.path.join(REPO_ROOT, "cache", "harvest_seen_set.txt")
QUEUE_FILE = os.path.join(REPO_ROOT, "cache", "candidate_queue.txt")
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
DEAD_FILE = os.path.join(REPO_ROOT, "cache", "pool_dead.txt")

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
last_git_push_ts = 0
GIT_PUSH_THROTTLE = 600  # Throttle git push to at most once per 600 seconds

def throttled_git_push(msg="harvester pool cycle"):
    """Throttles git push to at most once per 600 seconds."""
    global last_git_push_ts
    now = time.time()
    if (now - last_git_push_ts) < GIT_PUSH_THROTTLE:
        print(f"[GIT PUSH GUARD] Throttled: last push {(now - last_git_push_ts):.1f}s ago (< {GIT_PUSH_THROTTLE}s). Skipping git push.")
        return False

    try:
        run_cmd(f'git -C "{REPO_ROOT}" fetch origin main --quiet')
        run_cmd(f'git -C "{REPO_ROOT}" merge --no-edit origin/main --quiet')
        run_cmd(f'git -C "{REPO_ROOT}" add ip/harvest/real_pool.txt work/FLEET_CYCLE.txt')
        c_out, c_err, c_code = run_cmd(f'git -C "{REPO_ROOT}" commit -m "{msg}"')
        if c_code == 0 or "nothing to commit" in c_out:
            p_out, p_err, p_code = run_cmd(f'git -C "{REPO_ROOT}" push origin main')
            if p_code == 0:
                last_git_push_ts = time.time()
                print(f"[GIT PUSH GUARD] Git push succeeded ({msg}). Next allowed in {GIT_PUSH_THROTTLE}s.")
                return True
            else:
                print(f"[GIT PUSH GUARD] Git push failed: {p_err or p_out}")
    except Exception as e:
        print(f"[GIT PUSH GUARD] Git push exception: {e}")
    return False

def set_kaggle_creds(username, token):
    os.makedirs(os.path.dirname(KAGGLE_JSON), exist_ok=True)
    with open(KAGGLE_JSON, "w", encoding="utf-8") as f:
        json.dump({"username": username, "key": token}, f, indent=2)
    with open(KAGGLE_TOKEN, "w", encoding="utf-8") as f:
        f.write(token)
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

def load_pool_endpoints():
    pool_eps = set()
    if os.path.exists(POOL_FILE):
        with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as pf:
            for line in pf:
                l = line.strip()
                if l:
                    pool_eps.add(l.split("\t")[0].split()[0])
    return pool_eps

def harvest_and_dedupe(seen=None):
    pool_endpoints = load_pool_endpoints()
    new_entries = []
    # Only read part files whose mtime is within the last 2 hours (7200s)
    now_ts = time.time()
    part_files = [
        pf for pf in glob.glob(os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive_part_*.txt"))
        if (now_ts - os.path.getmtime(pf)) <= 7200
    ]
    
    for pf in part_files:
        try:
            with open(pf, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    endpoint = raw.split("\t")[0].split()[0]
                    if endpoint not in pool_endpoints:
                        pool_endpoints.add(endpoint)
                        new_entries.append(raw)
        except Exception:
            pass

    if new_entries:
        # Promote part-file lines directly to real_pool.txt with no second pass
        os.makedirs(os.path.dirname(POOL_FILE), exist_ok=True)
        with open(POOL_FILE, "a", encoding="utf-8") as pf:
            for entry in new_entries:
                pf.write(entry + "\n")

    return len(new_entries), len(pool_endpoints)

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

    # Throttle git push to at most once per 600 seconds
    throttled_git_push(f"v98.185 harvest pool update (+{new_pool}, total={pool_total})")

    return log_line

last_merge_ts = 0


def process_queue_failed_files():
    failed_files = glob.glob(os.path.join(REPO_ROOT, "ip", "harvest", "queue_failed_part_*.txt"))
    if not failed_files:
        return 0

    dead_eps = set()
    if os.path.exists(DEAD_FILE):
        with open(DEAD_FILE, "r", encoding="utf-8", errors="ignore") as df:
            for line in df:
                m = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3}:\d{2,5})\b", line)
                if m:
                    dead_eps.add(m.group(1))

    new_dead = []
    for ff in failed_files:
        try:
            with open(ff, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    m = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3}:\d{2,5})\b", line)
                    if m:
                        ep = m.group(1)
                        if ep not in dead_eps:
                            dead_eps.add(ep)
                            new_dead.append(ep)
            # Clear the failed part file
            with open(ff, "w", encoding="utf-8") as f:
                pass
        except Exception as e:
            print(f"[FAILED PART ERROR] {ff}: {e}")

    if new_dead:
        os.makedirs(os.path.dirname(DEAD_FILE), exist_ok=True)
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(DEAD_FILE, "a", encoding="utf-8") as df:
            for ep in new_dead:
                df.write(f"[{now_str}] {ep}\tspeed.cloudflare.com\tQUEUE\tREASON:FAIL_CONNECT\tRETIRED\n")
        print(f"[FAILED QUEUE] Appended {len(new_dead):,} new dead endpoints to cache/pool_dead.txt. Cleared {len(failed_files)} failed part files.")

    return len(new_dead)

def merge_out_branches():
    """Every 300s, fetch all out/sh* branches and merge their files into main, then push once."""
    global last_merge_ts
    now = time.time()
    if (now - last_merge_ts) < 300:
        return False

    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] [MERGE] Fetching all out/sh* branches...")
    run_cmd(f'git -C "{REPO_ROOT}" fetch origin "+refs/heads/out/sh*:refs/remotes/origin/out/sh*" --prune --quiet')

    out, err, code = run_cmd(f'git -C "{REPO_ROOT}" branch -r --list "origin/out/sh*"')
    remote_branches = [b.strip() for b in out.splitlines() if b.strip()]

    if not remote_branches:
        print("[MERGE] No out/sh* branches found on remote.")
        last_merge_ts = now
        return False

    print(f"[MERGE] Found {len(remote_branches)} remote shard branches to merge.")
    merged_count = 0
    for rb in remote_branches:
        branch_name = rb.split("/")[-1]
        tag = branch_name.rsplit("sh", 1)[-1]
        c_out, c_err, c_code = run_cmd(
            f'git -C "{REPO_ROOT}" checkout {rb} -- '
            f'"ip/harvest/verified_alive_part_{tag}*.txt" '
            f'"ip/harvest/queue_failed_part_{tag}*.txt" '
            f'"ip/harvest/shodan_stats_v98_{tag}*.txt" '
            f'"ip/harvest/shodan_progress_v98_{tag}*.txt" '
            f'"ip/harvest/stage_{tag}.txt"'
        )
        if c_code == 0:
            merged_count += 1

    new_pool, pool_total = harvest_and_dedupe()
    process_queue_failed_files()

    run_cmd(f'git -C "{REPO_ROOT}" add ip/harvest/ real_pool.txt cache/ work/FLEET_CYCLE.txt')
    st_out, _, _ = run_cmd(f'git -C "{REPO_ROOT}" status --porcelain')
    if st_out:
        msg = f"v98.188 merge {merged_count} shard branches, pool={pool_total} (+{new_pool})"
        run_cmd(f'git -C "{REPO_ROOT}" commit -m "{msg}"')
        p_out, p_err, p_code = run_cmd(f'git -C "{REPO_ROOT}" push origin main')
        if p_code == 0:
            print(f"[MERGE] Pushed merged shard files to main (pool={pool_total}, +{new_pool}).")
        else:
            print(f"[MERGE] Push to main failed: {p_err or p_out}")
    else:
        print("[MERGE] No file changes after merging shard branches.")

    last_merge_ts = now
    return True

def main():
    seen = load_seen_set()
    cycle = 1
    last_cycle_t = 0

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        merge_out_branches()
        run_single_cycle(cycle, seen)
        return

    while True:
        try:
            merge_out_branches()
            now = time.time()
            if (now - last_cycle_t) >= 900:
                run_single_cycle(cycle, seen)
                cycle += 1
                last_cycle_t = now
            time.sleep(30)
        except KeyboardInterrupt:
            print("Stopping fleet cycle.")
            break
        except Exception as e:
            print(f"Cycle exception: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
