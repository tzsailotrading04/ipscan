"""
generate_hosting_subnets.py
Generates data/hosting_subnets.txt from data/ip2asn-v4-u32.tsv:
- Filters for all hosting/datacenter ASNs (OVH, Hetzner, DigitalOcean, Contabo, Leaseweb,
  M247, ColoCrossing, Vultr, Linode, Hostinger, AWS, Azure, GCP, and all matching orgs).
- Converts IP ranges to canonical /24 subnets (a.b.c).
- Deduplicates and sorts deterministically.
"""
import os
import time

ROOT = r"D:\DEpinFarm"
ASN_FILE = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")
OUT_FILE = os.path.join(ROOT, "data", "hosting_subnets.txt")

KEYWORDS = (
    "ovh", "hetzner", "digitalocean", "contabo", "leaseweb", "m247", 
    "colocrossing", "vultr", "linode", "hostinger",
    "amazon", "aws", "ec2", "google", "microsoft", "azure", "oracle",
    "alibaba", "tencent", "scaleway", "ionos", "godaddy", "rackspace",
    "equinix", "hosting", "host", "cloud", "datacenter", "data center",
    "colo", "vps", "dedicated", "server", "akamai", "fastly", "cloudflare",
    "choopa", "melbicom", "netcup", "quadranet", "psychz", "gcore",
    "zenlayer", "upcloud", "hivelocity", "worldstream", "racknerd",
    "hosthatch", "hostens", "serverius", "servers.com", "terrahost",
    "datawagon", "dmit", "colohouse", "hostdime", "singlehop", "steadfast",
    "liquidweb", "bluehost", "hostgator", "siteground", "kinsta", "cogent"
)

def u24_to_str(u24):
    return f"{(u24 >> 16) & 0xFF}.{(u24 >> 8) & 0xFF}.{u24 & 0xFF}"

def main():
    t0 = time.time()
    print(f"Loading {ASN_FILE}...")
    subnets = set()
    total_raw_ips = 0
    matched_ranges = 0
    
    with open(ASN_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 5:
                continue
            try:
                s = int(p[0])
                e = int(p[1])
                asn = p[2].strip()
                cc = p[3].strip()
                org = p[4].strip()
            except ValueError:
                continue
                
            org_l = org.lower()
            if any(kw in org_l for kw in KEYWORDS):
                matched_ranges += 1
                total_raw_ips += (e - s + 1)
                s_u24 = s >> 8
                e_u24 = e >> 8
                for u in range(s_u24, e_u24 + 1):
                    subnets.add(u)
                    
    sorted_u24 = sorted(list(subnets))
    print(f"Matched {matched_ranges:,} ranges ({total_raw_ips:,} raw IPs).")
    print(f"Generated {len(sorted_u24):,} unique /24 subnets ({len(sorted_u24)*256:,} IPs when /24 expanded) in {time.time()-t0:.2f}s.")
    
    print(f"Writing to {OUT_FILE}...")
    with open(OUT_FILE, "w", encoding="utf-8") as out_fp:
        for u in sorted_u24:
            out_fp.write(u24_to_str(u) + "\n")
            
    size_mb = os.path.getsize(OUT_FILE) / (1024 * 1024)
    print(f"Saved {OUT_FILE} ({size_mb:.2f} MB) in {time.time()-t0:.2f}s!")

if __name__ == "__main__":
    main()
