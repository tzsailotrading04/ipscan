import os
import re

ROOT = r"D:\DEpinFarm"
shard_files = [os.path.join(ROOT, "kaggle", "cl_shodan", "run.py")] + [
    os.path.join(ROOT, "kaggle", f"cl_shodan_{i:02d}", "run.py") for i in range(20)
]

for p in shard_files:
    with open(p, "r", encoding="utf-8") as f:
        c = f.read()

    # 1. Update ENGINE_VER
    c = re.sub(r'ENGINE_VER = "v\d+\.\d+"', 'ENGINE_VER = "v98.157"', c)

    # 2. STEP 1 - Add bulk_all.txt to load_candidates
    # is_list check
    old_is_list = 'is_list = "lists_all" in os.path.basename(path)'
    new_is_list = 'is_list = ("lists_all" in os.path.basename(path)) or ("bulk_all" in os.path.basename(path))'
    if old_is_list in c:
        c = c.replace(old_is_list, new_is_list)

    # v_files list
    old_v_files = 'v_files += [os.path.join(REPO_ROOT, "ip", "harvest", "lists_all.txt")]'
    new_v_files = 'v_files += [os.path.join(REPO_ROOT, "ip", "harvest", "lists_all.txt")]\n    v_files += [os.path.join(REPO_ROOT, "ip", "harvest", "bulk_all.txt")]'
    if 'bulk_all.txt")]' not in c and old_v_files in c:
        c = c.replace(old_v_files, new_v_files)

    # 3. STEP 2 - Fix weighting to be count-aware: FAST x3, MED x2, OK x1
    old_selection_pattern = re.compile(r'            if usable:\s+fast_u = \[.*?addr, proto = random\.choice\(target\)\s+else:', re.DOTALL)
    new_selection = """            if usable:
                weights = [3 if PROXY_CLASS.get(p[0]) == "FAST" else (2 if PROXY_CLASS.get(p[0]) == "MED" else 1) for p in usable]
                addr, proto = random.choices(usable, weights=weights, k=1)[0]
            else:"""
    if old_selection_pattern.search(c):
        c = old_selection_pattern.sub(new_selection, c)
    else:
        # Fallback direct replacement
        old_sel_exact = """            if usable:
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
        if old_sel_exact in c:
            c = c.replace(old_sel_exact, new_selection)

    # 4. STEP 3 - Semaphore 600 -> 1200, validation timeout 15s -> 12s
    c = c.replace('sem = asyncio.Semaphore(600)', 'sem = asyncio.Semaphore(1200)')
    # in build_pool try_http and try_socks5:
    c = c.replace('proxy=f"http://{addr}", timeout=15)', 'proxy=f"http://{addr}", timeout=12)')
    c = c.replace('BASE + rand_ip(), timeout=15)', 'BASE + rand_ip(), timeout=12)')

    # Ensure startup slice cap at 20,000 is present
    if 'mine = mine[:20000]' not in c:
        c = c.replace('mine = allc[SHARD_IDX::NUM_SHARDS]          # DISJOINT slice',
                      'mine = allc[SHARD_IDX::NUM_SHARDS]          # DISJOINT slice\n        mine = mine[:20000]')

    with open(p, "w", encoding="utf-8") as f:
        f.write(c)

print(f"Applied v98.157 to {len(shard_files)} shard files.")

# Update work/VERSION
with open(os.path.join(ROOT, "work", "VERSION"), "w", encoding="utf-8") as f:
    f.write("v98.157\n")
print("Updated work/VERSION to v98.157.")
