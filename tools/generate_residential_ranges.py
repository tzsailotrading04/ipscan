import os
import time

ROOT = r"D:\DEpinFarm"
ASN_FILE = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")
RANGES_OUT = os.path.join(ROOT, "data", "residential_ranges.txt")
HOSTING_ASNS_FILE = os.path.join(ROOT, "data", "hosting_asns.txt")

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

def u32_to_ip(u):
    return f"{(u >> 24) & 0xFF}.{(u >> 16) & 0xFF}.{(u >> 8) & 0xFF}.{u & 0xFF}"

def is_private_or_reserved(s, e):
    o1 = (s >> 24) & 0xFF
    if o1 in (0, 10, 127) or o1 >= 224:
        return True
    if o1 == 172 and 16 <= ((s >> 16) & 0xFF) <= 31:
        return True
    if o1 == 192 and ((s >> 16) & 0xFF) == 168:
        return True
    if o1 == 100 and 64 <= ((s >> 16) & 0xFF) <= 127:
        return True
    return False

def range_to_cidrs(start, end):
    cidrs = []
    while end >= start:
        max_size = 32
        while max_size > 0:
            mask = ~((1 << (32 - (max_size - 1))) - 1) & 0xFFFFFFFF
            if (start & mask) != start:
                break
            max_size -= 1
        x = 32 - int((end - start + 1)).bit_length() + 1
        if max_size < x:
            max_size = x
        cidrs.append(f"{u32_to_ip(start)}/{max_size}")
        start += (1 << (32 - max_size))
    return cidrs

def main():
    hosting_asns = set()
    if os.path.exists(HOSTING_ASNS_FILE):
        with open(HOSTING_ASNS_FILE) as f:
            for l in f:
                l = l.strip()
                if l: hosting_asns.add(l)

    t0 = time.time()
    total_ips = 0
    matched_ranges = 0

    print("Generating residential CIDR ranges...")
    with open(ASN_FILE, "r", encoding="utf-8", errors="ignore") as f_in, \
         open(RANGES_OUT, "w", encoding="utf-8") as f_out:
        for line in f_in:
            p = line.rstrip("\n").split("\t")
            if len(p) < 5:
                continue
            try:
                s = int(p[0])
                e = int(p[1])
                asn = p[2].strip()
                org = p[4].strip()
            except ValueError:
                continue

            if is_private_or_reserved(s, e):
                continue

            org_l = org.lower()
            if asn in hosting_asns or any(kw in org_l for kw in HOSTING_KEYWORDS):
                continue

            matched_ranges += 1
            total_ips += (e - s + 1)
            f_out.write(f"{s}\t{e}\t{asn}\t{org}\n")

    sz = os.path.getsize(RANGES_OUT) / (1024 * 1024)
    print(f"Generated {RANGES_OUT}: {matched_ranges:,} ranges, {total_ips:,} total IPs ({sz:.2f} MB)")

if __name__ == "__main__":
    main()
