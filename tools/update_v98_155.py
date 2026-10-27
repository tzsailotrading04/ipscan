import os
import re
import glob

ROOT = r"D:\DEpinFarm"

# 1. Update 21 Shard Files
shard_files = [os.path.join(ROOT, "kaggle", "cl_shodan", "run.py")] + [
    os.path.join(ROOT, "kaggle", f"cl_shodan_{i:02d}", "run.py") for i in range(20)
]

old_selection = """            if usable:
                addr, proto = random.choice(usable)
            else:"""

new_selection = """            if usable:
                fast_u = [p for p in usable if PROXY_CLASS.get(p[0]) == "FAST"]
                med_u = [p for p in usable if PROXY_CLASS.get(p[0]) == "MED"]
                ok_u = [p for p in usable if PROXY_CLASS.get(p[0]) == "OK"]
                r = random.random()
                if r < 0.60:
                    target = fast_u or usable
                elif r < 0.90:
                    target = med_u or usable
                else:
                    target = ok_u or usable
                addr, proto = random.choice(target)
            else:"""

for p in shard_files:
    with open(p, "r", encoding="utf-8") as f:
        c = f.read()

    # Update ENGINE_VER
    c = re.sub(r'ENGINE_VER = "v\d+\.\d+"', 'ENGINE_VER = "v98.155"', c)

    # Update selection logic in fetch_ip
    if old_selection in c:
        c = c.replace(old_selection, new_selection)
    else:
        # Check if already updated or pattern match
        pattern = re.compile(r'            if usable:\s+addr, proto = random\.choice\(usable\)\s+else:')
        assert pattern.search(c), f"Selection pattern not found in {p}"
        c = pattern.sub(new_selection, c)

    with open(p, "w", encoding="utf-8") as f:
        f.write(c)

print(f"Applied STEP 1 weighted selection & v98.155 to {len(shard_files)} shard files.")

# 2. Update 11 Verifier Files
verifier_files = [os.path.join(ROOT, "kaggle", "cl_verify", "run.py")] + glob.glob(os.path.join(ROOT, "kaggle", "cl_verify_*", "run.py"))

for vf in verifier_files:
    with open(vf, "r", encoding="utf-8") as f:
        c = f.read()

    # Update CANDIDATES list
    if '"ip/harvest/bulk_all.txt"' not in c:
        c = c.replace('CANDIDATES = ["ip/harvest/lists_all.txt"', 'CANDIDATES = ["ip/harvest/bulk_all.txt", "ip/harvest/lists_all.txt"')

    # Update list_files in gather_candidates()
    old_list_files = 'list_files = [os.path.join(REPO, "ip", "harvest", "lists_all.txt")]'
    new_list_files = 'list_files = [os.path.join(REPO, "ip", "harvest", "bulk_all.txt"), os.path.join(REPO, "ip", "harvest", "lists_all.txt")]'
    if old_list_files in c:
        c = c.replace(old_list_files, new_list_files)

    with open(vf, "w", encoding="utf-8") as f:
        f.write(c)

print(f"Applied STEP 3 bulk_all.txt candidate loading to {len(verifier_files)} verifier files.")

# Update work/VERSION
with open(os.path.join(ROOT, "work", "VERSION"), "w", encoding="utf-8") as f:
    f.write("v98.155\n")
print("Updated work/VERSION to v98.155.")
