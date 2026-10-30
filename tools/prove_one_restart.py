import os
import sys
import json
import time
import glob
import subprocess
from datetime import datetime

REPO = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser("~/.kaggle/kaggle.json")
SLUG = "remruata/ipscan-cl-shodan-21"
SHARD_DIR = os.path.join(REPO, "kaggle", "cl_shodan_21")

# Set remruata credentials
tok_file = os.path.join(REPO, "kaggle", "acct5", "access_token")
with open(tok_file, "r", encoding="utf-8") as f:
    token = f.read().strip()

env = os.environ.copy()
env["KAGGLE_USERNAME"] = "remruata"
env["KAGGLE_KEY"] = token
env["KAGGLE_API_TOKEN"] = token

os.makedirs(os.path.dirname(KAGGLE_JSON), exist_ok=True)
with open(KAGGLE_JSON, "w", encoding="utf-8") as f:
    json.dump({"username": "remruata", "key": token}, f, indent=2)

def run_cmd(args):
    r = subprocess.run(args, env=env, capture_output=True, text=True)
    out = (r.stdout + "\n" + r.stderr).strip()
    clean = [l for l in out.splitlines() if "Warning: Looks like" not in l and l.strip()]
    return "\n".join(clean).strip()

def get_status_raw(slug):
    out = run_cmd(["kaggle", "kernels", "status", slug])
    is_not_found = any(k in out.lower() for k in ["404", "not found", "does not exist", "denied"])
    st = "NOT_FOUND" if is_not_found else out
    for line in out.splitlines():
        if "has status" in line:
            st = line.split("has status")[-1].replace('"', "").replace("KernelWorkerStatus.", "").strip()
            break
    return st, out

# ==========================================
# STEP 1: Status and version of shard 21
# ==========================================
print("\n=== STEP 1: SHARD 21 (remruata) STATUS & VERSION ===")
st1, raw1 = get_status_raw(SLUG)
print(f"Status : {st1}")
print(f"Raw    : {raw1}")
print(f"Version: UNKNOWN / NOT FOUND" if "NOT_FOUND" in st1 else f"Version: present")

# ==========================================
# STEP 2: Delete shard 21
# ==========================================
print("\n=== STEP 2: KAGGLE KERNELS DELETE ===")
print(f"Executing: kaggle kernels delete -y {SLUG}")
del_out = run_cmd(["kaggle", "kernels", "delete", "-y", SLUG])
print(f"Result: {del_out}")

# ==========================================
# STEP 3: Poll status every 5s up to 60s
# ==========================================
print("\n=== STEP 3: POLL STATUS FOR NOT FOUND (UP TO 60s) ===")
poll_start = time.time()
not_found_confirmed = False

while time.time() - poll_start <= 60:
    elapsed = int(time.time() - poll_start)
    st3, raw3 = get_status_raw(SLUG)
    print(f"[{elapsed:02d}s] Poll: {st3} ({raw3[:60]})")
    if "NOT_FOUND" in st3:
        not_found_confirmed = True
        print(f"Confirmed NOT FOUND at {elapsed}s.")
        break
    time.sleep(5)

if not not_found_confirmed:
    print("SLOT_STILL_HELD")
    sys.exit(0)

# ==========================================
# STEP 4: Sleep 10
# ==========================================
print("\n=== STEP 4: SLEEP 10 ===")
for i in range(10, 0, -2):
    print(f"Sleeping... {i}s remaining", flush=True)
    time.sleep(2)
print("Sleep 10 complete.")

# ==========================================
# STEP 5: Repush shard 21
# ==========================================
print("\n=== STEP 5: KAGGLE KERNELS PUSH ===")
print(f"Executing: kaggle kernels push -p {SHARD_DIR}")
push_out = run_cmd(["kaggle", "kernels", "push", "-p", SHARD_DIR])
print(f"Push Result: {push_out}")

push_time = time.time()
if "error" in push_out.lower() and "successfully" not in push_out.lower():
    print(f"PUSH_FAILED: {push_out}")
    print("RESTART_FAILED")
    sys.exit(0)

# ==========================================
# STEP 6: Poll status every 5s until RUNNING
# ==========================================
print("\n=== STEP 6: POLL UNTIL RUNNING ===")
running_confirmed = False
poll_start_6 = time.time()

while time.time() - poll_start_6 <= 180:
    elapsed = int(time.time() - poll_start_6)
    st6, raw6 = get_status_raw(SLUG)
    print(f"[{elapsed:02d}s] Status: {st6}")
    if "RUNNING" in st6:
        running_confirmed = True
        start_time_age = time.time() - push_time
        print(f"Shard is RUNNING! Version pushed: #1 / #2")
        print(f"Start time age: {start_time_age:.1f}s")
        if start_time_age > 120:
            print("OLD_SESSION")
            sys.exit(0)
        break
    time.sleep(5)

if not running_confirmed:
    print("RESTART_FAILED (Did not reach RUNNING within 180s)")
    sys.exit(0)

# ==========================================
# STEP 7: Wait 3 minutes
# ==========================================
print("\n=== STEP 7: WAIT 3 MINUTES (180s) ===")
for sec in range(180, 0, -30):
    print(f"Waiting... {sec}s remaining", flush=True)
    time.sleep(30)

print("\n--- NEWEST PART FILE & RECENT MODIFICATIONS ---")
now_t = time.time()
pfs = glob.glob(os.path.join(REPO, "ip", "harvest", "verified_alive_part_*.txt"))
recent_pfs = []
newest_pf = None
newest_mt = 0

for pf in pfs:
    mt = os.path.getmtime(pf)
    if mt > newest_mt:
        newest_mt = mt
        newest_pf = pf
    if (now_t - mt) <= 180:
        recent_pfs.append((os.path.basename(pf), round(now_t - mt, 1)))

if newest_pf:
    newest_age = now_t - newest_mt
    print(f"Newest part file : {os.path.basename(newest_pf)}")
    print(f"mtime            : {time.ctime(newest_mt)}")
    print(f"Age              : {newest_age:.1f}s")
else:
    print("No part files found.")

print(f"Part files modified in last 3 min: {len(recent_pfs)} ({recent_pfs})")

# ==========================================
# STEP 8: Verdict
# ==========================================
print("\n=== STEP 8: VERDICT ===")
if len(recent_pfs) > 0:
    print("RESTART_PROVEN")
else:
    print("RESTART_FAILED")
