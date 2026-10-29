import os
import sys
import json
import subprocess

REPO_ROOT = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser("~/.kaggle/kaggle.json")

FLEET = {
    "remruata": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct5", "access_token"),
        "kernels": [("00", "remruata/ipscan-cl-shodan-00"),
                    ("01", "remruata/ipscan-cl-shodan-01"),
                    ("20", "remruata/ipscan-cl-shodan-20"),
                    ("21", "remruata/ipscan-cl-shodan-21"),
                    ("harvest", "remruata/ipscan-cl-harvest")]
    },
    "lalthazualasailo": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct1", "access_token"),
        "kernels": [("02", "lalthazualasailo/ipscan-cl-shodan-02"),
                    ("03", "lalthazualasailo/ipscan-cl-shodan-03"),
                    ("04", "lalthazualasailo/ipscan-cl-shodan-04"),
                    ("05", "lalthazualasailo/ipscan-cl-shodan-05"),
                    ("22", "lalthazualasailo/ipscan-cl-shodan-22")]
    },
    "zomuanpuia": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct2", "access_token"),
        "kernels": [("06", "zomuanpuia/ipscan-cl-shodan-06"),
                    ("07", "zomuanpuia/ipscan-cl-shodan-07"),
                    ("08", "zomuanpuia/ipscan-cl-shodan-08"),
                    ("09", "zomuanpuia/ipscan-cl-shodan-09"),
                    ("23", "zomuanpuia/ipscan-cl-shodan-23")]
    },
    "laldinthari": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct3", "access_token"),
        "kernels": [("10", "laldinthari/ipscan-cl-shodan-10"),
                    ("11", "laldinthari/ipscan-cl-shodan-11"),
                    ("12", "laldinthari/ipscan-cl-shodan-12"),
                    ("13", "laldinthari/ipscan-cl-shodan-13"),
                    ("24", "laldinthari/ipscan-cl-shodan-24")]
    },
    "lalsangkima": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct4", "access_token"),
        "kernels": [("15", "lalsangkima/ipscan-cl-shodan-15"),
                    ("16", "lalsangkima/ipscan-cl-shodan-16"),
                    ("17", "lalsangkima/ipscan-cl-shodan-17"),
                    ("25", "lalsangkima/ipscan-cl-shodan-25"),
                    ("26", "lalsangkima/ipscan-cl-shodan-26")]
    },
    "spectatorlone": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "acct6", "access_token"),
        "kernels": [("14", "spectatorlone/ipscan-cl-shodan-14"),
                    ("18", "spectatorlone/ipscan-cl-shodan-18"),
                    ("19", "spectatorlone/ipscan-cl-shodan-19"),
                    ("27", "spectatorlone/ipscan-cl-shodan-27"),
                    ("28", "spectatorlone/ipscan-cl-shodan-28")]
    },
    "stephen34": {
        "token_file": os.path.join(REPO_ROOT, "kaggle", "stephen34", "access_token"),
        "kernels": [("29", "stephen34/ipscan-cl-shodan-29"),
                    ("30", "stephen34/ipscan-cl-shodan-30"),
                    ("31", "stephen34/ipscan-cl-shodan-31"),
                    ("32", "stephen34/ipscan-cl-shodan-32"),
                    ("33", "stephen34/ipscan-cl-shodan-33")]
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

print("=== STEP 2 - KAGGLE HEALTH CHECK ===")
print(f"{'Shard':<10} | {'Account':<18} | {'Status'}")
print("-" * 55)

running_per_acct = {}
not_running = []
any_over_5 = False

for uname, info in FLEET.items():
    set_creds(uname, info["token_file"])
    running_cnt = 0
    for s_name, ref in info["kernels"]:
        out = run(f"kaggle kernels status {ref}")
        status = "UNKNOWN"
        for line in out.split("\n"):
            if "status" in line.lower() or "kernelworkerstatus" in line.lower():
                status = line.strip()
                break
        if "RUNNING" in status:
            running_cnt += 1
            status_clean = "RUNNING"
        else:
            status_clean = status if status != "UNKNOWN" else (out or "NOT_FOUND")
            not_running.append((s_name, uname, status_clean))
        
        print(f"{s_name:<10} | {uname:<18} | {status_clean}")
    
    running_per_acct[uname] = running_cnt
    if running_cnt > 5:
        any_over_5 = True

print("-" * 55)
print("\nRUNNING count per account:")
for uname, cnt in running_per_acct.items():
    print(f"  {uname:<18}: {cnt}")

if any_over_5:
    print("\nFAILED: One or more accounts exceed 5 concurrent sessions!")
    sys.exit(1)

print("\nKernels NOT RUNNING:")
if not_running:
    for s_name, uname, st in not_running:
        print(f"  Shard {s_name} ({uname}): {st}")
    print("KAGGLE HEALTH FAILED")
else:
    print("  None (All 35 kernels are RUNNING)")
    print("KAGGLE HEALTH OK")
