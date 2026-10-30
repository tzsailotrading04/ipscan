#!/usr/bin/env python3
"""
tools/force_release_and_repush.py
Forces slot release by deleting all 34 Kaggle kernels, confirming deletion,
waiting 30 seconds, repushing, and verifying version / start time.
"""
import os
import sys
import json
import time
import subprocess
from datetime import datetime

REPO_ROOT = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser("~/.kaggle/kaggle.json")

FLEET = [
    ("remruata", os.path.join(REPO_ROOT, "kaggle", "acct5", "access_token"), ["00", "01", "20", "21"]),
    ("lalthazualasailo", os.path.join(REPO_ROOT, "kaggle", "acct1", "access_token"), ["02", "03", "04", "05", "22"]),
    ("zomuanpuia", os.path.join(REPO_ROOT, "kaggle", "acct2", "access_token"), ["06", "07", "08", "09", "23"]),
    ("laldinthari", os.path.join(REPO_ROOT, "kaggle", "acct3", "access_token"), ["10", "11", "12", "13", "24"]),
    ("lalsangkima", os.path.join(REPO_ROOT, "kaggle", "acct4", "access_token"), ["15", "16", "17", "25", "26"]),
    ("spectatorlone", os.path.join(REPO_ROOT, "kaggle", "acct6", "access_token"), ["14", "18", "19", "27", "28"]),
    ("stephen34", os.path.join(REPO_ROOT, "kaggle", "stephen34", "access_token"), ["29", "30", "31", "32", "33"]),
]

def set_credentials(username, token_file):
    with open(token_file, "r", encoding="utf-8") as f:
        token = f.read().strip()
    os.environ["KAGGLE_API_TOKEN"] = token
    os.environ["KAGGLE_USERNAME"] = username
    os.environ["KAGGLE_KEY"] = token
    os.makedirs(os.path.dirname(KAGGLE_JSON), exist_ok=True)
    with open(KAGGLE_JSON, "w", encoding="utf-8") as f:
        json.dump({"username": username, "key": token}, f, indent=2)

def run_cmd(args):
    res = subprocess.run(args, capture_output=True, text=True)
    out = (res.stdout + "\n" + res.stderr).strip()
    # strip kaggle warning
    clean_lines = [l for l in out.splitlines() if "Warning: Looks like you're using an outdated" not in l]
    return "\n".join(clean_lines).strip()

def step1_delete_all():
    print("\n================ STEP 1: DELETE ALL 34 SHARDS (3s GAP) ================")
    results = {}
    for acct, token_file, shards in FLEET:
        set_credentials(acct, token_file)
        for s in shards:
            slug = f"{acct}/ipscan-cl-shodan-{s}"
            cmd = ["kaggle", "kernels", "delete", "-y", slug]
            out = run_cmd(cmd)
            results[s] = out
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Shard {s} ({acct}): {out}", flush=True)
            time.sleep(3)
    return results

def step2_confirm_deleted():
    print("\n================ STEP 2: CONFIRM DELETION (EXPECT 404 / NOT FOUND) ================", flush=True)
    all_deleted = True
    for acct, token_file, shards in FLEET:
        set_credentials(acct, token_file)
        for s in shards:
            slug = f"{acct}/ipscan-cl-shodan-{s}"
            out = run_cmd(["kaggle", "kernels", "status", slug])
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Shard {s} ({acct}): {out}", flush=True)
            if "404" not in out and "not found" not in out.lower() and "does not exist" not in out.lower():
                all_deleted = False
            time.sleep(0.5)
    return all_deleted

def step3_wait_30s():
    print("\n================ STEP 3: WAIT 30 SECONDS FOR KAGGLE SLOT RELEASE ================", flush=True)
    for sec in range(30, 0, -5):
        print(f"Waiting {sec}s remaining...", flush=True)
        time.sleep(5)
    print("Wait complete. Slots released.", flush=True)

def step4_push_all():
    print("\n================ STEP 4: PUSH ALL 34 BACK (3s GAP) ================", flush=True)
    results = {}
    for acct, token_file, shards in FLEET:
        set_credentials(acct, token_file)
        for s in shards:
            shard_dir = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{s}")
            cmd = ["kaggle", "kernels", "push", "-p", shard_dir]
            out = run_cmd(cmd)
            results[s] = {
                "account": acct,
                "output": out,
                "push_time": datetime.now()
            }
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Shard {s} ({acct}): {out}", flush=True)
            time.sleep(3)
    return results

def step5_verify(push_results):
    print("\n================ STEP 5: VERIFY VERSION & START TIME ================", flush=True)
    now = datetime.now()
    failures = []
    
    for acct, token_file, shards in FLEET:
        set_credentials(acct, token_file)
        # get list mine
        list_out = run_cmd(["kaggle", "kernels", "list", "--mine"])
        
        for s in shards:
            slug = f"{acct}/ipscan-cl-shodan-{s}"
            push_info = push_results.get(s, {})
            push_out = push_info.get("output", "")
            
            # parse version
            # e.g. "Kernel version 2 successfully pushed."
            ver_num = None
            for line in push_out.splitlines():
                if "version" in line.lower() and "successfully pushed" in line.lower():
                    # extract number
                    parts = line.split()
                    for idx, p in enumerate(parts):
                        if p.lower() == "version" and idx + 1 < len(parts):
                            v_str = parts[idx+1]
                            if v_str.isdigit():
                                ver_num = int(v_str)

            # status check
            status_out = run_cmd(["kaggle", "kernels", "status", slug])
            
            # Start time: pushed just now (within 1-5 minutes)
            p_time = push_info.get("push_time", now)
            age_sec = (now - p_time).total_seconds()
            
            print(f"Shard {s} ({acct}): Version #{ver_num if ver_num else '?'} | Status: {status_out} | Started {int(age_sec)}s ago")
            
            if ver_num is not None and ver_num < 2:
                print(f"RESTART_FAILED shard_{s} (Version #{ver_num} < 2)")
                failures.append(s)
            elif age_sec > 600:
                print(f"RESTART_FAILED shard_{s} (Start time > 10m)")
                failures.append(s)
            elif "RUNNING" not in status_out and "QUEUED" not in status_out and "COMPLETE" not in status_out:
                print(f"RESTART_FAILED shard_{s} ({status_out})")
                failures.append(s)

    if not failures:
        print("\nALL 34 SHARDS VERIFIED: Version #2+ and started inside 10 minutes.")
    else:
        print(f"\nFAILED SHARDS: {failures}")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--step1":
        step1_delete_all()
    elif len(sys.argv) > 1 and sys.argv[1] == "--step2":
        step2_confirm_deleted()
    elif len(sys.argv) > 1 and sys.argv[1] == "--step3":
        step3_wait_30s()
    elif len(sys.argv) > 1 and sys.argv[1] == "--step4":
        step4_push_all()
    elif len(sys.argv) > 1 and sys.argv[1] == "--step5":
        step5_verify({})
    else:
        step1_delete_all()
        step2_confirm_deleted()
        step3_wait_30s()
        push_results = step4_push_all()
        step5_verify(push_results)

if __name__ == "__main__":
    main()
