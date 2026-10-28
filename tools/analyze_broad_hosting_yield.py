import os
import glob
import bisect

ROOT = r"D:\DEpinFarm"
TSV_PATH = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")

def ip_to_u32(ip_str):
    parts = [int(p) for p in ip_str.split(".")]
    return (parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]

def load_asn_db():
    ranges = []
    with open(TSV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 5:
                start_u32 = int(parts[0])
                end_u32 = int(parts[1])
                asn = parts[2]
                cc = parts[3]
                desc = parts[4]
                ranges.append((start_u32, end_u32, asn, desc))
    ranges.sort(key=lambda x: x[0])
    start_keys = [r[0] for r in ranges]
    return ranges, start_keys

def lookup_ip(ip_str, ranges, start_keys):
    u = ip_to_u32(ip_str)
    idx = bisect.bisect_right(start_keys, u) - 1
    if idx >= 0:
        start_u32, end_u32, asn, desc = ranges[idx]
        if start_u32 <= u <= end_u32:
            return asn, desc
    return "UNKNOWN", "UNKNOWN"

def analyze():
    # 1. Parse stats
    shards_stats = {}
    total_speed = 0.0
    total_scanned_ips = 0
    total_errno99 = 0
    active_workers = 0

    for i in range(20):
        tag = f"{i:02d}"
        fpath = os.path.join(ROOT, "ip", "harvest", f"shodan_stats_v98_{tag}.txt")
        if os.path.exists(fpath):
            data = {}
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().replace("\\n", "\n")
                for line in content.splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        data[k.strip()] = v.strip()
            shards_stats[tag] = data

    print("=" * 80)
    print("FLEET BROAD-HOSTING SCAN STATUS (6 Workers/Container)")
    print("=" * 80)
    print(f"{'Shard':<6} {'Offset':<18} {'Req/s':<10} {'Errno99':<10} {'Workers':<8} {'Engine'}")
    print("-" * 80)

    for i in range(20):
        tag = f"{i:02d}"
        s = shards_stats.get(tag, {})
        offset = int(s.get("offset", 0))
        total = int(s.get("total", 1753088))
        req_s = float(s.get("req_s", 0.0))
        e99 = int(s.get("errno99", 0))
        w = int(s.get("workers", 0))
        engine = s.get("engine", "v98.164")

        total_speed += req_s
        total_scanned_ips += offset
        total_errno99 += e99
        active_workers += w

        pct = (offset / total * 100) if total else 0.0
        print(f"{tag:<6} {offset:>7}/{total:<8} ({pct:4.1f}%) {req_s:>8.1f}/s {e99:>8} {w:>6}    {engine}")

    print("-" * 80)
    print(f"Total Fleet Scan Speed  : {total_speed:,.1f} IPs/s")
    print(f"Total Scanned in Sweep  : {total_scanned_ips:,} IPs")
    print(f"Total Errno99 (Exhaust) : {total_errno99}")
    print(f"Active Worker Processes : {active_workers} / 120 (Target 6/container)")

    # 2. Collect newly discovered proxies in verified_alive_part_*_w*.txt
    print("\n" + "=" * 80)
    print("NEWLY DISCOVERED CANDIDATES FROM 6-WORKER RUNS")
    print("=" * 80)

    new_proxies = set()
    worker_files = glob.glob(os.path.join(ROOT, "ip", "harvest", "verified_alive_part_*_w*.txt"))
    for wf in worker_files:
        with open(wf, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line and ":" in line:
                    new_proxies.add(line)

    print(f"Found {len(new_proxies)} unique candidate entries in worker partition files.")
    if new_proxies:
        ranges, start_keys = load_asn_db()
        provider_counts = {}
        port_counts = {}

        for p in new_proxies:
            ip, port = p.split(":", 1)
            port_counts[port] = port_counts.get(port, 0) + 1
            asn, desc = lookup_ip(ip, ranges, start_keys)
            # Simplify provider name
            prov_name = desc.split()[0].rstrip(",.-") if desc != "UNKNOWN" else asn
            provider_counts[prov_name] = provider_counts.get(prov_name, 0) + 1

        print("\nYield by Port:")
        for pt, cnt in sorted(port_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  Port {pt:<5} : {cnt} candidates")

        print("\nYield by Provider / ASN:")
        for prov, cnt in sorted(provider_counts.items(), key=lambda x: x[1], reverse=True)[:15]:
            print(f"  {prov:<25} : {cnt} candidates")

    # 3. Time to 30,000 proxies calculation
    print("\n" + "=" * 80)
    print("ESTIMATED TIME TO 30,000 PROXIES")
    print("=" * 80)
    # Total remaining IPs in 35M broad hosting pass
    remaining_ips = 35060992 - total_scanned_ips
    print(f"Remaining broad hosting pool: {remaining_ips:,} IPs")
    if total_speed > 0:
        sec_to_complete_pool = remaining_ips / total_speed
        hrs_to_complete_pool = sec_to_complete_pool / 3600
        print(f"At {total_speed:,.1f} IPs/s, complete 35M pool sweep finishes in: {hrs_to_complete_pool:.2f} hours")
    
if __name__ == "__main__":
    analyze()
