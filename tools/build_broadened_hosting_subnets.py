"""
tools/build_broadened_hosting_subnets.py
Builds data/hosting_subnets.txt from data/ip2asn-v4-u32.tsv:
- Includes existing 10 providers: OVH, Hetzner, DigitalOcean, Contabo, Leaseweb, M247, ColoCrossing, Vultr, Linode, Hostinger.
- Includes mid-tier, regional, resellers, and colocation worldwide: Scaleway, IONOS, GoDaddy, Netcup, QuadraNet, Psychz, G-Core, Zenlayer, UpCloud, Hivelocity, Worldstream, RackNerd, HostHatch, Hostens, Serverius, Servers.com, TerraHost, DataWagon, DMIT, Liquid Web, SiteGround, Bluehost, HostGator, Cogent, Equinix, ColoHouse, HostDime, SingleHop, Steadfast, Rackspace, Choopa, Melbicom.
- Matches any org with hosting, datacenter, data center, colo, vps, dedicated.
- Strictly excludes hyperscalers: Amazon/AWS, Google/GCP, Microsoft/Azure, Oracle, Alibaba, Tencent, Cloudflare.
"""
import os
import time

ROOT = r"D:\DEpinFarm"
ASN_FILE = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")
OUT_FILE = os.path.join(ROOT, "data", "hosting_subnets.txt")

HYPERSCALERS = (
    "amazon", "aws", "ec2", "google", "gcp", "microsoft", "azure", 
    "oracle", "alibaba", "tencent", "cloudflare"
)

TARGET_KW = (
    "ovh", "hetzner", "digitalocean", "contabo", "leaseweb", "m247", 
    "colocrossing", "vultr", "linode", "hostinger",
    "scaleway", "ionos", "godaddy", "rackspace",
    "equinix", "hosting", "datacenter", "data center",
    "colo", "colocation", "vps", "dedicated", "choopa", "melbicom", "netcup", "quadranet",
    "psychz", "gcore", "zenlayer", "upcloud", "hivelocity", "worldstream",
    "racknerd", "hosthatch", "hostens", "serverius", "servers.com", "terrahost",
    "datawagon", "dmit", "colohouse", "hostdime", "singlehop", "steadfast",
    "liquidweb", "bluehost", "hostgator", "siteground", "kinsta", "cogent"
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

            # Exclude hyperscalers
            if any(h in org for h in HYPERSCALERS):
                continue

            if any(kw in org for kw in TARGET_KW):
                matched_ranges += 1
                total_raw_ips += (e - s + 1)
                for u in range(s >> 8, (e >> 8) + 1):
                    subnets.add(u)

    sorted_u24 = sorted(list(subnets))
    print(f"Matched {matched_ranges:,} ranges ({total_raw_ips:,} raw IPs).")
    print(f"Generated {len(sorted_u24):,} unique /24 subnets ({len(sorted_u24)*256:,} IPs) in {time.time()-t0:.2f}s.")

    print(f"Writing to {OUT_FILE}...")
    with open(OUT_FILE, "w", encoding="utf-8") as out_fp:
        for u in sorted_u24:
            out_fp.write(u24_to_str(u) + "\n")

    size_mb = os.path.getsize(OUT_FILE) / (1024 * 1024)
    print(f"Successfully generated {OUT_FILE} ({size_mb:.2f} MB, {len(sorted_u24):,} subnets).")

if __name__ == "__main__":
    main()
