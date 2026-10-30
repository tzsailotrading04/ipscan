import os
import glob
import json

repo = r"D:\DEpinFarm"
metas = glob.glob(os.path.join(repo, "kaggle", "*", "kernel-metadata.json"))

by_account = {}
for m in sorted(metas):
    try:
        data = json.load(open(m))
        kid = data.get("id", "")
        if "/" in kid:
            u, slug = kid.split("/", 1)
            by_account.setdefault(u, []).append((slug, m))
    except Exception:
        pass

for u, slugs in by_account.items():
    print(f"=== {u} ({len(slugs)} kernels) ===")
    for s, m in slugs:
        print(f"  {s} ({os.path.basename(os.path.dirname(m))})")
