import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

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

def check_kernel(args):
    acct, k = args
    tok_path = os.path.join(ROOT, "kaggle", acct, "access_token")
    tok = open(tok_path, "r", encoding="utf-8").read().strip()
    env = os.environ.copy()
    env["KAGGLE_API_TOKEN"] = tok

    k_dir = os.path.join(ROOT, "kaggle", k)
    meta_path = os.path.join(k_dir, "kernel-metadata.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    kid = meta["id"]

    cmd = [kaggle_bin, "kernels", "status", kid]
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    out = res.stdout.strip()
    status = "UNKNOWN"
    for line in out.splitlines():
        if kid in line or "has status" in line:
            status = line.strip()
            break
    if not status or status == "UNKNOWN":
        status = out.replace("\n", " ")[:60]
    return acct, k, kid, status

def main():
    tasks = []
    for acct, klist in SHARDS:
        for k in klist:
            tasks.append((acct, k))

    print(f"Checking {len(tasks)} Kaggle shards across 6 accounts...")
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(check_kernel, tasks))

    running = 0
    queued = 0
    complete = 0
    error = 0
    other = 0

    print("\nShard Statuses:")
    for acct, k, kid, st in sorted(results, key=lambda x: x[1]):
        print(f"  {k:15s} ({acct:5s}): {st}")
        st_low = st.lower()
        if "running" in st_low:
            running += 1
        elif "queued" in st_low:
            queued += 1
        elif "complete" in st_low:
            complete += 1
        elif "error" in st_low or "failed" in st_low:
            error += 1
        else:
            other += 1

    print("\nSummary:")
    print(f"  RUNNING:  {running}")
    print(f"  QUEUED:   {queued}")
    print(f"  COMPLETE: {complete}")
    print(f"  ERROR:    {error}")
    print(f"  OTHER:    {other}")
    print(f"  TOTAL:    {len(results)}")

if __name__ == "__main__":
    main()
