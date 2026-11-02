#!/usr/bin/env python3
"""
tools/fleet_restart.py
Restart the fleet one account at a time in order:
1) lalthazualasailo
2) zomuanpuia
3) laldinthari
4) lalsangkima

For each account:
- Delete its 5 kernels
- Wait 30 minutes (1800 seconds)
- Push its 5 shards
- Print RUNNING per account after each push
- Wait 30 minutes before starting the next account
"""

import os
import sys
import time
import json
import subprocess
import datetime

REPO_ROOT = r"D:\DEpinFarm"
RESTART_STATE = os.path.join(REPO_ROOT, "work", "fleet_restart_state.json")
LOG_FILE = os.path.join(REPO_ROOT, "work", "fleet_restart.log")

ACCOUNTS_ORDER = ["lalthazualasailo", "zomuanpuia", "laldinthari", "lalsangkima"]

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

def log(msg):
    iso_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = f"[{iso_time}] {msg}"
    print(entry, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry + "\n")

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

def save_restart_state(data):
    try:
        with open(RESTART_STATE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

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

def restart_account(uname, is_last):
    info = FLEET_MAP[uname]
    shards = info["shards"]
    with open(info["token_file"], "r", encoding="utf-8") as tf:
        token = tf.read().strip()
    set_kaggle_creds(uname, token)

    log(f"============================================================")
    log(f"STARTING RESTART FOR ACCOUNT: {uname} (shards: {shards})")
    log(f"============================================================")

    # 1. Delete its 5 kernels
    save_restart_state({"status": "deleting", "active_account": uname, "ts": time.time()})
    log(f"Deleting 5 kernels for {uname}...")
    for s in shards:
        ref = f"{uname}/ipscan-cl-shodan-{s:02d}"
        out, err, code = run_cmd(f"kaggle kernels delete -y {ref}")
        log(f"  Delete {ref}: code={code} {out or err}")

    # 2. Wait 30 minutes
    del_wait_secs = 1800
    save_restart_state({
        "status": "waiting_after_delete",
        "active_account": uname,
        "start_ts": time.time(),
        "target_ts": time.time() + del_wait_secs
    })
    log(f"Deleted kernels for {uname}. Waiting 30 minutes (1800s) for cooldown...")
    time.sleep(del_wait_secs)

    # 3. Push its 5 shards
    save_restart_state({"status": "pushing", "active_account": uname, "ts": time.time()})
    log(f"Pushing 5 shards for {uname}...")
    for s in shards:
        shard_dir = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{s:02d}")
        out, err, code = run_cmd(f'kaggle kernels push -p "{shard_dir}"')
        log(f"  Push Shard {s:02d} ({uname}): code={code} {out or err}")

    # 4. Check & Print RUNNING per account
    time.sleep(15)  # small buffer for status to register
    running_counts = get_running_per_account()
    running_str = " | ".join([f"{u}: {cnt}/5" for u, cnt in running_counts.items()])
    log(f"RUNNING PER ACCOUNT AFTER PUSH FOR {uname}: {running_str}")

    # 5. Wait 30 minutes before starting the next account
    if not is_last:
        post_wait_secs = 1800
        save_restart_state({
            "status": "waiting_after_push",
            "active_account": uname,
            "start_ts": time.time(),
            "target_ts": time.time() + post_wait_secs
        })
        log(f"Waiting 30 minutes (1800s) before starting the next account...")
        time.sleep(post_wait_secs)

def main():
    log(f"Starting Fleet Sequential Restart Orchestrator (PID {os.getpid()})...")
    for idx, uname in enumerate(ACCOUNTS_ORDER):
        is_last = (idx == len(ACCOUNTS_ORDER) - 1)
        restart_account(uname, is_last)
    save_restart_state({"status": "completed", "completed_at": time.time()})
    log("============================================================")
    log("ALL 4 ACCOUNTS HAVE COMPLETED SEQUENTIAL RESTART!")
    final_running = get_running_per_account()
    final_str = " | ".join([f"{u}: {cnt}/5" for u, cnt in final_running.items()])
    log(f"FINAL FLEET STATUS: {final_str}")
    log("============================================================")

if __name__ == "__main__":
    main()
