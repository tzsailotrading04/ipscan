#!/usr/bin/env python3
"""
tools/watchdog.py
Fleet Watchdog: Every 5 minutes checks RUNNING shards per account.
If an account has < 5 running and its 30-minute cooldown has passed, repushes missing shards.
Appends iso_time running_per_account repushed to work/WATCH.txt.
Alerts to work/ALERT.txt if any account sits below 5 for two consecutive checks.
"""

import os
import sys
import time
import json
import subprocess
import datetime

REPO_ROOT = r"D:\DEpinFarm"
WATCH_FILE = os.path.join(REPO_ROOT, "work", "WATCH.txt")
ALERT_FILE = os.path.join(REPO_ROOT, "work", "ALERT.txt")
STATE_FILE = os.path.join(REPO_ROOT, "work", "watchdog_state.json")
RESTART_STATE = os.path.join(REPO_ROOT, "work", "fleet_restart_state.json")

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
COOLDOWN_SECONDS = 1800  # 30 minutes

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

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_repush": {}, "consecutive_below_5": {}}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

def get_restart_account():
    """If a fleet restart orchestrator is currently actively deleting/waiting for an account, return its name."""
    if os.path.exists(RESTART_STATE):
        try:
            with open(RESTART_STATE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if d.get("status") in ("deleting", "waiting_after_delete"):
                    return d.get("active_account")
        except Exception:
            pass
    return None

def check_account_status(uname, info):
    with open(info["token_file"], "r", encoding="utf-8") as tf:
        token = tf.read().strip()
    set_kaggle_creds(uname, token)

    running_shards = []
    missing_shards = []

    for s in info["shards"]:
        s_tag = f"{s:02d}"
        ref = f"{uname}/ipscan-cl-shodan-{s_tag}"
        out, err, code = run_cmd(f"kaggle kernels status {ref}")
        if "RUNNING" in out:
            running_shards.append(s)
        else:
            missing_shards.append(s)

    return running_shards, missing_shards

def repush_shard(uname, info, s):
    s_tag = f"{s:02d}"
    shard_dir = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{s_tag}")
    with open(info["token_file"], "r", encoding="utf-8") as tf:
        token = tf.read().strip()
    set_kaggle_creds(uname, token)
    out, err, code = run_cmd(f'kaggle kernels push -p "{shard_dir}"')
    return code == 0, out or err

def watchdog_cycle(state):
    now_ts = time.time()
    iso_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    restarting_acct = get_restart_account()

    running_counts = {}
    repushed_by_acct = {}
    alerts = []

    for uname, info in FLEET_MAP.items():
        running_s, missing_s = check_account_status(uname, info)
        r_cnt = len(running_s)
        running_counts[uname] = r_cnt
        repushed_by_acct[uname] = []

        # Check consecutive below 5
        if r_cnt < 5:
            state["consecutive_below_5"][uname] = state["consecutive_below_5"].get(uname, 0) + 1
            if state["consecutive_below_5"][uname] >= 2 and uname != restarting_acct:
                alerts.append(f"[{iso_time}] [ALERT] Account {uname} has {r_cnt}/5 running for {state['consecutive_below_5'][uname]} consecutive checks.")
        else:
            state["consecutive_below_5"][uname] = 0

        # Check repush criteria: < 5 running, 30m cooldown passed, not in restart delete phase
        if r_cnt < 5 and uname != restarting_acct:
            last_pushed = state["last_repush"].get(uname, 0)
            if (now_ts - last_pushed) >= COOLDOWN_SECONDS:
                print(f"[{iso_time}] Watchdog: {uname} has {r_cnt}/5 running. 30m cooldown passed. Repushing {len(missing_s)} missing shards: {missing_s}")
                for s in missing_s:
                    ok, msg = repush_shard(uname, info, s)
                    if ok:
                        repushed_by_acct[uname].append(f"sh{s:02d}")
                        print(f"  Repushed sh{s:02d} successfully.")
                    else:
                        print(f"  Failed repush sh{s:02d}: {msg}")
                if repushed_by_acct[uname]:
                    state["last_repush"][uname] = now_ts
            else:
                remaining = int(COOLDOWN_SECONDS - (now_ts - last_pushed))
                print(f"[{iso_time}] Watchdog: {uname} has {r_cnt}/5 running. Cooldown active ({remaining}s remaining).")

    # Format log line for work/WATCH.txt: iso_time running_per_account repushed
    running_str = " ".join([f"{u}={cnt}" for u, cnt in running_counts.items()])
    repushed_list = []
    for u, shards in repushed_by_acct.items():
        if shards:
            repushed_list.append(f"{u}:[{','.join(shards)}]")
    repushed_str = " ".join(repushed_list) if repushed_list else "none"

    watch_entry = f"{iso_time} running: {running_str} repushed: {repushed_str}\n"
    with open(WATCH_FILE, "a", encoding="utf-8") as wf:
        wf.write(watch_entry)

    # Append alerts if any
    if alerts:
        with open(ALERT_FILE, "a", encoding="utf-8") as af:
            for al in alerts:
                af.write(al + "\n")
                print(al)

    save_state(state)
    print(f"[{iso_time}] WATCH ENTRY: {watch_entry.strip()}")
    return running_counts, repushed_str

def main():
    print(f"[{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] Starting Fleet Watchdog daemon (PID {os.getpid()})...", flush=True)
    state = load_state()
    while True:
        try:
            watchdog_cycle(state)
        except Exception as e:
            print(f"Watchdog exception: {e}", file=sys.stderr, flush=True)
        time.sleep(300)

if __name__ == "__main__":
    main()
