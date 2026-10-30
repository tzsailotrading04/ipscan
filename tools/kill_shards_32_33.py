import os
import sys
import json
import time
import subprocess

REPO = r"D:\DEpinFarm"
token_file = os.path.join(REPO, "kaggle", "stephen34", "access_token")
with open(token_file, "r", encoding="utf-8") as f:
    token = f.read().strip()

kaggle_json = os.path.expanduser("~/.kaggle/kaggle.json")
os.makedirs(os.path.dirname(kaggle_json), exist_ok=True)
with open(kaggle_json, "w", encoding="utf-8") as f:
    json.dump({"username": "stephen34", "key": token}, f, indent=2)

env = os.environ.copy()
env["KAGGLE_USERNAME"] = "stephen34"
env["KAGGLE_KEY"] = token
env["KAGGLE_API_TOKEN"] = token

def run_cmd(cmd):
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    out = (r.stdout + "\n" + r.stderr).strip()
    clean = [l for l in out.splitlines() if "Warning: Looks like you're using an outdated" not in l]
    return "\n".join(clean).strip()

print("STEP 1: Deleting shards 32 and 33 on stephen34...")
print("Executing: kaggle kernels delete -y stephen34/ipscan-cl-shodan-32")
out32 = run_cmd(["kaggle", "kernels", "delete", "-y", "stephen34/ipscan-cl-shodan-32"])
print(out32)

print("\nsleep 3")
time.sleep(3)

print("\nExecuting: kaggle kernels delete -y stephen34/ipscan-cl-shodan-33")
out33 = run_cmd(["kaggle", "kernels", "delete", "-y", "stephen34/ipscan-cl-shodan-33"])
print(out33)
