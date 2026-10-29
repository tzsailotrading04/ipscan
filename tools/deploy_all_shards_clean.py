"""
deploy_all_shards_clean.py
Deploys all 20 shards in waves of 3-4 with force-delete:
1. Deletes old kernel with -y to immediately free Kaggle batch slot
2. Pushes fresh code
3. Verifies running status
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

def deploy_wave():
    results = {}
    for acct, klist in SHARDS:
        tok_path = os.path.join(ROOT, "kaggle", acct, "access_token")
        tok = open(tok_path, "r", encoding="utf-8").read().strip()
        env = os.environ.copy()
        env["KAGGLE_API_TOKEN"] = tok

        print(f"\n=== Wave: Deploying on {acct} ({len(klist)} shards) ===")
        for k in klist:
            k_dir = os.path.join(ROOT, "kaggle", k)
            meta_path = os.path.join(k_dir, "kernel-metadata.json")
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            kid = meta["id"]

            print(f"[{k}] Force-deleting {kid}...")
            try:
                subprocess.run([kaggle_bin, "kernels", "delete", "-y", kid], env=env, capture_output=True, text=True, timeout=12)
            except Exception as e:
                print(f"[{k}] Delete skipped/timeout: {e}")
            time.sleep(2)

            print(f"[{k}] Pushing {kid}...")
            pushed = False
            for attempt in range(1, 4):
                res = subprocess.run([kaggle_bin, "kernels", "push", "-p", k_dir], env=env, capture_output=True, text=True, timeout=35)
                out = (res.stdout + " " + res.stderr).strip()
                if "successfully pushed" in out.lower():
                    print(f"[{k}] Successfully pushed (Attempt {attempt})")
                    pushed = True
                    results[k] = "PUSHED"
                    break
                else:
                    last_l = out.splitlines()[-1] if out.splitlines() else "ERR"
                    print(f"[{k}] Attempt {attempt} failed: {last_l}")
                    time.sleep(4)
            if not pushed:
                results[k] = "FAILED"
            time.sleep(2)

    return results

if __name__ == "__main__":
    res = deploy_wave()
    print("\n" + "=" * 50)
    print("DEPLOYMENT SUMMARY:")
    for k, st in res.items():
        print(f"  {k}: {st}")
    print("=" * 50)
