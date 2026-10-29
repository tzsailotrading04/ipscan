import re
import os

repo_root = r"D:\DEpinFarm"

def update_file(filepath, shard_idx):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    new_content = re.sub(r"^NUM_SHARDS\s*=\s*\d+", "NUM_SHARDS = 34", content, flags=re.MULTILINE)
    new_content = re.sub(r"^SHARD_IDX\s*=\s*\d+", f"SHARD_IDX = {shard_idx}", new_content, flags=re.MULTILINE)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

# 1. kaggle/cl_shodan/run.py
master_file = os.path.join(repo_root, "kaggle", "cl_shodan", "run.py")
update_file(master_file, 0)

# 2. kaggle/cl_shodan_00 through 33
for i in range(34):
    shard_dir = f"cl_shodan_{i:02d}"
    shard_file = os.path.join(repo_root, "kaggle", shard_dir, "run.py")
    update_file(shard_file, i)

print("Updated master and all 34 shard files.")
