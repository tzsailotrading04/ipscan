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
QUEUE_DIR = os.path.join(REPO_ROOT, "ip", "harvest", "queue")

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

def take_reading(reading_num):
    print(f"\n======================================================================", flush=True)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] --- READING {reading_num} OF 3 ---", flush=True)
    print(f"======================================================================", flush=True)

    # Sync git to get newest commits from Kaggle shards
    run_cmd(f'git -C "{REPO_ROOT}" fetch origin main --quiet')
    run_cmd(f'git -C "{REPO_ROOT}" merge --no-edit origin/main --quiet')

    now = time.time()

    # 1. Newest part file & 2. 5-min count & 3. 5-min lines
    part_files = glob.glob(os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive_part_*.txt"))
    newest_file = None
    newest_mtime = 0

    count_5m = 0
    lines_5m = 0

    for pf in part_files:
        try:
            m = os.path.getmtime(pf)
            if m > newest_mtime:
                newest_mtime = m
                newest_file = pf
            if (now - m) <= 300:
                count_5m += 1
                with open(pf, "r", encoding="utf-8", errors="ignore") as f:
                    lines_5m += sum(1 for l in f if l.strip())
        except Exception:
            pass

    newest_age = (now - newest_mtime) if newest_file else 999999
    newest_name = os.path.basename(newest_file) if newest_file else "None"
    mtime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(newest_mtime)) if newest_mtime else "N/A"

    print(f"1. Newest part file: {newest_name} | mtime: {mtime_str} | age: {newest_age:.1f}s", flush=True)
    print(f"2. Count of part files modified in last 5m: {count_5m}", flush=True)
    print(f"3. Total lines across part files modified in last 5m: {lines_5m}", flush=True)

    # 4. Pool size
    pool_lines = 0
    if os.path.exists(POOL_FILE):
        with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
            pool_lines = sum(1 for l in f if l.strip())
    print(f"4. wc -l on ip/harvest/real_pool.txt: {pool_lines}", flush=True)

    # 5. Queue files wc -l & count
    q_files = sorted(glob.glob(os.path.join(QUEUE_DIR, "q_*.txt")))
    q_count = len(q_files)
    total_q_lines = 0
    q_details = []
    for qf in q_files:
        try:
            with open(qf, "r", encoding="utf-8", errors="ignore") as f:
                cnt = sum(1 for l in f if l.strip())
                total_q_lines += cnt
                q_details.append(f"{os.path.basename(qf)}: {cnt}")
        except Exception:
            pass
    q_det_str = f" ({', '.join(q_details)})" if q_details else ""
    print(f"5. wc -l on ip/harvest/queue/q_*.txt: {total_q_lines} total lines across {q_count} batch files{q_det_str}", flush=True)

    # 6. RUNNING shard count and any not RUNNING
    running_count = 0
    not_running = []

    for uname, tok_file, shard_list in FLEET_MAPPING:
        set_credentials(uname, tok_file)
        for tag in shard_list:
            meta_path = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{tag}", "kernel-metadata.json")
            with open(meta_path, "r", encoding="utf-8") as mf:
                kid = json.load(mf)["id"]
            out, err, code = run_cmd(f"kaggle kernels status {kid}")
            status = "UNKNOWN"
            for line in out.splitlines():
                if "status" in line:
                    status = line.strip()
                    break
            if "RUNNING" in out:
                running_count += 1
            else:
                not_running.append(f"shard_{tag} ({uname}: {status})")

    not_running_str = f" | Not RUNNING: {', '.join(not_running)}" if not_running else " | None not RUNNING (all 34 healthy)"
    print(f"6. RUNNING shard count: {running_count}/34{not_running_str}", flush=True)

    return newest_age, q_count

def main():
    ages = []
    q_counts = []

    # Reading 1
    age1, qc1 = take_reading(1)
    ages.append(age1)
    q_counts.append(qc1)

    # Wait 2 minutes (120s)
    print(f"\n[{time.strftime('%H:%M:%S')}] Waiting 120s for Reading 2...", flush=True)
    time.sleep(120)

    # Reading 2
    age2, qc2 = take_reading(2)
    ages.append(age2)
    q_counts.append(qc2)

    # Wait 2 minutes (120s)
    print(f"\n[{time.strftime('%H:%M:%S')}] Waiting 120s for Reading 3...", flush=True)
    time.sleep(120)

    # Reading 3
    age3, qc3 = take_reading(3)
    ages.append(age3)
    q_counts.append(qc3)

    # Summary
    print(f"\n======================================================================", flush=True)
    print(f"BLOCK CHECK FINAL SUMMARY", flush=True)
    print(f"======================================================================", flush=True)
    print(f"AGE TREND: {ages[0]:.1f}s -> {ages[1]:.1f}s -> {ages[2]:.1f}s", flush=True)

    # Verdict determination
    if ages[2] < 180:
        verdict = "WORKING"
    elif ages[2] < ages[0] and (ages[1] < ages[0] or ages[2] < ages[1]):
        verdict = "WARMUP"
    else:
        verdict = "STILL_BLOCKED"

    print(f"VERDICT: {verdict}", flush=True)
    print(f"QUEUE REMAINING: {q_counts[2]}", flush=True)
    print(f"======================================================================\n", flush=True)

if __name__ == "__main__":
    main()
