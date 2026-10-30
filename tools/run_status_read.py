import os
import glob
import time
import json
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

REPO = r"D:\DEpinFarm"
now = time.time()

# 1. wc -l on ip/harvest/real_pool.txt
real_pool_p = os.path.join(REPO, "ip", "harvest", "real_pool.txt")
real_pool_lines = sum(1 for _ in open(real_pool_p, errors="ignore")) if os.path.exists(real_pool_p) else 0

# 2. wc -l on cache/pool_dead.txt
dead_pool_p = os.path.join(REPO, "cache", "pool_dead.txt")
dead_pool_lines = sum(1 for _ in open(dead_pool_p, errors="ignore")) if os.path.exists(dead_pool_p) else 0

# 3. wc -l on cache/alive_buffer.txt
alive_buf_p = os.path.join(REPO, "cache", "alive_buffer.txt")
alive_buf_lines = sum(1 for _ in open(alive_buf_p, errors="ignore")) if os.path.exists(alive_buf_p) else 0

# 4. Queue: count of q_*.txt files and total lines in them
queue_dir = os.path.join(REPO, "ip", "harvest", "queue")
q_files = [f for f in glob.glob(os.path.join(queue_dir, "q_*.txt")) if not f.endswith(".ack") and ".ack_" not in f]
total_q_lines = 0
q_file_details = []
for qf in sorted(q_files):
    cnt = sum(1 for line in open(qf, errors="ignore") if line.strip())
    total_q_lines += cnt
    q_file_details.append(f"{os.path.basename(qf)}: {cnt} lines")

# 5 & 6. Part files
part_files = glob.glob(os.path.join(REPO, "ip", "harvest", "verified_alive_part_*.txt"))
total_part_lines = 0
modified_last_10m = 0
newest_part_file = None
newest_part_mtime = 0

for pf in part_files:
    mtime = os.path.getmtime(pf)
    if mtime > newest_part_mtime:
        newest_part_mtime = mtime
        newest_part_file = pf
    if (now - mtime) <= 600:
        modified_last_10m += 1
    total_part_lines += sum(1 for line in open(pf, errors="ignore") if line.strip())

newest_part_age = (now - newest_part_mtime) if newest_part_file else 999999

# 7. RUNNING shard count per account, and any shard not RUNNING
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

def check_shard_status(item):
    s, u, tp = item
    s_tag = f"{s:02d}"
    kid = f"{u}/ipscan-cl-shodan-{s_tag}"
    env = os.environ.copy()
    env["KAGGLE_API_TOKEN"] = tokens[tp]
    env["KAGGLE_USERNAME"] = u
    env["KAGGLE_KEY"] = tokens[tp]
    r = subprocess.run(["kaggle", "kernels", "status", kid], env=env, capture_output=True, text=True, timeout=20)
    out = (r.stdout + " " + r.stderr).strip()
    status = "UNKNOWN"
    clean_lines = [l for l in out.splitlines() if "Warning: Looks like" not in l]
    clean_out = " ".join(clean_lines)
    if any(k in clean_out.lower() for k in ["404", "not found", "does not exist", "denied"]):
        status = "DELETED / NOT FOUND"
    else:
        for line in clean_lines:
            if "has status" in line:
                status = line.split("has status")[-1].replace('"', "").replace("KernelWorkerStatus.", "").strip()
                break
            elif "status" in line.lower():
                status = line.strip()
                break
    return s, u, status

with ThreadPoolExecutor(max_workers=8) as pool:
    shard_results = list(pool.map(check_shard_status, FLEET))

# 8. Stage files
stage_files_content = {}
for s_num in ["00", "17", "33"]:
    sp = os.path.join(REPO, "ip", "harvest", f"stage_{s_num}.txt")
    if os.path.exists(sp):
        with open(sp, "r", encoding="utf-8", errors="ignore") as f:
            stage_files_content[s_num] = f.read().strip()
    else:
        stage_files_content[s_num] = "FILE_NOT_FOUND (not generated or shard deleted)"

# 9 & 10. Rig status (alive/dead/free mem/bytes moved)
rig_alive = 0
rig_dead = 0
rig_free_mem = "UNKNOWN"
rig_bytes_10m = 0
try:
    res = subprocess.run(["wsl", "-d", "depinfarm", "-u", "root", "python3", "/mnt/d/DEpinFarm/tools/r2_node_manager.py", "--status"], capture_output=True, text=True, timeout=25)
    for line in res.stdout.splitlines():
        if "ALIVE:" in line:
            rig_alive = int(line.split("ALIVE:")[-1].strip())
        elif "DEAD:" in line:
            rig_dead = int(line.split("DEAD:")[-1].strip())
        elif "FREE MEMORY:" in line:
            rig_free_mem = line.split("FREE MEMORY:")[-1].strip()
        elif "BYTES MOVED:" in line:
            rig_bytes_10m = line.split("BYTES MOVED:")[-1].strip()
except Exception as e:
    rig_free_mem = f"ERR: {e}"

# 11. New proxies since 19:00
# Check real_pool.txt git commits or part files timestamped after 19:00
proxies_since_1900 = 0
t_1900 = datetime.now().replace(hour=19, minute=0, second=0, microsecond=0)
t_1900_epoch = t_1900.timestamp()
# If current time is past midnight (01:17), 19:00 was yesterday evening
if now < t_1900_epoch:
    # 19:00 was yesterday
    t_1900_epoch -= 86400

for pf in part_files:
    if os.path.getmtime(pf) >= t_1900_epoch:
        proxies_since_1900 += sum(1 for line in open(pf, errors="ignore") if line.strip())

# Print outputs as structured JSON
output = {
    "1_real_pool_lines": real_pool_lines,
    "2_pool_dead_lines": dead_pool_lines,
    "3_alive_buffer_lines": alive_buf_lines,
    "4_queue_count": len(q_files),
    "4_queue_total_lines": total_q_lines,
    "4_queue_details": q_file_details,
    "5_part_total_lines": total_part_lines,
    "5_part_modified_10m": modified_last_10m,
    "6_newest_part_file": os.path.basename(newest_part_file) if newest_part_file else "None",
    "6_newest_part_age_sec": round(newest_part_age, 1),
    "7_shards": shard_results,
    "8_stages": stage_files_content,
    "9_rig_alive": rig_alive,
    "9_rig_dead": rig_dead,
    "9_rig_free_mem": rig_free_mem,
    "10_rig_bytes_10m": rig_bytes_10m,
    "proxies_since_1900": proxies_since_1900,
}

with open(r"D:\DEpinFarm\work\status_read_out.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2)

print("COMPLETE: status_read_out.json written")
