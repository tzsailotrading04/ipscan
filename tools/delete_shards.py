"""
tools/delete_shards.py
Deletes all 20 Kaggle kernels: ipscan-cl-shodan-00 through ipscan-cl-shodan-19 across all accounts.
Then inspects remaining kernels per account to report available slots.
"""
import json
import os
import subprocess
import sys

ROOT = r"D:\DEpinFarm"
userprofile = os.environ.get("USERPROFILE", r"C:\Users\pc")
kaggle_bin = os.path.join(userprofile, r"AppData\Local\Python\pythoncore-3.14-64\Scripts\kaggle.exe")

SHARD_MAPPING = [
    ("acct5", ["cl_shodan_00", "cl_shodan_01"]),
    ("acct1", ["cl_shodan_02", "cl_shodan_03", "cl_shodan_04", "cl_shodan_05"]),
    ("acct2", ["cl_shodan_06", "cl_shodan_07", "cl_shodan_08", "cl_shodan_09"]),
    ("acct3", ["cl_shodan_10", "cl_shodan_11", "cl_shodan_12", "cl_shodan_13"]),
    ("acct4", ["cl_shodan_15", "cl_shodan_16", "cl_shodan_17"]),
    ("acct6", ["cl_shodan_14", "cl_shodan_18", "cl_shodan_19"]),
]

def get_env_for_acct(acct):
    tok_path = os.path.join(ROOT, "kaggle", acct, "access_token")
    if not os.path.exists(tok_path):
        return None
    with open(tok_path, "r", encoding="utf-8") as f:
        tok = f.read().strip()
    env = os.environ.copy()
    env["KAGGLE_API_TOKEN"] = tok
    return env

def delete_kernel(acct, k_folder):
    k_dir = os.path.join(ROOT, "kaggle", k_folder)
    meta_path = os.path.join(k_dir, "kernel-metadata.json")
    if not os.path.exists(meta_path):
        return k_folder, "NO_METADATA", ""
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    kid = meta["id"]

    env = get_env_for_acct(acct)
    if not env:
        return kid, "NO_TOKEN", ""

    cmd = [kaggle_bin, "kernels", "delete", "-y", kid]
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    out = (res.stdout + " " + res.stderr).strip()

    # Verify if deleted
    if res.returncode == 0 or "deleted" in out.lower() or "not found" in out.lower() or "does not exist" in out.lower():
        return kid, "DELETED", out
    else:
        return kid, "FAILED", out

def list_account_kernels(acct):
    env = get_env_for_acct(acct)
    if not env:
        return ["NO_TOKEN"]
    cmd = [kaggle_bin, "kernels", "list", "--mine", "--page-size", "20"]
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    lines = [l.strip() for l in res.stdout.splitlines() if l.strip() and not l.startswith("ref") and not l.startswith("---") and not l.startswith("Warning:")]
    return lines

def main():
    print("=== STARTING DELETION OF KERNELS CL_SHODAN_00 THROUGH 19 ===", flush=True)
    results = []

    for acct, k_list in SHARD_MAPPING:
        print(f"\nProcessing Account: {acct}", flush=True)
        for k in k_list:
            kid, status, out = delete_kernel(acct, k)
            print(f"  [{status}] {k} -> {kid} : {out[:80]}", flush=True)
            results.append((acct, k, kid, status))

    print("\n" + "="*70, flush=True)
    print("CHECKING REMAINING KERNELS & AVAILABLE SLOTS PER ACCOUNT", flush=True)
    print("="*70, flush=True)

    account_slots = {}
    for acct, _ in SHARD_MAPPING:
        active_list = list_account_kernels(acct)
        # Kaggle allows up to 30 concurrent private/public notebooks per account
        count = len(active_list)
        account_slots[acct] = (count, active_list)
        print(f"\nAccount: {acct} (Remaining Kernels: {count})")
        if count == 0:
            print("  (Empty - All slots free)")
        else:
            for item in active_list:
                print(f"  * {item}")

    print("\n" + "="*70, flush=True)
    print("SUMMARY OF DELETIONS", flush=True)
    print("="*70, flush=True)
    success_cnt = sum(1 for _, _, _, st in results if st == "DELETED")
    fail_cnt = len(results) - success_cnt
    print(f"Total Shards Targeted: {len(results)}")
    print(f"Successfully Deleted : {success_cnt}")
    print(f"Failed / Retried     : {fail_cnt}")

if __name__ == "__main__":
    main()
