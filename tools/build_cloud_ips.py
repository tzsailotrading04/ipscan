import os

ASN_FILE = "D:/DEpinFarm/data/ip2asn-v4-u32.tsv"
OUT_FILE = "D:/DEpinFarm/ip/harvest/cloud_target_ips.txt"

# High-proxy-density VPS and cloud hosting keywords
CLOUD_KEYWORDS = [
    'digitalocean', 'hetzner', 'vultr', 'choopa', 'linode',
    'ovh', 'contabo', 'leaseweb', 'kamatera', 'm247',
    'hostinger', 'amazon', 'aws', 'google-cloud', 'azure'
]

def u32_to_ip(u):
    return f"{(u >> 24) & 255}.{(u >> 16) & 255}.{(u >> 8) & 255}.{u & 255}"

def build_cloud_ips(max_targets=60000):
    print(f"Reading {ASN_FILE}...")
    subnets = []
    
    with open(ASN_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 5:
                start, end, asn, cc, org = int(p[0]), int(p[1]), p[2], p[3], p[4]
                org_lower = org.lower()
                if any(k in org_lower for k in CLOUD_KEYWORDS):
                    # Step by 256 (/24 subnets) through this range
                    cur = start
                    while cur <= end:
                        subnets.append(cur)
                        cur += 256

    print(f"Total cloud /24 subnets identified: {len(subnets):,}")
    
    # Pick candidate IPs (e.g. offset +1 or +10 in each /24)
    # Stride if more than max_targets
    stride = max(1, len(subnets) // max_targets)
    sampled = subnets[::stride][:max_targets]
    
    target_ips = [u32_to_ip(u + 1) for u in sampled]
    print(f"Sampled {len(target_ips):,} target cloud IPs (stride={stride})")
    
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="ascii") as f:
        for ip in target_ips:
            f.write(ip + "\n")
            
    print(f"Saved to {OUT_FILE}")
    return len(target_ips)

if __name__ == "__main__":
    build_cloud_ips()
