import os
import ipaddress
import bisect

D = r"D:\DEpinFarm"

asns = set()
for line in open(os.path.join(D, "data", "hosting_asns.txt")):
    line = line.strip()
    if line.isdigit():
        asns.add(line)
print("asns:", len(asns), flush=True)

# Parse existing cloud CIDRs into merged [start_u32, end_u32] intervals for ultra-fast dedupe
cf = os.path.join(D, "data", "ranges_cloud.txt")
cloud_intervals = []
if os.path.exists(cf):
    for line in open(cf, errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            if "-" in line:
                p = line.split("-")
                s = int(ipaddress.IPv4Address(p[0].strip()))
                e = int(ipaddress.IPv4Address(p[1].strip()))
                cloud_intervals.append((s, e))
            elif "/" in line:
                net = ipaddress.ip_network(line, strict=False)
                s = int(net.network_address)
                e = int(net.broadcast_address)
                cloud_intervals.append((s, e))
        except Exception:
            pass

# Merge cloud intervals
cloud_intervals.sort()
merged_cloud = []
for s, e in cloud_intervals:
    if not merged_cloud:
        merged_cloud.append((s, e))
    else:
        last_s, last_e = merged_cloud[-1]
        if s <= last_e + 1:
            merged_cloud[-1] = (last_s, max(last_e, e))
        else:
            merged_cloud.append((s, e))

cloud_starts = [x[0] for x in merged_cloud]
cloud_ends = [x[1] for x in merged_cloud]
print("existing cloud intervals (merged):", len(merged_cloud), flush=True)

def is_inside_cloud(c_start, c_end):
    if not cloud_starts:
        return False
    idx = bisect.bisect_right(cloud_starts, c_start) - 1
    if idx >= 0:
        if cloud_ends[idx] >= c_end:
            return True # completely inside existing cloud range
    return False

out_path = os.path.join(D, "data", "ranges_hosting.txt")
out = open(out_path, "w", encoding="utf-8")
seen = set()
total_ips = 0
src = os.path.join(D, "data", "ip2asn-v4-u32.tsv")

for line in open(src, errors="ignore"):
    p = line.rstrip("\n").split("\t")
    if len(p) < 5:
        continue
    asn = p[2]
    if asn not in asns:
        continue
    start_raw, end_raw = p[0], p[1]
    try:
        s_ip = ipaddress.IPv4Address(int(start_raw)) if start_raw.isdigit() else ipaddress.IPv4Address(start_raw)
        e_ip = ipaddress.IPv4Address(int(end_raw)) if end_raw.isdigit() else ipaddress.IPv4Address(end_raw)
        net = ipaddress.summarize_address_range(s_ip, e_ip)
    except Exception:
        continue
    for c in net:
        if c.prefixlen < 8 or c.num_addresses > 1048576:
            continue
        key = str(c)
        if key in seen:
            continue
        seen.add(key)
        
        # Dedupe check against existing cloud ranges
        c_start = int(c.network_address)
        c_end = int(c.broadcast_address)
        if is_inside_cloud(c_start, c_end):
            continue
            
        out.write(key + "\n")
        total_ips += c.num_addresses
        
    if len(seen) % 20000 == 0 and len(seen) > 0:
        print(f"seen {len(seen)} cidrs, ips {total_ips}", flush=True)

out.close()
print("HOSTING_CIDRS", len(seen))
print("HOSTING_IPS", total_ips)
