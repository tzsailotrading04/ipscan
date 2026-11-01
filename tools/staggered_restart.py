#!/usr/bin/env python3
"""
tools/staggered_restart.py
Restarts 25 fleet shards across 5 accounts, one account at a time, 10 minutes apart.
For each account:
1) Deletes all existing ipscan-cl-shodan-* kernels on that account to cleanly release batch CPU slots.
2) Pushes the new renumbered shards (5 shards per account, 25 total).
3) Verifies RUNNING status per account after each finishes.
"""

import os
import sys
import time
import re

REPO_ROOT = r"D:\DEpinFarm" if os.path.exists(r"D:\DEpinFarm") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from tools.fleet_cycle import FLEET_MAP, set_kaggle_creds, run_cmd

ACCOUNTS_ORDER = [
    ("lalthazualasailo", [0, 1, 2, 3, 16]),
    ("zomuanpuia", [4, 5, 6, 7, 17]),
    ("laldinthari", [8, 9, 10, 11, 18]),
    ("lalsangkima", [12, 13, 14, 15, 19]),
]

def check_account_running(uname, shards):
    cfg = FLEET_MAP[uname]
    token = open(cfg["token_file"]).read().strip()
    set_kaggle_creds(uname, token)
    running = 0
    for s in shards:
        ref = f"{uname}/ipscan-cl-shodan-{s:02d}"
        out, err, code = run_cmd(f"kaggle kernels status {ref}")
        if "RUNNING" in out:
            running += 1
    return running

def get_existing_shodan_kernels(uname):
    out, err, code = run_cmd("kaggle kernels list --mine")
    kernels = []
    for line in out.splitlines():
        parts = line.split()
        if parts:
            ref = parts[0]
            if f"{uname}/ipscan-cl-shodan" in ref:
                kernels.append(ref)
    return kernels

def restart_account(uname, shards):
    print(f"\n=======================================================", flush=True)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Restarting {uname} (shards {shards})...", flush=True)
    print(f"=======================================================", flush=True)
    cfg = FLEET_MAP[uname]
    token = open(cfg["token_file"]).read().strip()
    set_kaggle_creds(uname, token)

    # 1. Cleanly delete all existing shodan kernels on this account to free the 5 CPU batch slots
    existing = get_existing_shodan_kernels(uname)
    print(f"  Found {len(existing)} existing shodan kernel(s) on {uname} to release slots: {existing}")
    for ref in existing:
        print(f"    Deleting {ref}...", end="", flush=True)
        d_out, d_err, d_code = run_cmd(f"kaggle kernels delete -y {ref}")
        print(" OK", flush=True)
        time.sleep(2)

    # Also delete target refs if not already in list
    for s in shards:
        ref = f"{uname}/ipscan-cl-shodan-{s:02d}"
        if ref not in existing:
            run_cmd(f"kaggle kernels delete -y {ref}")
            time.sleep(1)

    time.sleep(3)

    # 2. Push new shard code
    for s in shards:
        shard_dir = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{s:02d}")
        ref = f"{uname}/ipscan-cl-shodan-{s:02d}"
        print(f"  [{s:02d}] Pushing {shard_dir} ({ref})...", end="", flush=True)
        p_out, p_err, p_code = run_cmd(f'kaggle kernels push -p "{shard_dir}"')
        res = "OK" if "successfully pushed" in p_out else (p_out.splitlines()[-1] if p_out else p_err)
        print(f" -> {res}", flush=True)
        time.sleep(3)

    # 3. Verify status
    time.sleep(5)
    running = check_account_running(uname, shards)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {uname} RUNNING: {running}/{len(shards)}", flush=True)
    return running

def main():
    start_account_idx = 0
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        start_account_idx = int(sys.argv[1])

    for idx in range(start_account_idx, len(ACCOUNTS_ORDER)):
        uname, shards = ACCOUNTS_ORDER[idx]
        restart_account(uname, shards)
        
        # Print status of all accounts so far
        print("\n--- Current Fleet RUNNING Summary ---", flush=True)
        for u, sh in ACCOUNTS_ORDER:
            r = check_account_running(u, sh)
            print(f"  {u:<20}: {r}/{len(sh)} RUNNING", flush=True)
        print("-------------------------------------\n", flush=True)

        if idx < len(ACCOUNTS_ORDER) - 1:
            print(f"Sleeping 10 minutes (600s) before next account ({ACCOUNTS_ORDER[idx+1][0]})...\n", flush=True)
            time.sleep(600)

if __name__ == "__main__":
    main()
