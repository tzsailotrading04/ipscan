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
    ("stephen34", os.path.join(REPO, "kaggle", "stephen34", "access_token")),
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
    res = subprocess.run(["kaggle", "kernels", "list", "--mine", "--page-size", "15"], capture_output=True, text=True)
    clean = [l for l in (res.stdout + res.stderr).splitlines() if "Warning: Looks like" not in l]
    print(f"=== {acct} ===")
    for l in clean[:12]:
        print(" ", l)
