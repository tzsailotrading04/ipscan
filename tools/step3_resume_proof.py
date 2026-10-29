import os

repo_root = r"D:\DEpinFarm"
offsets = {}
broken = []

print("=== STEP 3 - RESUME PROOF ===")
print(f"{'Shard':<8} | {'Progress File':<32} | {'Offset'}")
print("-" * 55)

for i in range(34):
    s_tag = f"{i:02d}"
    fname = f"shodan_progress_v98_{s_tag}.txt"
    fpath = os.path.join(repo_root, "ip", "harvest", fname)
    if not os.path.exists(fpath):
        print(f"Shard {s_tag} | {fname:<32} | MISSING")
        broken.append(s_tag)
        print(f"RESUME_BROKEN shard {s_tag}")
    else:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            if not lines:
                print(f"Shard {s_tag} | {fname:<32} | EMPTY")
                broken.append(s_tag)
                print(f"RESUME_BROKEN shard {s_tag}")
            else:
                val = int(lines[0])
                offsets[s_tag] = val
                print(f"Shard {s_tag} | {fname:<32} | {val}")
                if val == 0:
                    broken.append(s_tag)
                    print(f"RESUME_BROKEN shard {s_tag}")
        except Exception as e:
            print(f"Shard {s_tag} | {fname:<32} | ERR: {e}")
            broken.append(s_tag)
            print(f"RESUME_BROKEN shard {s_tag}")

print("-" * 55)
if offsets:
    min_s = min(offsets, key=offsets.get)
    max_s = max(offsets, key=offsets.get)
    print(f"Lowest Offset : {offsets[min_s]} (Shard {min_s})")
    print(f"Highest Offset: {offsets[max_s]} (Shard {max_s})")
else:
    print("No valid offsets found.")

# Reference from shodan_stats_v98_00.txt
ref_file = os.path.join(repo_root, "ip", "harvest", "shodan_stats_v98_00.txt")
ref_offset = "NOT FOUND"
if os.path.exists(ref_file):
    with open(ref_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("offset="):
                ref_offset = line.strip().split("=")[1]
                break

print(f"\nLive Reference Offset from shodan_stats_v98_00.txt: {ref_offset}")

if not broken:
    print("\nRESUME CHECK: ALL SHARDS OK")
else:
    print(f"\nRESUME CHECK: {len(broken)} SHARDS BROKEN/MISSING ({', '.join(broken)})")
