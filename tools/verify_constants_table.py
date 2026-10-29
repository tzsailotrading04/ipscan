import os
import re

repo_root = r"D:\DEpinFarm"

def check_file(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    m_num = re.search(r"^NUM_SHARDS\s*=\s*(\d+)", content, re.MULTILINE)
    m_idx = re.search(r"^SHARD_IDX\s*=\s*(\d+)", content, re.MULTILINE)
    num_shards = int(m_num.group(1)) if m_num else None
    shard_idx = int(m_idx.group(1)) if m_idx else None
    return shard_idx, num_shards

rows = []
all_ok = True

# Master
master_p = os.path.join(repo_root, "kaggle", "cl_shodan", "run.py")
s_idx, n_sh = check_file(master_p)
rows.append(("kaggle/cl_shodan/run.py", str(s_idx), str(n_sh)))
if n_sh != 34:
    all_ok = False

# 34 shards
for i in range(34):
    fname = f"kaggle/cl_shodan_{i:02d}/run.py"
    p = os.path.join(repo_root, fname)
    s_idx, n_sh = check_file(p)
    rows.append((fname, str(s_idx), str(n_sh)))
    if s_idx != i or n_sh != 34:
        all_ok = False

print(f"{'file':<30} | {'SHARD_IDX':<9} | {'NUM_SHARDS':<10}")
print("-" * 55)
for f, idx, num in rows:
    print(f"{f:<30} | {idx:<9} | {num:<10}")

print("-" * 55)
print(f"Total files checked: {len(rows)}")
if all_ok:
    print("ALL 35 FILES VERIFIED CORRECT.")
else:
    print("FAILED")
