import os
import sys
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

REPO = r"D:\DEpinFarm"

FLEET = [
    (0, "remruata", "kaggle/acct5/access_token"),
    (1, "remruata", "kaggle/acct5/access_token"),
    (2, "lalthazualasailo", "kaggle/acct1/access_token"),
    (3, "lalthazualasailo", "kaggle/acct1/access_token"),
    (4, "lalthazualasailo", "kaggle/acct1/access_token"),
    (5, "lalthazualasailo", "kaggle/acct1/access_token"),
    (6, "zomuanpuia", "kaggle/acct2/access_token"),
    (7, "zomuanpuia", "kaggle/acct2/access_token"),
    (8, "zomuanpuia", "kaggle/acct2/access_token"),
    (9, "zomuanpuia", "kaggle/acct2/access_token"),
    (10, "laldinthari", "kaggle/acct3/access_token"),
    (11, "laldinthari", "kaggle/acct3/access_token"),
    (12, "laldinthari", "kaggle/acct3/access_token"),
    (13, "laldinthari", "kaggle/acct3/access_token"),
    (14, "spectatorlone", "kaggle/acct6/access_token"),
    (15, "lalsangkima", "kaggle/acct4/access_token"),
    (16, "lalsangkima", "kaggle/acct4/access_token"),
    (17, "lalsangkima", "kaggle/acct4/access_token"),
    (18, "spectatorlone", "kaggle/acct6/access_token"),
    (19, "spectatorlone", "kaggle/acct6/access_token"),
    (20, "remruata", "kaggle/acct5/access_token"),
    (21, "remruata", "kaggle/acct5/access_token"),
    (22, "lalthazualasailo", "kaggle/acct1/access_token"),
    (23, "zomuanpuia", "kaggle/acct2/access_token"),
    (24, "laldinthari", "kaggle/acct3/access_token"),
    (25, "lalsangkima", "kaggle/acct4/access_token"),
    (26, "lalsangkima", "kaggle/acct4/access_token"),
    (27, "spectatorlone", "kaggle/acct6/access_token"),
    (28, "spectatorlone", "kaggle/acct6/access_token"),
    (29, "stephen34", "kaggle/stephen34/access_token"),
    (30, "stephen34", "kaggle/stephen34/access_token"),
    (31, "stephen34", "kaggle/stephen34/access_token"),
    (32, "stephen34", "kaggle/stephen34/access_token"),
    (33, "stephen34", "kaggle/stephen34/access_token"),
]

tokens = {tp: open(os.path.join(REPO, tp)).read().strip() for _, _, tp in FLEET}

def check_one(item):
    s, u, tp = item
    s_tag = f"{s:02d}"
    kid = f"{u}/ipscan-cl-shodan-{s_tag}"
    env = os.environ.copy()
    env["KAGGLE_API_TOKEN"] = tokens[tp]
    env["KAGGLE_USERNAME"] = u
    env["KAGGLE_KEY"] = tokens[tp]
    r = subprocess.run(["kaggle", "kernels", "status", kid], env=env, capture_output=True, text=True, timeout=20)
    out = (r.stdout + " " + r.stderr).strip()
    status = "UNKNOWN"
    for line in out.splitlines():
        if "404" in line or "not found" in line.lower() or "does not exist" in line.lower():
            status = "NOT_FOUND / DELETED"
            break
        if "status" in line.lower():
            cleaned = line.strip().replace("Warning: Looks like you're using an outdated `kaggle` version (installed: 2.2.4), please consider upgrading to the latest version (2.2.5)", "").strip()
            if "has status" in cleaned:
                status = cleaned.split("has status")[-1].replace('"', "").replace("KernelWorkerStatus.", "").strip()
            else:
                status = cleaned
            break
    return s, u, kid, status

with ThreadPoolExecutor(max_workers=8) as pool:
    results = list(pool.map(check_one, FLEET))

print("=== ALL SHARDS STATUS ===")
acct_counts = {}
running_total = 0

for s, u, kid, st in sorted(results):
    if u not in acct_counts:
        acct_counts[u] = {"RUNNING": 0, "OTHER": 0, "DELETED": 0, "TOTAL": 0}
    acct_counts[u]["TOTAL"] += 1
    if "RUNNING" in st:
        acct_counts[u]["RUNNING"] += 1
        running_total += 1
    elif "DELETED" in st or "NOT_FOUND" in st:
        acct_counts[u]["DELETED"] += 1
    else:
        acct_counts[u]["OTHER"] += 1
    if u == "stephen34":
        print(f"shard_{s:02d} ({u}): {st}")

print("\n=== STEPHEN34 BREAKDOWN ===")
s_running = acct_counts["stephen34"]["RUNNING"]
s_free = 5 - s_running
print(f"stephen34 Running Shards : {s_running}")
print(f"stephen34 Free Slots     : {s_free} (Max capacity: 5)")

print("\n=== PER-ACCOUNT RUNNING ===")
for u, c in sorted(acct_counts.items()):
    print(f"  {u:18s}: {c['RUNNING']} running / {c['TOTAL']} assigned ({5 - c['RUNNING']} slots free)")

print(f"\nTOTAL RUNNING ACROSS ALL ACCOUNTS: {running_total}")
