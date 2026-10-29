"""
tools/repush_fleet_complete.py
Orchestrates:
1. Deleting all running kernels across all 6 accounts to quiet the git ref race.
2. Fetching, merging, and pushing the helper commit to GitHub origin/main cleanly.
3. Repushing all 20 shards per account range:
   - Token swap into ~/.kaggle/kaggle.json without BOM
   - Setting KAGGLE_USERNAME, KAGGLE_KEY, KAGGLE_API_TOKEN
   - Running kaggle kernels delete -y <user>/ipscan-cl-shodan-NN
   - Sleeping 4s
   - Running kaggle kernels push -p kaggle\\cl_shodan_NN
4. Repushing the harvest kernel last on acct5.
5. Querying and reporting status for all 21 deployed kernels.
6. Restoring original ~/.kaggle/kaggle.json.
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

def run_cmd(cmd_list, timeout=45):
    try:
        r = subprocess.run(cmd_list, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout + "\n" + r.stderr).strip()
        filtered = "\n".join([l for l in out.splitlines() if "Warning: Looks like you're using an outdated" not in l and l.strip()])
        return r.returncode, filtered
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"

def main():
    # 0. Backup original kaggle.json
    orig_kaggle_json = None
    if os.path.exists(KAGGLE_JSON):
        with open(KAGGLE_JSON, "r", encoding="utf-8") as f:
            orig_kaggle_json = f.read()

    try:
        print("=" * 75)
        print("PHASE 1: STOPPING/DELETING RUNNING FLEET TO HALT REMOTE GIT CONTENTION")
        print("=" * 75)
        for acct, user, shards in ACCOUNTS:
            set_kaggle_token(acct, user)
            for s in shards:
                kid = f"{user}/ipscan-cl-shodan-{s}"
                print(f"Stopping/deleting {kid}...", flush=True)
                code, out = run_cmd(["kaggle", "kernels", "delete", "-y", kid])
                print(f"  -> {out or 'OK'}")
        
        # Also stop harvest
        set_kaggle_token(HARVEST[0], HARVEST[1])
        print(f"Stopping/deleting harvest: {HARVEST[3]}...", flush=True)
        code, out = run_cmd(["kaggle", "kernels", "delete", "-y", HARVEST[3]])
        print(f"  -> {out or 'OK'}")

        print("\nWaiting 6 seconds for Kaggle runner processes to fully terminate...", flush=True)
        time.sleep(6)

        print("\n" + "=" * 75)
        print("PHASE 2: COMMITTING AND PUSHING HELPER PATCH TO GITHUB ORIGIN/MAIN")
        print("=" * 75)
        git_pushed = False
        for attempt in range(1, 16):
            print(f"Git sync attempt {attempt}/15...", flush=True)
            run_cmd(["git", "-C", ROOT, "fetch", "origin", "main"])
            m_code, m_out = run_cmd(["git", "-C", ROOT, "merge", "--no-edit", "origin/main"])
            if m_code != 0:
                print(f"  Merge failed: {m_out}, aborting merge and retrying...", flush=True)
                run_cmd(["git", "-C", ROOT, "merge", "--abort"])
                time.sleep(2)
                continue
            
            p_code, p_out = run_cmd(["git", "-C", ROOT, "push", "origin", "HEAD:main"])
            if p_code == 0:
                print(f"  SUCCESS! Pushed commit to origin/main on attempt {attempt}: {p_out}", flush=True)
                git_pushed = True
                break
            else:
                print(f"  Push failed: {p_out}, retrying in 2s...", flush=True)
                time.sleep(2)
        
        if not git_pushed:
            print("CRITICAL: Failed to push to GitHub! Aborting fleet repush to avoid deploying old code.", file=sys.stderr)
            sys.exit(1)

        print("\n" + "=" * 75)
        print("PHASE 3: REPUSHING ALL 20 SHARDS WITH NEW MERGE HELPER")
        print("=" * 75)
        push_results = {}

        for acct, user, shards in ACCOUNTS:
            print(f"\n--- Swapping to {acct} ({user}) for shards {','.join(shards)} ---")
            set_kaggle_token(acct, user)

            for s in shards:
                kid = f"{user}/ipscan-cl-shodan-{s}"
                kdir = os.path.join(ROOT, "kaggle", f"cl_shodan_{s}")
                
                print(f"\n[{s}] Running: kaggle kernels delete -y {kid}", flush=True)
                d_code, d_out = run_cmd(["kaggle", "kernels", "delete", "-y", kid])
                print(f"[{s}] Delete output: {d_out or 'OK'}")
                
                print(f"[{s}] Sleeping 4s...", flush=True)
                time.sleep(4)

                print(f"[{s}] Running: kaggle kernels push -p {kdir}", flush=True)
                p_code, p_out = run_cmd(["kaggle", "kernels", "push", "-p", kdir], timeout=60)
                print(f"[{s}] Push output: {p_out or 'OK'}")
                push_results[kid] = p_out

        print("\n" + "=" * 75)
        print("PHASE 4: REPUSHING HARVEST KERNEL LAST ON ACCT5 (remruata)")
        print("=" * 75)
        set_kaggle_token(HARVEST[0], HARVEST[1])
        h_kid = HARVEST[3]
        h_kdir = os.path.join(ROOT, "kaggle", HARVEST[2])

        print(f"Running: kaggle kernels delete -y {h_kid}", flush=True)
        d_code, d_out = run_cmd(["kaggle", "kernels", "delete", "-y", h_kid])
        print(f"Delete output: {d_out or 'OK'}")

        print("Sleeping 4s...", flush=True)
        time.sleep(4)

        print(f"Running: kaggle kernels push -p {h_kdir}", flush=True)
        p_code, p_out = run_cmd(["kaggle", "kernels", "push", "-p", h_kdir], timeout=60)
        print(f"Push output: {p_out or 'OK'}")
        push_results[h_kid] = p_out

        print("\n" + "=" * 75)
        print("PHASE 5: FINAL KERNEL STATUS FOR ALL 21 KERNELS")
        print("=" * 75)
        status_results = {}
        for acct, user, shards in ACCOUNTS:
            set_kaggle_token(acct, user)
            for s in shards:
                kid = f"{user}/ipscan-cl-shodan-{s}"
                s_code, s_out = run_cmd(["kaggle", "kernels", "status", kid])
                status_results[kid] = s_out
                print(f"{kid:40} : {s_out}")

        set_kaggle_token(HARVEST[0], HARVEST[1])
        s_code, s_out = run_cmd(["kaggle", "kernels", "status", HARVEST[3]])
        status_results[HARVEST[3]] = s_out
        print(f"{HARVEST[3]:40} : {s_out}")

        print("\n" + "=" * 75)
        print("SUMMARY TABLE OF PUSH RESULTS AND STATUS")
        print("=" * 75)
        for kid in sorted(push_results.keys()):
            p_res = push_results.get(kid, "").replace("\n", " ")
            s_res = status_results.get(kid, "").replace("\n", " ")
            print(f"{kid:40} | Push: {p_res[:45]:45} | Status: {s_res}")

    finally:
        # Restore original ~/.kaggle/kaggle.json
        if orig_kaggle_json is not None:
            with open(KAGGLE_JSON, "w", encoding="utf-8", newline="\n") as f:
                f.write(orig_kaggle_json)
            print("\nRestored original ~/.kaggle/kaggle.json")

if __name__ == "__main__":
    main()
