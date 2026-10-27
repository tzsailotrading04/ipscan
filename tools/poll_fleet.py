import os
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = r"D:\DEpinFarm"
userprofile = os.environ.get("USERPROFILE", r"C:\Users\pc")
kaggle_bin = os.path.join(userprofile, r"AppData\Local\Python\pythoncore-3.14-64\Scripts\kaggle.exe")

ALL_KERNELS = [
    # Shards
    ("acct5", "cl_shodan_00"), ("acct5", "cl_shodan_01"),
    ("acct1", "cl_shodan_02"), ("acct1", "cl_shodan_03"), ("acct1", "cl_shodan_04"), ("acct1", "cl_shodan_05"),
    ("acct2", "cl_shodan_06"), ("acct2", "cl_shodan_07"), ("acct2", "cl_shodan_08"), ("acct2", "cl_shodan_09"),
    ("acct3", "cl_shodan_10"), ("acct3", "cl_shodan_11"), ("acct3", "cl_shodan_12"), ("acct3", "cl_shodan_13"),
    ("acct4", "cl_shodan_14"), ("acct4", "cl_shodan_15"), ("acct4", "cl_shodan_16"), ("acct4", "cl_shodan_17"),
    ("acct6", "cl_shodan_18"), ("acct6", "cl_shodan_19"),
    # Verifiers
    ("acct1", "cl_verify_0"), ("acct2", "cl_verify_1"), ("acct3", "cl_verify_2"),
    ("acct4", "cl_verify_3"), ("acct5", "cl_verify_4"), ("acct5", "cl_verify_5"),
    ("acct6", "cl_verify_6"), ("acct6", "cl_verify_7"), ("acct6", "cl_verify_8"),
]

def check_one(item):
    acct, k = item
    tok_path = os.path.join(ROOT, "kaggle", acct, "access_token")
    if not os.path.exists(tok_path):
        return k, "NO_TOKEN"
    token = open(tok_path, "r", encoding="utf-8").read().strip()
    env = os.environ.copy()
    env["KAGGLE_API_TOKEN"] = token
    meta_path = os.path.join(ROOT, "kaggle", k, "kernel-metadata.json")
    if not os.path.exists(meta_path):
        return k, "NO_META"
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    kid = meta["id"]
    try:
        proc = subprocess.run([kaggle_bin, "kernels", "status", kid], env=env, capture_output=True, text=True, timeout=15)
        st = "UNKNOWN"
        for line in proc.stdout.splitlines():
            if 'status "' in line:
                st = line.split('"')[1]
            elif 'status ' in line:
                st = line.split()[-1]
        return k, st
    except Exception as e:
        return k, f"ERR: {e}"

def poll_all():
    with ThreadPoolExecutor(max_workers=15) as ex:
        results = dict(ex.map(check_one, ALL_KERNELS))
    
    shards = {k: v for k, v in results.items() if "shodan" in k}
    verifiers = {k: v for k, v in results.items() if "verify" in k}

    sh_running = sum(1 for s in shards.values() if "running" in s.lower() or "queued" in s.lower())
    vr_running = sum(1 for s in verifiers.values() if "running" in s.lower() or "queued" in s.lower())

    print(f"[{time.strftime('%H:%M:%S')}] Shards Running: {sh_running}/20 | Verifiers Running: {vr_running}/9", flush=True)
    print("\n--- Shards ---", flush=True)
    for k in sorted(shards.keys()):
        print(f"  {k}: {shards[k]}", flush=True)
    print("\n--- Verifiers ---", flush=True)
    for k in sorted(verifiers.keys()):
        print(f"  {k}: {verifiers[k]}", flush=True)

if __name__ == "__main__":
    poll_all()
