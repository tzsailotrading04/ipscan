#!/usr/bin/env python3
"""
Repush All 34 Shards with v98.189 Patch
1. Uses valid tokens from kaggle/acct*/access_token.
2. For each shard: deletes old kernel to free the 5-session batch quota slot, then pushes new version.
3. Covers all 34 active shards across 7 accounts in exact order requested.
"""

import os
import subprocess
import json
import time
import sys

REPO = r"D:\DEpinFarm"
KAGGLE_DIR = os.path.join(os.environ.get("USERPROFILE", r"C:\Users\pc"), ".kaggle")
os.makedirs(KAGGLE_DIR, exist_ok=True)

GROUPS = [
    ("remruata", "acct5", ["00", "01", "20", "21"]),
    ("lalthazualasailo", "acct1", ["02", "03", "04", "05", "22"]),
    ("zomuanpuia", "acct2", ["06", "07", "08", "09", "23"]),
    ("laldinthari", "acct3", ["10", "11", "12", "13", "24"]),
    ("lalsangkima", "acct4", ["15", "16", "17", "25", "26"]),
    ("spectatorlone", "acct6", ["14", "18", "19", "27", "28"]),
    ("lalruatmawiaralte", "acct7", ["29", "30", "31", "32", "33"]),
]

successes = []
failures = []

for username, acct_folder, shards in GROUPS:
    print(f"\n==========================================")
    print(f"Account: {username} ({acct_folder}) - {len(shards)} shards")
    print(f"==========================================")

    token_path = os.path.join(REPO, "kaggle", acct_folder, "access_token")
    if not os.path.exists(token_path):
        print(f"Error: Token not found at {token_path}")
        for s in shards:
            failures.append((s, username, "Token not found"))
        continue

    with open(token_path, "r", encoding="utf-8") as f:
        tok = f.read().strip()

    with open(os.path.join(KAGGLE_DIR, "kaggle.json"), "w", encoding="utf-8") as f:
        json.dump({"username": username, "key": tok}, f, indent=2)
    with open(os.path.join(KAGGLE_DIR, "access_token"), "w", encoding="utf-8") as f:
        f.write(tok)

    env = os.environ.copy()
    env["KAGGLE_USERNAME"] = username
    env["KAGGLE_KEY"] = tok
    env["KAGGLE_API_TOKEN"] = tok

    for s in shards:
        slug = f"{username}/ipscan-cl-shodan-{s}"
        kernel_path = os.path.join(REPO, "kaggle", f"cl_shodan_{s}")

        print(f">>> Deleting old {slug} ...", end=" ", flush=True)
        del_res = subprocess.run(["kaggle", "kernels", "delete", "-y", slug], env=env, capture_output=True, text=True)
        del_out = (del_res.stdout + " " + del_res.stderr).strip()
        if "deleted successfully" in del_out or del_res.returncode == 0:
            print("DELETED", flush=True)
        elif "404" in del_out or "not found" in del_out.lower():
            print("NOT FOUND (clean)", flush=True)
        else:
            print(f"INFO: {del_out.splitlines()[-1] if del_out else 'OK'}", flush=True)

        time.sleep(3)

        print(f">>> Pushing {kernel_path} ({username}) ...", flush=True)
        push_res = subprocess.run(["kaggle", "kernels", "push", "-p", kernel_path], env=env, capture_output=True, text=True)
        out_raw = (push_res.stdout + "\n" + push_res.stderr).strip()
        lines = [l for l in out_raw.splitlines() if l.strip() and not l.startswith("Warning:")]
        last_line = lines[-1] if lines else "OK"

        if push_res.returncode == 0 and ("Your Kernel" in out_raw or "successfully pushed" in out_raw.lower() or "kernel version" in out_raw.lower()):
            print(f"    SUCCESS: {last_line}", flush=True)
            successes.append(s)
        else:
            print(f"    FAILED ({push_res.returncode}): {out_raw}", flush=True)
            failures.append((s, username, out_raw))

        time.sleep(3)

print("\n==========================================")
print(f"SUMMARY: {len(successes)}/34 SUCCESSFUL, {len(failures)} FAILED")
if failures:
    print("FAILURES:")
    for s, u, err in failures:
        print(f"  Shard {s} ({u}): {err}")
else:
    print("ALL 34 SHARDS PUSHED SUCCESSFULLY WITH 0 FAILURES")
print("==========================================")
