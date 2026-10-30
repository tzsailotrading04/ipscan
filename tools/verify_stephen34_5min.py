import os
import sys
import json
import subprocess

REPO = r"D:\DEpinFarm"
token_file = os.path.join(REPO, "kaggle", "stephen34", "access_token")
with open(token_file, "r", encoding="utf-8") as f:
    token = f.read().strip()

kaggle_json = os.path.expanduser("~/.kaggle/kaggle.json")
with open(kaggle_json, "w", encoding="utf-8") as f:
    json.dump({"username": "stephen34", "key": token}, f, indent=2)

env = os.environ.copy()
env["KAGGLE_USERNAME"] = "stephen34"
env["KAGGLE_KEY"] = token
env["KAGGLE_API_TOKEN"] = token

shards = ["29", "30", "31", "32", "33"]
statuses = {}

for s in shards:
    slug = f"stephen34/ipscan-cl-shodan-{s}"
    res = subprocess.run(["kaggle", "kernels", "status", slug], env=env, capture_output=True, text=True)
    out = (res.stdout + " " + res.stderr).strip()
    status = "UNKNOWN"
    clean_lines = [l for l in out.splitlines() if "Warning: Looks like" not in l]
    clean_out = " ".join(clean_lines)

    if any(k in clean_out.lower() for k in ["404", "not found", "does not exist", "denied"]):
        status = "NOT FOUND / DELETED"
    else:
        for line in clean_lines:
            if "has status" in line:
                status = line.split("has status")[-1].replace('"', "").replace("KernelWorkerStatus.", "").strip()
                break
            elif "status" in line.lower():
                status = line.strip()
                break
    statuses[s] = status
    print(f"shard_{s}: {status} (raw: {clean_out[:80]})")

running = [s for s, st in statuses.items() if "RUNNING" in st]
deleted = [s for s, st in statuses.items() if "DELETED" in st or "NOT FOUND" in st]

print("\n=== STEPHEN34 5-MINUTE VERIFICATION ===")
print(f"Running shards count : {len(running)} (shards: {', '.join(running)})")
print(f"Free slots count    : {5 - len(running)} free")
print(f"Shard 32 status     : {statuses.get('32')}")
print(f"Shard 33 status     : {statuses.get('33')}")
if "32" in deleted and "33" in deleted:
    print("VERDICT: 32 and 33 are STILL GONE. Slots permanently freed.")
else:
    print("VERDICT: UNEXPECTED STATE")
