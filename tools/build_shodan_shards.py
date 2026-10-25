import os

ASN_FILE = "D:/DEpinFarm/data/ip2asn-v4-u32.tsv"
SHARDS_FILE = "D:/DEpinFarm/work/shodan_shards.txt"
SHARDS_DIR = "D:/DEpinFarm/work/shards"

CLOUD_KEYWORDS = [
    'digitalocean', 'hetzner', 'vultr', 'choopa', 'linode',
    'ovh', 'contabo', 'leaseweb', 'kamatera', 'm247',
    'hostinger', 'amazon', 'aws', 'google-cloud', 'azure'
]

def u32_to_ip(u):
    return f"{(u >> 24) & 255}.{(u >> 16) & 255}.{(u >> 8) & 255}.{u & 255}"

def main():
    print(f"Reading {ASN_FILE}...")
    subnets = []
    with open(ASN_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 5:
                start, end, asn, cc, org = int(p[0]), int(p[1]), p[2], p[3], p[4]
                org_lower = org.lower()
                if any(k in org_lower for k in CLOUD_KEYWORDS):
                    cur = start
                    while cur <= end:
                        subnets.append(cur)
                        cur += 256

    total = len(subnets)
    print(f"Total cloud /24 subnets: {total:,}")

    NUM_SHARDS = 20
    shard_size = total // NUM_SHARDS
    os.makedirs(os.path.dirname(SHARDS_FILE), exist_ok=True)
    os.makedirs(SHARDS_DIR, exist_ok=True)

    summary_lines = []
    with open(SHARDS_FILE, "w", encoding="utf-8") as f_all:
        for i in range(NUM_SHARDS):
            s_start = i * shard_size
            s_end = total if i == NUM_SHARDS - 1 else (i + 1) * shard_size
            shard_subnets = subnets[s_start:s_end]
            shard_ips = [u32_to_ip(u + 1) for u in shard_subnets]
            
            # Write individual shard file
            shard_p = os.path.join(SHARDS_DIR, f"shard_{i:02d}.txt")
            with open(shard_p, "w", encoding="ascii") as sf:
                for ip in shard_ips:
                    sf.write(f"{ip}\n")
                    f_all.write(f"{i:02d}\t{ip}\n")
                    
            summary = f"Shard {i:02d}: {len(shard_ips):,} IPs ({shard_ips[0]} -> {shard_ips[-1]})"
            summary_lines.append(summary)
            print(summary)

    meta_file = "D:/DEpinFarm/work/shodan_shards_meta.txt"
    with open(meta_file, "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines) + "\n")

    print(f"\nSaved all {total:,} rows to {SHARDS_FILE} (size: {os.path.getsize(SHARDS_FILE):,} bytes)")
    print(f"Saved 20 individual shard files to {SHARDS_DIR}/")

if __name__ == "__main__":
    main()
