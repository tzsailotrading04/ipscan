import os
import glob

REPO_ROOT = r"D:\DEpinFarm" if os.path.exists(r"D:\DEpinFarm") else "."

target1 = 'sh_stats_file = os.path.join(work_dir, f"sh{SHARD_TAG}_stats.txt")'
repl1 = 'sh_stats_file = os.path.join(work_dir, f"sh{SHARD_TAG}_w{worker_id}_stats.txt")'

target2 = 'f"work/sh{SHARD_TAG}_stats.txt",'
repl2 = 'f"work/sh{SHARD_TAG}*_stats.txt",'

modified_count = 0
for i in range(20):
    fpath = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{i:02d}", "run.py")
    if not os.path.exists(fpath):
        continue
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()

    changed = False
    if target1 in content:
        content = content.replace(target1, repl1)
        changed = True

    if target2 in content:
        content = content.replace(target2, repl2)
        changed = True

    if changed:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        modified_count += 1
        print(f"Updated cl_shodan_{i:02d}/run.py")
    else:
        print(f"cl_shodan_{i:02d}/run.py targets not found or already updated.")

print(f"Total modified shards: {modified_count}/20")
