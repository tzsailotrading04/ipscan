import os
import sys
import json
import time
import subprocess
from datetime import datetime

REPO_ROOT = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser("~/.kaggle/kaggle.json")

SHARDS_TO_RESTORE = [
    (21, "remruata", os.path.join(REPO_ROOT, "kaggle", "acct5", "access_token")),
    (22, "lalthazualasailo", os.path.join(REPO_ROOT, "kaggle", "acct1", "access_token")),
    (23, "zomuanpuia", os.path.join(REPO_ROOT, "kaggle", "acct2", "access_token")),
    (24, "laldinthari", os.path.join(REPO_ROOT, "kaggle", "acct3", "access_token")),
    (25, "lalsangkima", os.path.join(REPO_ROOT, "kaggle", "acct4", "access_token")),
    (26, "lalsangkima", os.path.join(REPO_ROOT, "kaggle", "acct4", "access_token")),
    (27, "spectatorlone", os.path.join(REPO_ROOT, "kaggle", "acct6", "access_token")),
    (28, "spectatorlone", os.path.join(REPO_ROOT, "kaggle", "acct6", "access_token")),
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

def run_cmd(args, env=None):
    res = subprocess.run(args, capture_output=True, text=True, env=env)
    out = (res.stdout + "\n" + res.stderr).strip()
    clean = [l for l in out.splitlines() if "Warning: Looks like" not in l]
    return "\n".join(clean).strip()

print("=== STEP 1: RESTORING & REPUSHING SHARDS 21-28 (3s GAP) ===")
results = {}

for s_idx, (s, acct, tok_path) in enumerate(SHARDS_TO_RESTORE):
    set_credentials(acct, tok_path)
    shard_dir = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{s:02d}")
    ts_str = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts_str}] Pushing shard {s:02d} ({acct})...", flush=True)
    out = run_cmd(["kaggle", "kernels", "push", "-p", shard_dir])
    results[s] = out
    print(f"[{ts_str}] Shard {s:02d} result: {out}", flush=True)
    
    if s_idx < len(SHARDS_TO_RESTORE) - 1:
        print("Waiting 3s...", flush=True)
        time.sleep(3)

print("\n=== STEP 2: LEAVING SHARDS 32 & 33 FREE FOR AGENT ===")
print("Shards 32 and 33 on stephen34 remain deleted and untouched.")

print("\n=== STATUS VERIFICATION FOR RESTORED SHARDS ===")
time.sleep(5)
for s, acct, tok_path in SHARDS_TO_RESTORE:
    set_credentials(acct, tok_path)
    slug = f"{acct}/ipscan-cl-shodan-{s:02d}"
    st_out = run_cmd(["kaggle", "kernels", "status", slug])
    print(f"Shard {s:02d} ({acct}) Status: {st_out}")
