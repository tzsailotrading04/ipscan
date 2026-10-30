#!/usr/bin/env python3
import os
import sys
import glob
import time
import json
import subprocess

REPO_ROOT = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser("~/.kaggle/kaggle.json")
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")

FLEET_MAPPING = [
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

def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def main():
    print("=" * 60)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] STEP 7 VERIFICATION")
    print("=" * 60)

    # 1. Fetch & merge latest
    print("Fetching and merging latest git updates...")
    run_cmd(f'git -C "{REPO_ROOT}" fetch origin main --quiet')
    run_cmd(f'git -C "{REPO_ROOT}" merge --no-edit origin/main --quiet')

    now = time.time()

    # 2. Part files analysis
    part_files = glob.glob(os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive_part_*.txt"))
    newest_file = None
    newest_mtime = 0

    files_5m = 0
    lines_5m = 0

    for pf in part_files:
        try:
            m = os.path.getmtime(pf)
            if m > newest_mtime:
                newest_mtime = m
                newest_file = pf
            if (now - m) <= 300:
                files_5m += 1
                with open(pf, "r", encoding="utf-8", errors="ignore") as f:
                    lines_5m += sum(1 for l in f if l.strip())
        except Exception:
            pass

    newest_age = (now - newest_mtime) if newest_file else 999999
    newest_name = os.path.basename(newest_file) if newest_file else "None"

    # 3. Pool size
    pool_size = 0
    if os.path.exists(POOL_FILE):
        with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
            pool_size = sum(1 for l in f if l.strip())

    # 4. RUNNING per account
    running_by_acct = {}
    total_running = 0
    total_checked = 0

    print("\nChecking Kaggle shard statuses across 7 accounts...")
    for uname, tok_file, shard_list in FLEET_MAPPING:
        set_credentials(uname, tok_file)
        acct_running = 0
        for tag in shard_list:
            total_checked += 1
            meta_path = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{tag}", "kernel-metadata.json")
            with open(meta_path, "r", encoding="utf-8") as mf:
                kid = json.load(mf)["id"]
            out, err, code = run_cmd(f"kaggle kernels status {kid}")
            if "RUNNING" in out:
                acct_running += 1
                total_running += 1
        running_by_acct[uname] = acct_running

    print("\n--- RESULTS ---")
    print(f"Newest part-file           : {newest_name}")
    print(f"Newest part-file mtime     : {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(newest_mtime))}")
    print(f"Newest part-file age       : {newest_age:.1f}s ({newest_age/60:.2f} minutes)")
    print(f"Part files modified (5m)   : {files_5m}")
    print(f"Part file lines added (5m) : {lines_5m}")
    print(f"Pool size (real_pool.txt)  : {pool_size}")
    print("\nRUNNING per account:")
    for uname, cnt in running_by_acct.items():
        print(f"  {uname:<18} : {cnt} RUNNING")
    print(f"Total RUNNING shards       : {total_running}/{total_checked}")

    print("\nVERDICT:")
    if newest_age <= 180:
        print(f"QUEUE_UNBLOCKED_AND_HARVESTING (Newest part-file age {newest_age:.1f}s <= 180s)")
    else:
        print(f"STILL_BLOCKED (Newest part-file age {newest_age:.1f}s > 180s)")

if __name__ == "__main__":
    main()
