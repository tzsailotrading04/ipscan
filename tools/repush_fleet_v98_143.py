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
    ("acct4", ["cl_shodan_14", "cl_shodan_15", "cl_shodan_16", "cl_shodan_17"]),
    ("acct6", ["cl_shodan_18", "cl_shodan_19"]),
]

VERIFIERS = [
    ("acct1", ["cl_verify_0"]),
    ("acct2", ["cl_verify_1"]),
    ("acct3", ["cl_verify_2"]),
    ("acct4", ["cl_verify_3"]),
    ("acct5", ["cl_verify_4", "cl_verify_5"]),
    ("acct6", ["cl_verify_6", "cl_verify_7", "cl_verify_8"]),
]

def push_kernel(acct, kdir_name):
    tok_path = os.path.join(ROOT, "kaggle", acct, "access_token")
    token = open(tok_path, "r", encoding="utf-8").read().strip()
    env = os.environ.copy()
    env["KAGGLE_API_TOKEN"] = token

    p = os.path.join(ROOT, "kaggle", kdir_name)
    for attempt in range(1, 4):
        print(f"[{time.strftime('%H:%M:%S')}] Pushing {kdir_name} on {acct} (attempt {attempt})...", flush=True)
        res = subprocess.run([kaggle_bin, "kernels", "push", "-p", p], env=env, capture_output=True, text=True)
        out = (res.stdout + " " + res.stderr).strip()
        if "successfully" in out.lower() or res.returncode == 0:
            print(f"[{time.strftime('%H:%M:%S')}] OK: {kdir_name}: {out}", flush=True)
            return True
        elif "409" in out or "conflict" in out.lower():
            print(f"[{time.strftime('%H:%M:%S')}] 409 conflict on {kdir_name}, sleeping 5s...", flush=True)
            time.sleep(5)
        else:
            print(f"[{time.strftime('%H:%M:%S')}] WARN: {kdir_name}: {out}", flush=True)
            time.sleep(3)
    return False

def push_all():
    print("=== RE-PUSHING ALL 9 VERIFIERS ===", flush=True)
    for acct, klist in VERIFIERS:
        for k in klist:
            push_kernel(acct, k)
            time.sleep(2)

    print("\n=== RE-PUSHING ALL 20 SHARDS ===", flush=True)
    for acct, klist in SHARDS:
        for k in klist:
            push_kernel(acct, k)
            time.sleep(2)

    print("\n=== FLEET RE-PUSH COMPLETE ===", flush=True)

if __name__ == "__main__":
    push_all()
