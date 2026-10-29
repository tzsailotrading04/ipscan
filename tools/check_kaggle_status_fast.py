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

def check_all():
    results = {}
    for acct, klist in SHARDS:
        tok_path = os.path.join(ROOT, "kaggle", acct, "access_token")
        tok = open(tok_path, "r", encoding="utf-8").read().strip()
        env = os.environ.copy()
        env["KAGGLE_API_TOKEN"] = tok

        for k in klist:
            meta_path = os.path.join(ROOT, "kaggle", k, "kernel-metadata.json")
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            kid = meta["id"]
            try:
                res = subprocess.run([kaggle_bin, "kernels", "status", kid], env=env, capture_output=True, text=True, timeout=12)
                out = res.stdout.strip()
                status = "UNKNOWN"
                for l in out.splitlines():
                    if "has status" in l:
                        status = l.split("has status")[-1].strip(" \"'")
                results[k] = status
                print(f"{k}: {status}")
            except Exception as e:
                results[k] = f"ERR: {e}"
                print(f"{k}: ERR: {e}")
    return results

if __name__ == "__main__":
    check_all()
