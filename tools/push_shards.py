import os
import sys
import subprocess
import time

REPO_ROOT = r"D:\DEpinFarm"
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
from watchdog import FLEET_MAP, set_kaggle_creds, run_cmd, check_account_status

def push_shards_for_account(uname, shard_indices):
    info = FLEET_MAP[uname]
    with open(info["token_file"], "r", encoding="utf-8") as tf:
        token = tf.read().strip()
    set_kaggle_creds(uname, token)

    print(f"=== Pushing shards {shard_indices} to {uname} ===")
    for s in shard_indices:
        s_tag = f"{s:02d}"
        shard_dir = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{s_tag}")
        print(f"Pushing cl_shodan_{s_tag}...")
        out, err, code = run_cmd(f'kaggle kernels push -p "{shard_dir}"')
        print(f"[{s_tag}] code={code}: {out or err}")
        time.sleep(2)

def print_all_status():
    print("\n--- CURRENT RUNNING STATUS ---")
    for uname, info in FLEET_MAP.items():
        running, missing = check_account_status(uname, info)
        print(f"{uname}: RUNNING={len(running)} ({running}), NOT_RUNNING={len(missing)} ({missing})")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "lalthazualasailo"
    if target == "lalthazualasailo":
        push_shards_for_account("lalthazualasailo", [0, 1, 2, 3, 4])
    elif target == "laldinthari":
        push_shards_for_account("laldinthari", [5, 6, 7, 8, 9])
    else:
        print(f"Unknown target: {target}")
        sys.exit(1)
    
    # Wait a few seconds for Kaggle to register the kernels before status check
    print("Waiting 15 seconds for kernels to initialize...")
    time.sleep(15)
    print_all_status()
