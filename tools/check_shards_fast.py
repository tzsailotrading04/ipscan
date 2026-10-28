import os, json, subprocess, concurrent.futures

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

def check_one(item):
    acct, k = item
    meta_path = os.path.join(ROOT, "kaggle", k, "kernel-metadata.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    tok_path = os.path.join(ROOT, "kaggle", acct, "access_token")
    token = open(tok_path, "r", encoding="utf-8").read().strip()
    env = os.environ.copy()
    env["KAGGLE_API_TOKEN"] = token
    kid = meta["id"]
    try:
        proc = subprocess.run([kaggle_bin, "kernels", "status", kid], env=env, capture_output=True, text=True, timeout=15)
        st = "UNKNOWN"
        for line in proc.stdout.splitlines():
            line = line.strip()
            if "status" in line:
                st = line.replace('"', '').split()[-1]
        return k, st
    except Exception as e:
        return k, f"ERR: {e}"

VERIFY_MAP = [
    ("acct1", ["cl_verify_0"]),
    ("acct2", ["cl_verify_1"]),
    ("acct3", ["cl_verify_2"]),
    ("acct4", ["cl_verify_3"]),
    ("acct5", ["cl_verify_4", "cl_verify_5"]),
    ("acct6", ["cl_verify_6", "cl_verify_7", "cl_verify_8"]),
]

if __name__ == "__main__":
    items = [(acct, k) for acct, klist in SHARDS for k in klist]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = dict(executor.map(check_one, items))

    print("=== SHARDS (20) ===")
    for k in sorted(results.keys()):
        print(f"{k}: {results[k]}")

    v_items = [(acct, k) for acct, klist in VERIFY_MAP for k in klist]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        v_results = dict(executor.map(check_one, v_items))

    print("\n=== VERIFIERS (9) ===")
    for k in sorted(v_results.keys()):
        print(f"{k}: {v_results[k]}")

