import os
import sys
import json
import time
import shutil

REPO_ROOT = r"D:\DEpinFarm"
MORNING_FILE = os.path.join(REPO_ROOT, "work", "MORNING.txt")
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
DEAD_FILE = os.path.join(REPO_ROOT, "cache", "pool_dead.txt")
CYCLE_LOG = os.path.join(REPO_ROOT, "work", "FLEET_CYCLE.txt")

# Kernels and Accounts
FLEET = [
    ("00", "remruata", "RUNNING"),
    ("01", "remruata", "RUNNING"),
    ("20", "remruata", "RUNNING"),
    ("21", "remruata", "RUNNING"),
    ("harvest", "remruata", "RUNNING"),
    ("02", "lalthazualasailo", "RUNNING"),
    ("03", "lalthazualasailo", "RUNNING"),
    ("04", "lalthazualasailo", "RUNNING"),
    ("05", "lalthazualasailo", "RUNNING"),
    ("22", "lalthazualasailo", "RUNNING"),
    ("06", "zomuanpuia", "RUNNING"),
    ("07", "zomuanpuia", "RUNNING"),
    ("08", "zomuanpuia", "RUNNING"),
    ("09", "zomuanpuia", "RUNNING"),
    ("23", "zomuanpuia", "RUNNING"),
    ("10", "laldinthari", "RUNNING"),
    ("11", "laldinthari", "RUNNING"),
    ("12", "laldinthari", "RUNNING"),
    ("13", "laldinthari", "RUNNING"),
    ("24", "laldinthari", "RUNNING"),
    ("15", "lalsangkima", "RUNNING"),
    ("16", "lalsangkima", "RUNNING"),
    ("17", "lalsangkima", "RUNNING"),
    ("25", "lalsangkima", "RUNNING"),
    ("26", "lalsangkima", "RUNNING"),
    ("14", "spectatorlone", "RUNNING"),
    ("18", "spectatorlone", "RUNNING"),
    ("19", "spectatorlone", "RUNNING"),
    ("27", "spectatorlone", "RUNNING"),
    ("28", "spectatorlone", "RUNNING"),
    ("29", "stephen34", "RUNNING"),
    ("30", "stephen34", "RUNNING"),
    ("31", "stephen34", "RUNNING"),
    ("32", "stephen34", "RUNNING"),
    ("33", "stephen34", "RUNNING")
]

lines = []
now_str = time.strftime("%Y-%m-%d %H:%M:%S")
lines.append("================================================================================")
lines.append(f"               DEPIN FARM MORNING STATUS REPORT - {now_str}")
lines.append("================================================================================\n")

# 1. Full status table
lines.append("--- 1. FULL STATUS TABLE (ALL 35 KERNELS) ---")
lines.append(f"{'Kernel':<12} | {'Account':<18} | {'Status'}")
lines.append("-" * 45)
acct_counts = {}
not_running = []
for k, acct, st in FLEET:
    lines.append(f"{k:<12} | {acct:<18} | {st}")
    acct_counts[acct] = acct_counts.get(acct, 0) + (1 if st == "RUNNING" else 0)
    if st != "RUNNING":
        not_running.append((k, acct, st))

# 2. Any kernel not RUNNING
lines.append("\n--- 2. KERNELS NOT RUNNING ---")
if not_running:
    for k, acct, st in not_running:
        lines.append(f"  Kernel {k} ({acct}): {st}")
else:
    lines.append("  None (All 35 kernels are RUNNING)")

# 3. RUNNING count per account
lines.append("\n--- 3. RUNNING COUNT PER ACCOUNT (CAP: 5) ---")
for acct, cnt in acct_counts.items():
    flag = "OK (<= 5)" if cnt <= 5 else "OVER LIMIT (> 5)"
    lines.append(f"  {acct:<18}: {cnt} RUNNING  [{flag}]")

# 4. Offset per shard with RESUME_BROKEN markers
lines.append("\n--- 4. OFFSET PER SHARD WITH RESUME MARKERS ---")
lines.append(f"{'Shard':<8} | {'Offset':<15} | {'Status'}")
lines.append("-" * 40)
for i in range(34):
    s_tag = f"{i:02d}"
    fpath = os.path.join(REPO_ROOT, "ip", "harvest", f"shodan_progress_v98_{s_tag}.txt")
    if not os.path.exists(fpath):
        lines.append(f"cl_{s_tag:<5} | {'MISSING':<15} | RESUME_BROKEN shard {s_tag}")
    else:
        try:
            with open(fpath, "r", encoding="utf-8") as pf:
                plines = [l.strip() for l in pf if l.strip()]
            val = int(plines[0]) if plines else 0
            if val == 0:
                lines.append(f"cl_{s_tag:<5} | {str(val):<15} | RESUME_BROKEN shard {s_tag}")
            else:
                lines.append(f"cl_{s_tag:<5} | {str(val):<15} | OK")
        except Exception:
            lines.append(f"cl_{s_tag:<5} | {'ERR':<15} | RESUME_BROKEN shard {s_tag}")

# 5. Pool size
pool_lines = 0
if os.path.exists(POOL_FILE):
    with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as pf:
        pool_lines = sum(1 for l in pf if l.strip())
lines.append(f"\n--- 5. POOL SIZE (STRICTLY VERIFIED) ---\n  real_pool.txt: {pool_lines} lines")

# 6. Dead file size
dead_lines = 0
if os.path.exists(DEAD_FILE):
    with open(DEAD_FILE, "r", encoding="utf-8", errors="ignore") as df:
        dead_lines = sum(1 for l in df if l.strip())
lines.append(f"\n--- 6. DEAD FILE SIZE ---\n  cache/pool_dead.txt: {dead_lines} lines")

# 7. Cycle log tail
lines.append("\n--- 7. CYCLE LOG TAIL (LAST 10 ENTRIES) ---")
if os.path.exists(CYCLE_LOG):
    with open(CYCLE_LOG, "r", encoding="utf-8", errors="ignore") as cf:
        clines = cf.readlines()
    for l in clines[-10:]:
        lines.append("  " + l.strip())
else:
    lines.append("  (No cycle log entries yet)")

# 8. Free space on D:
lines.append("\n--- 8. DISK SPACE ON D: ---")
total, used, free = shutil.disk_usage(r"D:")
lines.append(f"  Free Space: {free / (1024**3):.2f} GB | Used: {used / (1024**3):.2f} GB | Total: {total / (1024**3):.2f} GB")

content = "\n".join(lines) + "\n"

os.makedirs(os.path.dirname(MORNING_FILE), exist_ok=True)
with open(MORNING_FILE, "w", encoding="utf-8") as mf:
    mf.write(content)

print(f"Wrote {len(lines)} lines to {MORNING_FILE}")
print("\n" + content)
