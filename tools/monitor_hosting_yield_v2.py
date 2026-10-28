"""
monitor_hosting_yield_v2.py
Pulls the latest shard progress and verified alive files from origin/main.
Computes:
1. Total scanned IPs across all 20 shards
2. Total genuine verified proxies found with multi-target strict probe (0x16)
3. Genuine per 1,000 IPs live rate
4. Breakdown by port (:80, :443, :3128, :8080, :8000, :1080, :8118, :8888)
5. Breakdown by provider (OVH, Hetzner, Contabo, DO, etc.)
"""
import glob
import os
import subprocess
import time
import bisect

ROOT = r"D:\DEpinFarm"
ASN_FILE = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")

def pull_latest():
    subprocess.run(["git", "-C", ROOT, "fetch", "origin", "main", "--quiet"], capture_output=True)
    subprocess.run(["git", "-C", ROOT, "pull", "--no-edit", "-s", "ort", "-X", "ours", "origin", "main", "--quiet"], capture_output=True)

class ASNLookup:
    def __init__(self, tsv_path):
        self.starts = []
        self.ends = []
        self.orgs = []
        if not os.path.exists(tsv_path):
            return
        with open(tsv_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) >= 5:
                    try:
                        self.starts.append(int(p[0]))
                        self.ends.append(int(p[1]))
                        self.orgs.append(p[4].strip())
                    except ValueError:
                        continue

    def lookup(self, ip_str):
        if not self.starts:
            return "Unknown"
        try:
            octets = [int(x) for x in ip_str.split(".")]
            u32 = (octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]
            idx = bisect.bisect_right(self.starts, u32) - 1
            if idx >= 0 and u32 <= self.ends[idx]:
                return self.orgs[idx]
        except Exception:
            pass
        return "Unknown"

def main():
    pull_latest()
    
    total_scanned = 0
    total_rate = 0.0
    shard_offsets = {}
    
    for i in range(20):
        tag = f"{i:02d}"
        s_path = os.path.join(ROOT, "ip", "harvest", f"shodan_stats_v98_{tag}.txt")
        offset = 0
        req_s = 0.0
        if os.path.exists(s_path):
            with open(s_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        if k == "offset":
                            try: offset = int(v)
                            except ValueError: pass
                        elif k == "req_s":
                            try: req_s = float(v)
                            except ValueError: pass
        total_scanned += offset
        total_rate += req_s
        shard_offsets[tag] = (offset, req_s)

    # Collect all verified proxies from parts
    all_proxies = set()
    port_counts = {80: 0, 443: 0, 3128: 0, 8080: 0, 8000: 0, 1080: 0, 8118: 0, 8888: 0}
    other_ports = {}
    
    asn_lookup = ASNLookup(ASN_FILE)
    provider_counts = {}

    v_files = sorted(glob.glob(os.path.join(ROOT, "ip", "harvest", "verified_alive_part_*.txt")))
    for vf in v_files:
        with open(vf, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                addr = line.split("\t")[0].strip()
                if ":" in addr:
                    all_proxies.add(addr)

    for addr in all_proxies:
        ip, p_str = addr.split(":")
        try:
            port = int(p_str)
            if port in port_counts:
                port_counts[port] += 1
            else:
                other_ports[port] = other_ports.get(port, 0) + 1
        except ValueError:
            continue
            
        org = asn_lookup.lookup(ip).upper()
        # Classify provider
        prov = "OTHER / UNKNOWN"
        for candidate in ["OVH", "HETZNER", "CONTABO", "VULTR", "LINODE", "DIGITALOCEAN", "LEASEWEB", "COLOCROSSING", "M247", "HOSTINGER"]:
            if candidate in org:
                prov = candidate
                break
        provider_counts[prov] = provider_counts.get(prov, 0) + 1

    total_verified = len(all_proxies)
    yield_per_1k = (total_verified / max(1, total_scanned)) * 1000

    print("=" * 70)
    print("BUDGET HOSTING FLEET - REAL-TIME HARVEST MONITOR")
    print("=" * 70)
    print(f"Total Unique Hosting IPs Scanned: {total_scanned:,}")
    print(f"Fleet Aggregate Speed:            {total_rate:,.1f} req/s")
    print(f"Total Genuine Proxies Verified:   {total_verified:,}")
    print(f"Genuine Yield per 1,000 IPs:      {yield_per_1k:.4f}")
    print("-" * 70)
    print("PORT BREAKDOWN:")
    for p in [80, 443, 3128, 8080, 8000, 1080, 8118, 8888]:
        cnt = port_counts[p]
        pct = (cnt / max(1, total_verified)) * 100
        print(f"  Port {p:<5} : {cnt:6,} ({pct:5.1f}%)")
    if other_ports:
        print(f"  Other ports: {sum(other_ports.values()):,} across {len(other_ports)} ports")
    print("-" * 70)
    print("PROVIDER BREAKDOWN:")
    for prov, cnt in sorted(provider_counts.items(), key=lambda x: x[1], reverse=True):
        pct = (cnt / max(1, total_verified)) * 100
        print(f"  {prov:<16} : {cnt:6,} ({pct:5.1f}%)")
    print("=" * 70)

if __name__ == "__main__":
    main()
