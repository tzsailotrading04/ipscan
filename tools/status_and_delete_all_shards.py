import os
import sys
import json
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor

REPO = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser("~/.kaggle/kaggle.json")

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
    r = subprocess.run(["kaggle", "kernels", "status", kid], env=env, capture_output=True, text=True, timeout=15)
    out = (r.stdout + " " + r.stderr).strip()
    status = "UNKNOWN"
    clean_lines = [l for l in out.splitlines() if "Warning: Looks like" not in l and l.strip()]
    clean_out = " ".join(clean_lines)

    if any(k in clean_out.lower() for k in ["404", "not found", "does not exist", "denied"]):
        status = "NOT_FOUND / ALREADY_DELETED"
    else:
        for line in clean_lines:
            if "has status" in line:
                status = line.split("has status")[-1].replace('"', "").replace("KernelWorkerStatus.", "").strip()
                break
            elif "status" in line.lower():
                status = line.strip()
                break
    return s, u, kid, status

print("=================================================================")
print("           PART 1: CURRENT STATUS OF ALL 34 SHARDS               ")
print("=================================================================")
with ThreadPoolExecutor(max_workers=8) as pool:
    statuses = list(pool.map(check_one, FLEET))

statuses.sort(key=lambda x: x[0])
running_count = 0
deleted_count = 0
other_count = 0

for s, u, kid, st in statuses:
    print(f"Shard {s:02d} ({u:16s}): {st}")
    if "RUNNING" in st:
        running_count += 1
    elif "DELETED" in st or "NOT_FOUND" in st:
        deleted_count += 1
    else:
        other_count += 1

print(f"\nSTATUS SUMMARY: {running_count} RUNNING, {deleted_count} ALREADY_DELETED, {other_count} OTHER (Total: {len(statuses)})")

print("\n=================================================================")
print("           PART 2: DELETING ALL 34 SHARDS                        ")
print("=================================================================")

def set_credentials(username, token):
    os.environ["KAGGLE_API_TOKEN"] = token
    os.environ["KAGGLE_USERNAME"] = username
    os.environ["KAGGLE_KEY"] = token
    with open(KAGGLE_JSON, "w", encoding="utf-8") as f:
        json.dump({"username": username, "key": token}, f, indent=2)

delete_results = []
for s, u, tp in FLEET:
    tok = tokens[tp]
    set_credentials(u, tok)
    s_tag = f"{s:02d}"
    kid = f"{u}/ipscan-cl-shodan-{s_tag}"
    
    r = subprocess.run(["kaggle", "kernels", "delete", "-y", kid], capture_output=True, text=True)
    out = (r.stdout + "\n" + r.stderr).strip()
    clean = [l for l in out.splitlines() if "Warning: Looks like" not in l and l.strip()]
    res_str = " ".join(clean)
    delete_results.append((s, u, kid, res_str))
    print(f"[{time.strftime('%H:%M:%S')}] Shard {s:02d} ({kid}): {res_str}", flush=True)
    time.sleep(1.5)

print("\n=================================================================")
print("           PART 3: CONFIRMATION AUDIT                            ")
print("=================================================================")
with ThreadPoolExecutor(max_workers=8) as pool:
    audit = list(pool.map(check_one, FLEET))

all_gone = True
for s, u, kid, st in sorted(audit, key=lambda x: x[0]):
    if "NOT_FOUND" not in st and "DELETED" not in st:
        all_gone = False
        print(f"WARNING: Shard {s:02d} ({kid}) still reports: {st}")

if all_gone:
    print("ALL 34 SHARDS SUCCESSFULLY DELETED AND VERIFIED GONE.")
else:
    print("Some shards may still be terminating on Kaggle backend.")
