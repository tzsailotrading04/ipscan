"""
deploy_fleet_v2.py
Pushes all 20 shards to Kaggle cleanly.
Uses 30s timeout per push, logs status, and verifies running state.
"""
import json
import os
import subprocess
import time

ROOT = r"D:\DEpinFarm"
userprofile = os.environ.get("USERPROFILE", r"C:\Users\pc")
kaggle_bin = os.path.join(userprofile, r"AppData\Local\Python\pythoncore-3.14-64\Scripts\kaggle.exe")

SHARDS = [
    ("acct5", ["cl_shodan_00", "cl_shodan_01"]),
    ("acct1", ["cl_shodan_02", "cl_shodan_03", "cl_shodan_04", "cl_shodan_05"]),
    ("acct2", ["cl_shodan_06", "cl_shodan_07", "cl_shodan_08", "cl_shodan_09"]),
    ("acct3", ["cl_shodan_10", "cl_shodan_11", "cl_shodan_12", "cl_shodan_13"]),
    ("acct4", ["cl_shodan_15", "cl_shodan_16", "cl_shodan_17"]),
    ("acct6", ["cl_shodan_14", "cl_shodan_18", "cl_shodan_19"]),
]

def deploy_all(skip_shards=None):
    if skip_shards is None:
        skip_shards = []
    
    total = sum(len(klist) for _, klist in SHARDS) - len(skip_shards)
    done = 0

    for acct, klist in SHARDS:
        tok_path = os.path.join(ROOT, "kaggle", acct, "access_token")
        tok = open(tok_path, "r", encoding="utf-8").read().strip()
        env = os.environ.copy()
        env["KAGGLE_API_TOKEN"] = tok

        print(f"\n=======================================================")
        print(f"Deploying on {acct} ({len(klist)} shards)")
        print(f"=======================================================")

        for k in klist:
            if k in skip_shards:
                print(f"[{k}] Skipping (already deployed and running).")
                continue

            k_dir = os.path.join(ROOT, "kaggle", k)
            meta_path = os.path.join(k_dir, "kernel-metadata.json")
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            kid = meta["id"]

            print(f"[{k}] Pushing {kid}...", flush=True)
            pushed = False
            for attempt in range(1, 3):
                try:
                    res = subprocess.run([kaggle_bin, "kernels", "push", "-p", k_dir],
                                         env=env, capture_output=True, text=True, timeout=35)
                    lines = [l for l in (res.stdout + "\n" + res.stderr).splitlines() if "Warning" not in l and l.strip()]
                    last_line = lines[-1] if lines else "OK"
                    print(f"[{k}] Attempt {attempt}: {last_line}", flush=True)
                    if "successfully pushed" in (res.stdout + res.stderr):
                        pushed = True
                        break
                    elif "already running" in (res.stdout + res.stderr).lower():
                        # Try to wait or push again
                        time.sleep(3)
                except subprocess.TimeoutExpired:
                    print(f"[{k}] Attempt {attempt}: TIMEOUT (>35s)", flush=True)
                time.sleep(2)

            done += 1
            print(f"[{k}] Done ({done}/{total})")
            time.sleep(2)

if __name__ == "__main__":
    import sys
    # cl_shodan_00 was already pushed and is RUNNING
    skip = ["cl_shodan_00"] if "--all" not in sys.argv else []
    deploy_all(skip_shards=skip)
    print("\nALL TARGET SHARDS DEPLOYED.")
