import os
import sys
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

REPO = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser("~/.kaggle/kaggle.json")

ACCT_TOKENS = {
    "lalthazualasailo": os.path.join(REPO, "kaggle", "acct1", "access_token"),
    "zomuanpuia": os.path.join(REPO, "kaggle", "acct2", "access_token"),
    "remruata": os.path.join(REPO, "kaggle", "acct5", "access_token"),
    "laldinthari": os.path.join(REPO, "kaggle", "acct3", "access_token"),
    "lalsangkima": os.path.join(REPO, "kaggle", "acct4", "access_token"),
    "spectatorlone": os.path.join(REPO, "kaggle", "acct6", "access_token"),
    "stephen34": os.path.join(REPO, "kaggle", "stephen34", "access_token"),
}

tokens = {u: open(p).read().strip() for u, p in ACCT_TOKENS.items()}

# Import slugs from check_all_meta_slugs
import check_all_meta_slugs
all_items = []
for u, slug_list in check_all_meta_slugs.by_account.items():
    for slug, m in slug_list:
        all_items.append((u, slug))

def check_item(item):
    u, slug = item
    tok = tokens.get(u)
    if not tok: return u, slug, "NO_TOKEN"
    env = os.environ.copy()
    env["KAGGLE_USERNAME"] = u
    env["KAGGLE_KEY"] = tok
    env["KAGGLE_API_TOKEN"] = tok
    full_slug = f"{u}/{slug}"
    r = subprocess.run(["kaggle", "kernels", "status", full_slug], env=env, capture_output=True, text=True, timeout=15)
    out = (r.stdout + " " + r.stderr).strip()
    status = "UNKNOWN"
    for l in out.splitlines():
        if "has status" in l:
            status = l.split("has status")[-1].replace('"', '').replace('KernelWorkerStatus.', '').strip()
            break
        elif "404" in l or "not found" in l.lower() or "denied" in l.lower():
            status = "NOT_FOUND"
            break
    return u, slug, status

with ThreadPoolExecutor(max_workers=10) as pool:
    results = list(pool.map(check_item, all_items))

print("=== ALL ACTIVE RUNNING / QUEUED KERNELS ===")
by_u = {}
for u, slug, st in results:
    by_u.setdefault(u, []).append((slug, st))

for u in sorted(by_u):
    print(f"\nAccount: {u}")
    active = [s for s, st in by_u[u] if "RUNNING" in st or "QUEUED" in st]
    print(f"  Active count: {len(active)}/5 max")
    for s, st in by_u[u]:
        if "RUNNING" in st or "QUEUED" in st:
            print(f"    RUNNING: {s}")
        elif "NOT_FOUND" not in st:
            print(f"    {st}: {s}")
