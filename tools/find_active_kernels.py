import os
import sys
import json
import subprocess

REPO = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser("~/.kaggle/kaggle.json")

ACCOUNTS = [
    ("remruata", os.path.join(REPO, "kaggle", "acct5", "access_token")),
    ("lalthazualasailo", os.path.join(REPO, "kaggle", "acct1", "access_token")),
    ("zomuanpuia", os.path.join(REPO, "kaggle", "acct2", "access_token")),
    ("laldinthari", os.path.join(REPO, "kaggle", "acct3", "access_token")),
    ("lalsangkima", os.path.join(REPO, "kaggle", "acct4", "access_token")),
    ("spectatorlone", os.path.join(REPO, "kaggle", "acct6", "access_token")),
]

def set_credentials(username, token_file):
    with open(token_file, "r", encoding="utf-8") as f:
        token = f.read().strip()
    os.environ["KAGGLE_API_TOKEN"] = token
    os.environ["KAGGLE_USERNAME"] = username
    os.environ["KAGGLE_KEY"] = token
    with open(KAGGLE_JSON, "w", encoding="utf-8") as f:
        json.dump({"username": username, "key": token}, f, indent=2)

for acct, tok_path in ACCOUNTS:
    set_credentials(acct, tok_path)
    res = subprocess.run(["kaggle", "kernels", "list", "--mine", "--page-size", "25"], capture_output=True, text=True)
    clean = [l for l in (res.stdout + res.stderr).splitlines() if "Warning: Looks like" not in l and l.strip()]
    print(f"\n=== ACCOUNT: {acct} ===")
    for l in clean:
        parts = l.split()
        if not parts: continue
        slug = parts[0]
        if "/" in slug:
            # check status
            st = subprocess.run(["kaggle", "kernels", "status", slug], capture_output=True, text=True)
            st_clean = [x.strip() for x in (st.stdout + st.stderr).splitlines() if "Warning: Looks like" not in x and x.strip()]
            status_line = " ".join(st_clean)
            if "RUNNING" in status_line or "QUEUED" in status_line:
                print(f"  ACTIVE: {slug} -> {status_line}")
