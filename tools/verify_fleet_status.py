import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor

REPO = r"D:\DEpinFarm"

print("=" * 70)
print("  ALL 29 REMAINING SHARDS: SHARD_IDX & NUM_SHARDS")
print("=" * 70)
shard_info = []
for i in range(29):
    tag = f"{i:02d}"
    run_file = os.path.join(REPO, "kaggle", f"cl_shodan_{tag}", "run.py")
    with open(run_file, "r", encoding="utf-8") as f:
        content = f.read()

    m_idx = re.search(r"^\s*SHARD_IDX\s*=\s*(\d+)", content, re.MULTILINE)
    m_num = re.search(r"^\s*NUM_SHARDS\s*=\s*(\d+)", content, re.MULTILINE)

    idx_val = m_idx.group(1) if m_idx else "MISSING"
    num_val = m_num.group(1) if m_num else "MISSING"
    shard_info.append((tag, idx_val, num_val))

for tag, idx_val, num_val in shard_info:
    print(f"Shard {tag}: SHARD_IDX = {idx_val:<2} | NUM_SHARDS = {num_val}")

print("\n" + "=" * 70)
print("  INDIVIDUAL SHARD RUN STATUS (ALL 29 SHARDS)")
print("=" * 70)
FLEET_MAP = {
    "remruata": {
        "token_file": os.path.join(REPO, "kaggle", "acct5", "access_token"),
        "shards": [0, 1, 20, 21],
    },
    "lalthazualasailo": {
        "token_file": os.path.join(REPO, "kaggle", "acct1", "access_token"),
        "shards": [2, 3, 4, 5, 22],
    },
    "zomuanpuia": {
        "token_file": os.path.join(REPO, "kaggle", "acct2", "access_token"),
        "shards": [6, 7, 8, 9, 23],
    },
    "laldinthari": {
        "token_file": os.path.join(REPO, "kaggle", "acct3", "access_token"),
        "shards": [10, 11, 12, 13, 24],
    },
    "lalsangkima": {
        "token_file": os.path.join(REPO, "kaggle", "acct4", "access_token"),
        "shards": [15, 16, 17, 25, 26],
    },
    "spectatorlone": {
        "token_file": os.path.join(REPO, "kaggle", "acct6", "access_token"),
        "shards": [14, 18, 19, 27, 28],
    },
}

def check_shard(item):
    uname, s, tpath = item
    s_tag = f"{s:02d}"
    ref = f"{uname}/ipscan-cl-shodan-{s_tag}"
    tok = open(tpath).read().strip()
    env = os.environ.copy()
    env["KAGGLE_USERNAME"] = uname
    env["KAGGLE_KEY"] = tok
    env["KAGGLE_API_TOKEN"] = tok
    try:
        r = subprocess.run(
            ["kaggle", "kernels", "status", ref],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (r.stdout + " " + r.stderr).strip()
        status = "UNKNOWN"
        for line in out.splitlines():
            if "has status" in line:
                status = line.split("has status")[-1].replace('"', "").replace("KernelWorkerStatus.", "").strip()
                break
            elif "404" in line or "not found" in line.lower():
                status = "NOT_FOUND"
                break
        if status == "UNKNOWN":
            if "RUNNING" in out:
                status = "RUNNING"
            elif "COMPLETE" in out:
                status = "COMPLETE"
        return uname, s, ref, status
    except Exception as e:
        return uname, s, ref, f"ERROR: {e}"

items = []
for uname, info in FLEET_MAP.items():
    for s in info["shards"]:
        items.append((uname, s, info["token_file"]))

with ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(check_shard, items))

acct_running = {u: 0 for u in FLEET_MAP}
acct_total = {u: len(FLEET_MAP[u]["shards"]) for u in FLEET_MAP}

for uname, s, ref, status in sorted(results, key=lambda x: x[1]):
    if "RUNNING" in status:
        acct_running[uname] += 1
    print(f"  Shard {s:02d} ({uname:<17}): {status}")

print("\n" + "=" * 70)
print("  RUNNING COUNT PER ACCOUNT")
print("=" * 70)
for u in FLEET_MAP:
    print(f"  {u:<18}: {acct_running[u]} RUNNING / {acct_total[u]} assigned")

tot_running = sum(acct_running.values())
print(f"\n  TOTAL RUNNING: {tot_running} / 29 shards across 6 accounts")
print("=" * 70)
