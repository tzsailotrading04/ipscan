#!/usr/bin/env python3
"""
tools/build_ranges.py
Fetches AWS, GCP, and Azure IP ranges:
- AWS: https://ip-ranges.amazonaws.com/ip-ranges.json
- GCP: https://www.gstatic.com/ipranges/cloud.json
- Azure: ServiceTags Public JSON
Converts every CIDR to individual IPs.
Subtracts cache/pool_dead.txt and ip/harvest/real_pool.txt.
Writes to ip/harvest/queue/ as q_a0_hosting_<ts>_<nn>.txt in 500,000-line files.
Prints total addresses, total files, and the count subtracted.
"""
import os
import sys
import time
import json
import re
import urllib.request
import ipaddress

REPO_ROOT = r"D:\DEpinFarm" if os.path.exists(r"D:\DEpinFarm") else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEAD_FILE = os.path.join(REPO_ROOT, "cache", "pool_dead.txt")
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
QUEUE_DIR = os.path.join(REPO_ROOT, "ip", "harvest", "queue")

AWS_URL = "https://ip-ranges.amazonaws.com/ip-ranges.json"
GCP_URL = "https://www.gstatic.com/ipranges/cloud.json"
AZURE_PAGE = "https://www.microsoft.com/en-us/download/details.aspx?id=56519"
AZURE_FALLBACK = "https://download.microsoft.com/download/7/1/d/71d86715-5596-4529-9b13-da13a5de5b63/ServiceTags_Public_20261026.json"

CHUNK_SIZE = 500000

def fetch_json(url, headers=None, timeout=30):
    hdr = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if headers:
        hdr.update(headers)
    req = urllib.request.Request(url, headers=hdr)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def fetch_aws():
    print("Fetching AWS IP ranges...")
    try:
        raw = fetch_json(AWS_URL)
        data = json.loads(raw)
        cidrs = [p["ip_prefix"] for p in data.get("prefixes", []) if "ip_prefix" in p]
        print(f"  AWS CIDRs fetched: {len(cidrs):,}")
        return cidrs
    except Exception as e:
        print(f"  Error fetching AWS: {e}")
        return []

def fetch_gcp():
    print("Fetching GCP IP ranges...")
    try:
        raw = fetch_json(GCP_URL)
        data = json.loads(raw)
        cidrs = [p["ipv4Prefix"] for p in data.get("prefixes", []) if "ipv4Prefix" in p]
        print(f"  GCP CIDRs fetched: {len(cidrs):,}")
        return cidrs
    except Exception as e:
        print(f"  Error fetching GCP: {e}")
        return []

def fetch_azure():
    print("Fetching Azure ServiceTags...")
    azure_url = AZURE_FALLBACK
    try:
        html = fetch_json(AZURE_PAGE)
        matches = re.findall(r'https://download\.microsoft\.com/download/[^"\'\s]+/ServiceTags_Public_[0-9]+\.json', html)
        if matches:
            azure_url = matches[0]
            print(f"  Discovered latest Azure URL: {azure_url}")
    except Exception as e:
        print(f"  Discovery failed ({e}), using fallback URL: {azure_url}")

    try:
        raw = fetch_json(azure_url)
        data = json.loads(raw)
        cidrs = []
        for val in data.get("values", []):
            for p in val.get("properties", {}).get("addressPrefixes", []):
                if ":" not in p and "/" in p:
                    cidrs.append(p)
        print(f"  Azure CIDRs fetched: {len(cidrs):,}")
        return cidrs
    except Exception as e:
        print(f"  Error fetching Azure: {e}")
        return []

