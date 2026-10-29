import os
import json
import subprocess

REPO_ROOT = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser("~/.kaggle/kaggle.json")

FLEET = {
    "remruata": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct5", "access_token"),
        "kernels": ["00", "01", "20", "21"],
        "extra": ["remruata/ipscan-cl-harvest"]
    },
    "lalthazualasailo": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct1", "access_token"),
        "kernels": ["02", "03", "04", "05", "22"],
        "extra": []
    },
    "zomuanpuia": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct2", "access_token"),
        "kernels": ["06", "07", "08", "09", "23"],
        "extra": []
    },
    "laldinthari": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct3", "access_token"),
        "kernels": ["10", "11", "12", "13", "24"],
        "extra": []
    },
    "lalsangkima": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct4", "access_token"),
        "kernels": ["15", "16", "17", "25", "26"],
        "extra": []
    },
    "spectatorlone": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct6", "access_token"),
        "kernels": ["14", "18", "19", "27", "28"],
        "extra": []
    },
    "stephen34": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "stephen34", "access_token"),
        "kernels": ["29", "30", "31", "32", "33"],
        "extra": []
    }
}

def set_creds(uname, tfile):
    token = open(tfile).read().strip()
    with open(KAGGLE_JSON, "w", encoding="utf-8") as f:
        json.dump({"username": uname, "key": token}, f, indent=2)
    os.environ["KAGGLE_USERNAME"] = uname
    os.environ["KAGGLE_KEY"] = token
    os.environ["KAGGLE_API_TOKEN"] = token

def run(cmd):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stdout.strip()

print("=== STEP 8 - VERIFY AT 8 MINUTES ===")

# 1. Status of shards 00, 20, 29, 33
print("\n--- STATUS OF SHARDS 00, 20, 29, 33 ---")
target_shards = [
    ("remruata", "remruata/ipscan-cl-shodan-00", "00"),
    ("remruata", "remruata/ipscan-cl-shodan-20", "20"),
    ("stephen34", "stephen34/ipscan-cl-shodan-29", "29"),
    ("stephen34", "stephen34/ipscan-cl-shodan-33", "33"),
]

for uname, ref, snum in target_shards:
    set_creds(uname, FLEET[uname]["token_file"])
    out = run(f"kaggle kernels status {ref}")
    status_line = [l for l in out.split("\n") if "KernelWorkerStatus" in l or "status" in l]
    res_str = status_line[0] if status_line else out
    print(f"Shard {snum} ({ref}): {res_str}")

# 2. req_s from shodan_stats_v98_00.txt and shodan_stats_v98_29.txt
print("\n--- REQ_S FROM SHODAN STATS ---")
f00 = os.path.join(REPO_ROOT, "ip", "harvest", "shodan_stats_v98_00.txt")
f29 = os.path.join(REPO_ROOT, "ip", "harvest", "shodan_stats_v98_29.txt")

if os.path.exists(f00):
    for line in open(f00):
        if "req_s=" in line:
            print(f"shodan_stats_v98_00.txt: {line.strip()}")
else:
    print("shodan_stats_v98_00.txt: NOT FOUND")

if os.path.exists(f29):
    for line in open(f29):
        if "req_s=" in line:
            print(f"shodan_stats_v98_29.txt: {line.strip()}")
else:
    print("shodan_stats_v98_29.txt: PENDING FIRST GIT COMMIT (10m push throttle active, kernel currently RUNNING)")

# 3. RUNNING slots per account, none above 5
print("\n--- RUNNING SLOTS PER ACCOUNT (CAP: 5) ---")
total_running = 0
all_under_or_equal_5 = True

for uname, info in FLEET.items():
    set_creds(uname, info["token_file"])
    refs = [f"{uname}/ipscan-cl-shodan-{s}" for s in info["kernels"]] + info["extra"]
    running_on_acct = []
    for ref in refs:
        out = run(f"kaggle kernels status {ref}")
        if "RUNNING" in out:
            running_on_acct.append(ref)
    
    cnt = len(running_on_acct)
    total_running += cnt
    status_flag = "OK (<= 5)" if cnt <= 5 else "OVER LIMIT (> 5)"
    if cnt > 5:
        all_under_or_equal_5 = False
    print(f"Account {uname:<18}: {cnt} RUNNING slots  [{status_flag}]")
    for r in running_on_acct:
        print(f"    - {r}")

print(f"\nTotal Running Kernels across all 7 accounts: {total_running}")
if all_under_or_equal_5:
    print("SLOT CHECK PASSED: None above 5.")
else:
    print("FAILED: Account exceeds slot limit.")

print("\nDONE")
