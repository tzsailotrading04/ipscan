#!/usr/bin/env python3
"""
Repush all 34 shards with un-gated push fix (v98.176).
Max 5 shards per account.
Prints: shard, account, status for each.
"""
import os
import sys
import json
import time
import subprocess

REPO_ROOT = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser("~/.kaggle/kaggle.json")

FLEET_MAPPING = [
    # remruata (acct5)
    ("remruata", os.path.join(REPO_ROOT, "kaggle", "acct5", "access_token"), ["00", "01", "20", "21"]),
    # lalthazualasailo (acct1)
    ("lalthazualasailo", os.path.join(REPO_ROOT, "kaggle", "acct1", "access_token"), ["02", "03", "04", "05", "22"]),
    # zomuanpuia (acct2)
    ("zomuanpuia", os.path.join(REPO_ROOT, "kaggle", "acct2", "access_token"), ["06", "07", "08", "09", "23"]),
    # laldinthari (acct3)
    ("laldinthari", os.path.join(REPO_ROOT, "kaggle", "acct3", "access_token"), ["10", "11", "12", "13", "24"]),
    # lalsangkima (acct4)
    ("lalsangkima", os.path.join(REPO_ROOT, "kaggle", "acct4", "access_token"), ["15", "16", "17", "25", "26"]),
    # spectatorlone (acct6)
    ("spectatorlone", os.path.join(REPO_ROOT, "kaggle", "acct6", "access_token"), ["14", "18", "19", "27", "28"]),
    # stephen34
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

def push_and_check(shard_tag, username):
    shard_dir = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{shard_tag}")
    meta_file = os.path.join(shard_dir, "kernel-metadata.json")
    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)
    kernel_id = meta["id"]

    # Push kernel with up to 3 retries
    pushed = False
    last_err = ""
    for attempt in range(1, 4):
        res = subprocess.run(
            ["kaggle", "kernels", "push", "-p", shard_dir],
            capture_output=True,
            text=True
        )
        out = (res.stdout + "\n" + res.stderr).strip()
        if "successfully pushed" in out or "Your Kernel has been updated" in out or "Your notebook was successfully pushed" in out:
            pushed = True
            break
        elif "409" in out or "Conflict" in out:
            time.sleep(3)
        else:
            last_err = out
            time.sleep(2)

    # Check status
    time.sleep(2)
    st_res = subprocess.run(
        ["kaggle", "kernels", "status", kernel_id],
        capture_output=True,
        text=True
    )
    st_out = (st_res.stdout + "\n" + st_res.stderr).strip()
    status = "UNKNOWN"
    for line in st_out.splitlines():
        if "has status" in line:
            status = line.split("has status")[-1].replace('"', "").replace("KernelWorkerStatus.", "").strip()
            break
        elif "status" in line:
            status = line.strip()

    return pushed, status, last_err

def main():
    print(f"{'shard':<8} | {'account':<18} | {'status':<25}")
    print("-" * 55)

    results = []
    for username, token_file, shard_list in FLEET_MAPPING:
        set_credentials(username, token_file)
        for tag in shard_list:
            pushed, status, err = push_and_check(tag, username)
            status_display = status if status != "UNKNOWN" else ("PUSHED" if pushed else f"ERR:{err[:20]}")
            print(f"shard_{tag:<2} | {username:<18} | {status_display:<25}")
            sys.stdout.flush()
            results.append((tag, username, status_display))
            time.sleep(1)

    print("\nREPUSH SUMMARY:")
    running_by_acct = {}
    for tag, username, status in results:
        if "RUNNING" in status or "QUEUED" in status or "PUSHED" in status:
            running_by_acct[username] = running_by_acct.get(username, 0) + 1

    for acct, cnt in sorted(running_by_acct.items()):
        print(f"  {acct}: {cnt} active")

if __name__ == "__main__":
    main()
