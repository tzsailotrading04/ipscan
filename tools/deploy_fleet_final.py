"""
tools/deploy_fleet_final.py
Executes the final fleet deployment:
1. Swaps token per account into ~/.kaggle/kaggle.json without BOM.
2. Sets environment variables KAGGLE_USERNAME, KAGGLE_KEY, KAGGLE_API_TOKEN.
3. For each shard in account's range:
   - kaggle kernels delete -y <user>/ipscan-cl-shodan-NN
   - sleep 4
   - kaggle kernels push -p kaggle\\cl_shodan_NN
4. Repushes the harvest kernel last on acct5:
   - kaggle kernels delete -y remruata/ipscan-cl-harvest
   - sleep 4
   - kaggle kernels push -p kaggle\\cl_harvest
5. Queries and reports kaggle kernels status for all 21 kernels.
6. Restores original ~/.kaggle/kaggle.json.
"""
import json
import os
import subprocess
import time
import sys

ROOT = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser(r"~/.kaggle/kaggle.json")

ACCOUNTS = [
    ("acct5", "remruata", ["00", "01"]),
    ("acct1", "lalthazualasailo", ["02", "03", "04", "05"]),
    ("acct2", "zomuanpuia", ["06", "07", "08", "09"]),
    ("acct3", "laldinthari", ["10", "11", "12", "13"]),
    ("acct6", "spectatorlone", ["14", "18", "19"]),
    ("acct4", "lalsangkima", ["15", "16", "17"]),
]

HARVEST = ("acct5", "remruata", "cl_harvest", "remruata/ipscan-cl-harvest")

def set_kaggle_token(acct, user):
    tok_path = os.path.join(ROOT, "kaggle", acct, "access_token")
    with open(tok_path, "r", encoding="utf-8") as f:
        tok = f.read().strip()
    
    os.makedirs(os.path.dirname(KAGGLE_JSON), exist_ok=True)
    with open(KAGGLE_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"username": user, "key": tok}, f, indent=2)

    os.environ["KAGGLE_USERNAME"] = user
    os.environ["KAGGLE_KEY"] = tok
    os.environ["KAGGLE_API_TOKEN"] = tok
    print(f"[{acct}] Token active for user: {user}", flush=True)

def run_cmd(cmd_list, timeout=60):
    try:
        r = subprocess.run(cmd_list, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout + "\n" + r.stderr).strip()
        filtered = "\n".join([l for l in out.splitlines() if "Warning: Looks like you're using an outdated" not in l and l.strip()])
        return r.returncode, filtered
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"

def main():
    orig_kaggle_json = None
    if os.path.exists(KAGGLE_JSON):
        with open(KAGGLE_JSON, "r", encoding="utf-8") as f:
            orig_kaggle_json = f.read()

    push_results = {}
    status_results = {}

    try:
        print("=" * 75)
        print("DEPLOYING 20 SHARDS ACROSS 6 ACCOUNTS")
        print("=" * 75)

        for acct, user, shards in ACCOUNTS:
            print(f"\n>>> Setting up {acct} ({user}) for shards: {shards} <<<", flush=True)
            set_kaggle_token(acct, user)

            for s in shards:
                kid = f"{user}/ipscan-cl-shodan-{s}"
                kdir = os.path.join(ROOT, "kaggle", f"cl_shodan_{s}")

                print(f"\n--- Shard {s} ({kid}) ---", flush=True)
                print(f"1. Deleting existing kernel: kaggle kernels delete -y {kid}", flush=True)
                d_code, d_out = run_cmd(["kaggle", "kernels", "delete", "-y", kid])
                print(f"   Delete: {d_out or 'OK'}")

                print("2. Sleeping 4s...", flush=True)
                time.sleep(4)

                print(f"3. Pushing kernel: kaggle kernels push -p {kdir}", flush=True)
                p_code, p_out = run_cmd(["kaggle", "kernels", "push", "-p", kdir], timeout=60)
                print(f"   Push result: {p_out or 'OK'}")
                push_results[kid] = p_out

        print("\n" + "=" * 75)
        print("DEPLOYING HARVEST KERNEL LAST ON ACCT5 (remruata)")
        print("=" * 75)
        h_acct, h_user, h_dir, h_kid = HARVEST
        set_kaggle_token(h_acct, h_user)
        h_kdir = os.path.join(ROOT, "kaggle", h_dir)

        print(f"\n1. Deleting existing harvest kernel: kaggle kernels delete -y {h_kid}", flush=True)
        d_code, d_out = run_cmd(["kaggle", "kernels", "delete", "-y", h_kid])
        print(f"   Delete: {d_out or 'OK'}")

        print("2. Sleeping 4s...", flush=True)
        time.sleep(4)

        print(f"3. Pushing harvest kernel: kaggle kernels push -p {h_kdir}", flush=True)
        p_code, p_out = run_cmd(["kaggle", "kernels", "push", "-p", h_kdir], timeout=60)
        print(f"   Push result: {p_out or 'OK'}")
        push_results[h_kid] = p_out

        print("\nWaiting 10 seconds before polling kernel status...", flush=True)
        time.sleep(10)

        print("\n" + "=" * 75)
        print("POLLING FINAL KERNEL STATUS FOR ALL 21 KERNELS")
        print("=" * 75)
        for acct, user, shards in ACCOUNTS:
            set_kaggle_token(acct, user)
            for s in shards:
                kid = f"{user}/ipscan-cl-shodan-{s}"
                s_code, s_out = run_cmd(["kaggle", "kernels", "status", kid])
                status_results[kid] = s_out
                print(f"{kid:40} : {s_out}")

        set_kaggle_token(h_acct, h_user)
        s_code, s_out = run_cmd(["kaggle", "kernels", "status", h_kid])
        status_results[h_kid] = s_out
        print(f"{h_kid:40} : {s_out}")

        print("\n" + "=" * 75)
        print("COMPLETE REPORT: 21 KERNELS PUSH & STATUS")
        print("=" * 75)
        for kid in sorted(push_results.keys()):
            p_res = push_results.get(kid, "").replace("\n", " ")
            s_res = status_results.get(kid, "").replace("\n", " ")
            print(f"{kid:40} | Push: {p_res[:40]:40} | Status: {s_res}")

    finally:
        if orig_kaggle_json is not None:
            with open(KAGGLE_JSON, "w", encoding="utf-8", newline="\n") as f:
                f.write(orig_kaggle_json)
            print("\nRestored original ~/.kaggle/kaggle.json")

if __name__ == "__main__":
    main()
