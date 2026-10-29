"""
tools/build_budget_vps_subnets.py
Generates data/hosting_subnets.txt strictly for the 10 budget-VPS providers:
- OVH, Hetzner, Contabo, Vultr, Linode, DigitalOcean, Leaseweb, ColoCrossing, M247, Hostinger
- Explicitly removes Cogent, Equinix, Telmex, Colombia Telecom, transit, IX, and telco ASNs
- Converts IP ranges to canonical /24 subnets (a.b.c)
- Deterministically sorted and deduped
"""
import os
import time

ROOT = r"D:\DEpinFarm"
ASN_FILE = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")
OUT_FILE = os.path.join(ROOT, "data", "hosting_subnets.txt")

BUDGET_VPS_KW = (
    "ovh", "hetzner", "contabo", "vultr", "linode", "digitalocean",
    "leaseweb", "colocrossing", "m247", "hostinger"
)

EXCLUDED_KW = (
    "cogent", "equinix", "telmex", "colombia", "telecom", "transit",
    "ix", "internet exchange", "telco", "amazon", "aws", "google", "gcp",
    "microsoft", "azure", "oracle", "alibaba", "tencent", "cloudflare"
)

def u24_to_str(u24):
    return f"{(u24 >> 16) & 0xFF}.{(u24 >> 8) & 0xFF}.{u24 & 0xFF}"

def main():
    t0 = time.time()
    print(f"Loading {ASN_FILE}...")
    subnets = set()
    matched_ranges = 0
    total_raw_ips = 0

    with open(ASN_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 5:
                continue
            try:
                s, e = int(p[0]), int(p[1])
                org = p[4].lower()
            except ValueError:
                continue

            # Check exclusions
            if any(ex in org for ex in EXCLUDED_KW):
                continue

            # Must match budget VPS list
            if any(kw in org for kw in BUDGET_VPS_KW):
                matched_ranges += 1
                total_raw_ips += (e - s + 1)
                
                # Align to /24 subnets
                cur = s >> 8
                end = e >> 8
                while cur <= end:
                    subnets.add(cur)
                    cur += 1

    print(f"Matched {matched_ranges:,} ranges ({total_raw_ips:,} raw IPs) in {time.time()-t0:.2f}s")
    print(f"Unique /24 subnets: {len(subnets):,} ({len(subnets)*256:,} IPs)")

    # Sort deterministically
    sorted_subnets = sorted(subnets)
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="ascii") as out:
        for u24 in sorted_subnets:
            out.write(u24_to_str(u24) + "\n")

    print(f"Wrote {len(sorted_subnets):,} subnets to {OUT_FILE}")

if __name__ == "__main__":
    main()
