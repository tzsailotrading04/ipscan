import os
import ipaddress
import time

ROOT = r"D:\DEpinFarm"
RANGES_FILE = os.path.join(ROOT, "data", "ranges_all.txt")
POOL_FILE = os.path.join(ROOT, "master_pool.txt")
HOSTING_FILE = os.path.join(ROOT, "data", "ranges_hosting.txt")
OUT_FILE = RANGES_FILE

def main():
    t0 = time.time()
    print("Loading master_pool.txt...", flush=True)
    pool_ips = []
    with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            p = line.strip().split()
            if p and ":" in p[0]:
                try:
                    parts = [int(x) for x in p[0].split(":")[0].split(".")]
                    pool_ips.append((parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3])
                except Exception:
                    pass
    pool_ips = set(pool_ips)
    print(f"Loaded {len(pool_ips)} unique IPs from pool.", flush=True)

    print("Loading current ranges_all.txt and indexing /16 buckets...", flush=True)
    cidrs = []
    buckets = {}
    with open(RANGES_FILE, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            c = line.strip()
            if not c:
                continue
            cidrs.append(c)
            try:
                net = ipaddress.IPv4Network(c)
                s_u32 = int(net.network_address)
                e_u32 = int(net.broadcast_address)
                for b in range(s_u32 >> 16, (e_u32 >> 16) + 1):
                    buckets.setdefault(b, []).append((s_u32, e_u32, idx))
            except Exception:
                pass

    print(f"Loaded {len(cidrs)} CIDRs.", flush=True)

    print("Matching pool hits to CIDRs...", flush=True)
    prod_counts = {}
    for ip in pool_ips:
        b = ip >> 16
        for s_u32, e_u32, idx in buckets.get(b, []):
            if s_u32 <= ip <= e_u32:
                prod_counts[idx] = prod_counts.get(idx, 0) + 1
                break

    sorted_prod_indices = sorted(prod_counts.keys(), key=lambda i: -prod_counts[i])
    prod_cidrs = [cidrs[i] for i in sorted_prod_indices]
    prod_set = set(prod_cidrs)
    print(f"Found {len(prod_cidrs)} productive CIDRs.", flush=True)

    hosting_cidrs = []
    if os.path.exists(HOSTING_FILE):
        with open(HOSTING_FILE, "r", encoding="utf-8") as f:
            for line in f:
                c = line.strip()
                if c and c not in prod_set and c not in hosting_cidrs:
                    hosting_cidrs.append(c)
    hosting_set = set(hosting_cidrs)
    print(f"Found {len(hosting_cidrs)} additional hosting CIDRs.", flush=True)

    other_cidrs = [c for c in cidrs if c not in prod_set and c not in hosting_set]
    print(f"Found {len(other_cidrs)} other CIDRs.", flush=True)

    num_slices = 20
    slices = [[] for _ in range(num_slices)]

    # 1. Round-robin productive CIDRs across 20 slices
    for i, c in enumerate(prod_cidrs):
        slices[i % num_slices].append(c)

    # 2. Round-robin hosting CIDRs across 20 slices
    for i, c in enumerate(hosting_cidrs):
        slices[i % num_slices].append(c)

    # 3. Round-robin other CIDRs across 20 slices
    for i, c in enumerate(other_cidrs):
        slices[i % num_slices].append(c)

    # Backup existing ranges_all.txt
    bak_file = os.path.join(ROOT, "data", "ranges_all.txt.bak_v69")
    if os.path.exists(RANGES_FILE) and not os.path.exists(bak_file):
        import shutil
        shutil.copy2(RANGES_FILE, bak_file)

    # Flatten slices into new ranges_all.txt
    print(f"Writing rebalanced ranges to {OUT_FILE}...", flush=True)
    with open(OUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        for s_idx, s_cidrs in enumerate(slices):
            for c in s_cidrs:
                f.write(c + "\n")

    print(f"Rebalanced ranges_all.txt completed in {time.time()-t0:.1f}s.")

if __name__ == "__main__":
    main()
