import glob, os, time, subprocess
from concurrent.futures import ThreadPoolExecutor

REPO = r"D:\DEpinFarm"

# 1. Sync remote commits quietly
try:
    subprocess.run(["git", "-C", REPO, "fetch", "origin", "main", "--quiet"], capture_output=True, timeout=15)
    subprocess.run(["git", "-C", REPO, "merge", "--no-edit", "origin/main", "--quiet"], capture_output=True, timeout=15)
except Exception:
    pass

# 2. Check 34 shards status
FLEET = [
    (0, "remruata", "kaggle/acct5/access_token"),
    (1, "remruata", "kaggle/acct5/access_token"),
    (2, "lalthazualasailo", "kaggle/acct1/access_token"),
    (3, "lalthazualasailo", "kaggle/acct1/access_token"),
    (4, "lalthazualasailo", "kaggle/acct1/access_token"),
    (5, "lalthazualasailo", "kaggle/acct1/access_token"),
    (6, "zomuanpuia", "kaggle/acct2/access_token"),
    (7, "zomuanpuia", "kaggle/acct2/access_token"),
    (8, "zomuanpuia", "kaggle/acct2/access_token"),
    (9, "zomuanpuia", "kaggle/acct2/access_token"),
    (10, "laldinthari", "kaggle/acct3/access_token"),
    (11, "laldinthari", "kaggle/acct3/access_token"),
    (12, "laldinthari", "kaggle/acct3/access_token"),
    (13, "laldinthari", "kaggle/acct3/access_token"),
    (14, "spectatorlone", "kaggle/acct6/access_token"),
    (15, "lalsangkima", "kaggle/acct4/access_token"),
    (16, "lalsangkima", "kaggle/acct4/access_token"),
    (17, "lalsangkima", "kaggle/acct4/access_token"),
    (18, "spectatorlone", "kaggle/acct6/access_token"),
    (19, "spectatorlone", "kaggle/acct6/access_token"),
    (20, "remruata", "kaggle/acct5/access_token"),
    (21, "remruata", "kaggle/acct5/access_token"),
    (22, "lalthazualasailo", "kaggle/acct1/access_token"),
    (23, "zomuanpuia", "kaggle/acct2/access_token"),
    (24, "laldinthari", "kaggle/acct3/access_token"),
    (25, "lalsangkima", "kaggle/acct4/access_token"),
    (26, "lalsangkima", "kaggle/acct4/access_token"),
    (27, "spectatorlone", "kaggle/acct6/access_token"),
    (28, "spectatorlone", "kaggle/acct6/access_token"),
    (29, "stephen34", "kaggle/stephen34/access_token"),
    (30, "stephen34", "kaggle/stephen34/access_token"),
    (31, "stephen34", "kaggle/stephen34/access_token"),
    (32, "stephen34", "kaggle/stephen34/access_token"),
    (33, "stephen34", "kaggle/stephen34/access_token"),
]

tokens = {tp: open(os.path.join(REPO, tp)).read().strip() for _, _, tp in FLEET}

def check_one(item):
    s, u, tp = item
    s_tag = f"{s:02d}"
    kid = f"{u}/ipscan-cl-shodan-{s_tag}"
    env = os.environ.copy()
    env["KAGGLE_API_TOKEN"] = tokens[tp]
    r = subprocess.run(["kaggle", "kernels", "status", kid], env=env, capture_output=True, text=True, timeout=20)
    out = (r.stdout + " " + r.stderr).strip()
    status = "UNKNOWN"
    for line in out.splitlines():
        if "status" in line.lower():
            cleaned = line.strip().replace("Warning: Looks like you're using an outdated `kaggle` version (installed: 2.2.4), please consider upgrading to the latest version (2.2.5)", "").strip()
            if "has status" in cleaned:
                status = cleaned.split("has status")[-1].replace('"', "").replace("KernelWorkerStatus.", "").strip()
            else:
                status = cleaned
            break
    return s, u, kid, status

with ThreadPoolExecutor(max_workers=8) as pool:
    results = list(pool.map(check_one, FLEET))

print("=== 34 SHARDS STATUS ===")
for s, u, kid, st in sorted(results):
    print(f"shard_{s:02d} ({u}): {st}")

# 3. Newest part file
part_files = glob.glob(os.path.join(REPO, "ip", "harvest", "verified_alive_part_*.txt"))
if part_files:
    newest = max(part_files, key=os.path.getmtime)
    mtime = os.path.getmtime(newest)
    now = time.time()
    age_s = now - mtime
    age_str = f"{age_s:.1f}s" if age_s < 60 else f"{age_s/60.0:.1f}m"
    mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
    line_cnt = sum(1 for line in open(newest, errors="ignore") if line.strip())
    print("\n=== NEWEST PART-FILE ===")
    print(f"File     : {os.path.basename(newest)}")
    print(f"mtime    : {mtime_str}")
    print(f"Age      : {age_str} ago ({age_s:.1f} seconds)")
    print(f"Lines    : {line_cnt}")
else:
    print("\nNo part files found!")
