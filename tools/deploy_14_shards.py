import os
import sys
import json
import time
import subprocess

REPO_ROOT = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser("~/.kaggle/kaggle.json")

ACCOUNT_MAP = {
    "acct5": {"username": "remruata", "shards": [20, 21], "token_path": os.path.join(REPO_ROOT, "kaggle", "acct5", "access_token")},
    "acct1": {"username": "lalthazualasailo", "shards": [22], "token_path": os.path.join(REPO_ROOT, "kaggle", "acct1", "access_token")},
    "acct2": {"username": "zomuanpuia", "shards": [23], "token_path": os.path.join(REPO_ROOT, "kaggle", "acct2", "access_token")},
    "acct3": {"username": "laldinthari", "shards": [24], "token_path": os.path.join(REPO_ROOT, "kaggle", "acct3", "access_token")},
    "acct4": {"username": "lalsangkima", "shards": [25, 26], "token_path": os.path.join(REPO_ROOT, "kaggle", "acct4", "access_token")},
    "acct6": {"username": "spectatorlone", "shards": [27, 28], "token_path": os.path.join(REPO_ROOT, "kaggle", "acct6", "access_token")},
    "acct0": {"username": "stephen34", "shards": [29, 30, 31, 32, 33], "token_path": os.path.join(REPO_ROOT, "kaggle", "stephen34", "access_token")},
}

def set_kaggle_creds(username, token):
    os.makedirs(os.path.dirname(KAGGLE_JSON), exist_ok=True)
    with open(KAGGLE_JSON, "w", encoding="utf-8") as f:
        json.dump({"username": username, "key": token}, f, indent=2)
    os.environ["KAGGLE_USERNAME"] = username
    os.environ["KAGGLE_KEY"] = token
    os.environ["KAGGLE_API_TOKEN"] = token

def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def main():
    print(f"{'Shard':<8} | {'Account':<18} | {'Kernel Ref':<35} | {'Returned Status'}")
    print("-" * 85)

    for acct_id, acct_info in ACCOUNT_MAP.items():
        uname = acct_info["username"]
        tpath = acct_info["token_path"]
        if not os.path.exists(tpath):
            print(f"FAILED: Token file missing for {acct_id} at {tpath}")
            sys.exit(1)
        with open(tpath, "r", encoding="utf-8") as tf:
            token = tf.read().strip()

        set_kaggle_creds(uname, token)

        for s in acct_info["shards"]:
            s_tag = f"{s:02d}"
            shard_dir = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{s_tag}")
            kernel_ref = f"{uname}/ipscan-cl-shodan-{s_tag}"

            # Push kernel
            push_out, push_err, pcode = run_cmd(f'kaggle kernels push -p "{shard_dir}"')
            if pcode != 0:
                status_str = f"PUSH_ERR: {push_err or push_out}"
            else:
                # Query status
                time.sleep(3)
                stat_out, stat_err, scode = run_cmd(f'kaggle kernels status {kernel_ref}')
                status_str = stat_out if stat_out else (push_out or "PUSHED")

            print(f"cl_{s_tag:<5} | {uname:<18} | {kernel_ref:<35} | {status_str}")

if __name__ == "__main__":
    main()