def load_subtracted_ips():
    subtracted = set()
    dead_cnt = 0
    if os.path.exists(DEAD_FILE):
        with open(DEAD_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                for tok in line.split():
                    if ":" in tok and not tok.startswith("["):
                        ip = tok.split(":")[0].strip()
                        subtracted.add(ip)
                        dead_cnt += 1
                        break
                    elif re.match(r'^(?:\d{1,3}\.){3}\d{1,3}$', tok):
                        subtracted.add(tok)
                        dead_cnt += 1
                        break

    pool_cnt = 0
    if os.path.exists(POOL_FILE):
        with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                first_tok = line.split("\t")[0].split()[0]
                ip = first_tok.split(":")[0].strip()
                if ip:
                    subtracted.add(ip)
                    pool_cnt += 1

    print(f"Loaded {len(subtracted):,} unique IPs to subtract (from {dead_cnt:,} dead entries, {pool_cnt:,} pool entries).")
    return subtracted

def main():
    target_count = 10000000
    if len(sys.argv) > 1:
        try:
            target_count = int(sys.argv[1])
        except ValueError:
            pass

    os.makedirs(QUEUE_DIR, exist_ok=True)
    ts = int(time.time())

    # 1. Fetch CIDRs
    aws_cidrs = fetch_aws()
    gcp_cidrs = fetch_gcp()
    azure_cidrs = fetch_azure()

    all_raw_cidrs = set(aws_cidrs + gcp_cidrs + azure_cidrs)
    print(f"Total raw CIDRs from all providers: {len(all_raw_cidrs):,}")

    # Parse and collapse networks
    parsed_nets = []
    for c in all_raw_cidrs:
        try:
            net = ipaddress.ip_network(c.strip(), strict=False)
            if net.version == 4 and not (net.is_private or net.is_loopback or net.is_link_local or net.is_reserved or net.is_multicast):
                parsed_nets.append(net)
        except Exception:
            continue

    print(f"Valid public IPv4 networks: {len(parsed_nets):,}. Collapsing overlaps...")
    collapsed = list(ipaddress.collapse_addresses(parsed_nets))
    print(f"Collapsed into {len(collapsed):,} disjoint networks.")

    # 2. Subtraction set
    subtracted_ips = load_subtracted_ips()

    # 3. Generate individual IPs
    print(f"Generating IPs until queue reaches target {target_count:,} addresses...")
    total_addresses = 0
    total_files = 0
    count_subtracted = 0
    current_file_lines = []
    file_idx = 1

    for net in collapsed:
        # For /31 and /32, use all IPs. For /30 or larger, hosts() skips net and bcast.
        if net.prefixlen >= 31:
            ip_iter = net
        else:
            ip_iter = net.hosts()

        for ip_obj in ip_iter:
            ip_str = str(ip_obj)
            if ip_str in subtracted_ips:
                count_subtracted += 1
                continue

            current_file_lines.append(ip_str)
            total_addresses += 1

            if len(current_file_lines) >= CHUNK_SIZE:
                out_path = os.path.join(QUEUE_DIR, f"q_a0_hosting_{ts}_{file_idx:02d}.txt")
                with open(out_path, "w", encoding="utf-8") as out_f:
                    out_f.write("\n".join(current_file_lines) + "\n")
                total_files += 1
                print(f"  Wrote {out_path} ({len(current_file_lines):,} lines) | total so far: {total_addresses:,}")
                file_idx += 1
                current_file_lines = []

                if total_addresses >= target_count:
                    break

        if total_addresses >= target_count:
            break

    if current_file_lines:
        out_path = os.path.join(QUEUE_DIR, f"q_a0_hosting_{ts}_{file_idx:02d}.txt")
        with open(out_path, "w", encoding="utf-8") as out_f:
            out_f.write("\n".join(current_file_lines) + "\n")
        total_files += 1
        print(f"  Wrote {out_path} ({len(current_file_lines):,} lines) | total so far: {total_addresses:,}")

    print("\n" + "=" * 50)
    print(f"Total addresses: {total_addresses:,}")
    print(f"Total files: {total_files}")
    print(f"Count subtracted: {count_subtracted:,}")
    print("=" * 50)

if __name__ == "__main__":
    main()
