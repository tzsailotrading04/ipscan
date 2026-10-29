import os
import time

ROOT = r"D:\DEpinFarm"
ASN_FILE = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")
OUT_FILE = os.path.join(ROOT, "data", "residential_subnets.txt")
HOSTING_ASNS_FILE = os.path.join(ROOT, "data", "hosting_asns.txt")

# Keywords that indicate hosting / cloud / datacenter / hyperscalers
HOSTING_KEYWORDS = (
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

def is_private_or_reserved(s, e):
    # Exclude 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 
    # 172.16.0.0/12, 192.0.0.0/24, 192.0.2.0/24, 192.88.99.0/24, 192.168.0.0/16,
    # 198.18.0.0/15, 198.51.100.0/24, 203.0.113.0/24, 224.0.0.0/4 (multicast/reserved)
    # Convert s to first octet
    o1 = (s >> 24) & 0xFF
    if o1 in (0, 10, 127):
        return True
    if o1 >= 224:
        return True
    if o1 == 172 and 16 <= ((s >> 16) & 0xFF) <= 31:
        return True
    if o1 == 192 and ((s >> 16) & 0xFF) == 168:
        return True
    if o1 == 100 and 64 <= ((s >> 16) & 0xFF) <= 127:
        return True
    return False

def build():
    t0 = time.time()
    hosting_asns = set()
    if os.path.exists(HOSTING_ASNS_FILE):
        with open(HOSTING_ASNS_FILE) as f:
            for l in f:
                l = l.strip()
                if l: hosting_asns.add(l)

    print(f"Loaded {len(hosting_asns)} known hosting ASNs.")
    print(f"Streaming {ASN_FILE}...")

    # We collect residential / ISP subnets
    # To keep memory bounded and deterministic, collect canonical u24 ints
    res_subnets = []
    total_ips = 0
    res_ranges = 0
    excluded_hosting_ranges = 0

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

            if is_private_or_reserved(s, e):
                continue

            org_l = org.lower()
            if asn in hosting_asns or any(kw in org_l for kw in HOSTING_KEYWORDS):
                excluded_hosting_ranges += 1
                continue

            # This is residential / ISP
            res_ranges += 1
            num_ips = e - s + 1
            total_ips += num_ips
            
            s_u24 = s >> 8
            e_u24 = e >> 8
            for u in range(s_u24, e_u24 + 1):
                res_subnets.append(u)

    print(f"Processed TSV in {time.time()-t0:.1f}s. Matched {res_ranges:,} residential ranges ({excluded_hosting_ranges:,} hosting excluded).")
    print(f"Total raw IPs in residential ranges: {total_ips:,}")
    print("Deduplicating subnets...")
    res_subnets = sorted(set(res_subnets))
    print(f"Unique /24 residential subnets: {len(res_subnets):,} ({len(res_subnets)*256:,} IPs)")

    print(f"Writing to {OUT_FILE}...")
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for u in res_subnets:
            f.write(u24_to_str(u) + "\n")

    print(f"Done in {time.time()-t0:.1f}s. File size: {os.path.getsize(OUT_FILE)/(1024*1024):.1f} MB")

if __name__ == "__main__":
    build()
