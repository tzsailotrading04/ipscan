import os
import glob
import subprocess

REPO_ROOT = r"D:\DEpinFarm"
QUEUE_DIR = os.path.join(REPO_ROOT, "ip", "harvest", "queue")
REAL_POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")

# 1. Queue depth
q_files = glob.glob(os.path.join(QUEUE_DIR, "q_*.txt"))
# Filter out .ack files if any
q_files = [f for f in q_files if not f.endswith(".ack") and not ".ack_" in f]

total_queue_lines = 0
for qf in q_files:
    try:
        with open(qf, "r", encoding="utf-8", errors="ignore") as f:
            total_queue_lines += sum(1 for line in f if line.strip())
    except Exception:
        pass

# 2. Pool size
pool_size = 0
if os.path.exists(REAL_POOL_FILE):
    with open(REAL_POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
        pool_size = sum(1 for line in f if line.strip())

# 3. Alive count (from WSL r2 rig status)
alive_count = "UNKNOWN"
try:
    res = subprocess.run(["wsl", "-d", "depinfarm", "-u", "root", "python3", "/mnt/d/DEpinFarm/tools/r2_node_manager.py", "--status"], capture_output=True, text=True, timeout=15)
    for line in res.stdout.splitlines():
        if "ALIVE:" in line:
            alive_count = line.split("ALIVE:")[-1].strip()
            break
except Exception as e:
    alive_count = f"ERR: {e}"

print(f"QUEUE_DEPTH : {total_queue_lines} lines across {len(q_files)} file(s) ({', '.join(os.path.basename(f) for f in q_files)})")
print(f"ALIVE_COUNT : {alive_count}")
print(f"POOL_SIZE   : {pool_size} lines")
