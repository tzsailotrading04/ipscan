import os
import sys

REPO_ROOT = r"D:\DEpinFarm"
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
from watchdog import FLEET_MAP, set_kaggle_creds, run_cmd

info = FLEET_MAP["lalthazualasailo"]
with open(info["token_file"]) as tf:
    token = tf.read().strip()
set_kaggle_creds("lalthazualasailo", token)

for s in ["01", "04"]:
    shard_dir = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{s}")
    out, err, code = run_cmd(f'kaggle kernels push -p "{shard_dir}"')
    print(f"--- Shard {s} (code={code}) ---")
    print("STDOUT:", out)
    print("STDERR:", err)
