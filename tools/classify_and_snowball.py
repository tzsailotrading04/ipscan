#!/usr/bin/env python3
"""
tools/classify_and_snowball.py - Classify master pool by ASN and build residential snowball
"""

import os
import bisect
import socket
import struct
import re
from collections import Counter

ROOT = r"D:\DEpinFarm"
ASN_FILE = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")
RES_RANGES_FILE = os.path.join(ROOT, "data", "residential_ranges.txt")
MOB_RANGES_FILE = os.path.join(ROOT, "data", "mobile_ranges.txt")
MASTER_POOL_FILE = os.path.join(ROOT, "master_pool.txt")
MASTER_FAST_FILE = os.path.join(ROOT, "master_fast.txt")
OUT_TSV = os.path.join(ROOT, "master_pool_classified.tsv")
OUT_SNOWBALL = os.path.join(ROOT, "ip", "rs_snowball.txt")

def ip_to_u32(ip):
    return struct.unpack("!I", socket.inet_aton(ip))[0]

def u32_to_ip(u):
    return socket.inet_ntoa(struct.pack("!I", u))

def load_ranges(path):
    intervals = []
    if not os.path.exists(path):
        return [], []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or "-" not in line:
                continue
            s, e = line.split("-")
            try:
                intervals.append((ip_to_u32(s), ip_to_u32(e)))
            except Exception:
                pass
    intervals.sort()
    merged = []
    for s, e in intervals:
        if not merged:
            merged.append((s, e))
        elif s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    starts = [m[0] for m in merged]
    return merged, starts

def in_intervals(u, intervals, starts):
    if not intervals:
        return False
    i = bisect.bisect_right(starts, u) - 1
    return i >= 0 and intervals[i][0] <= u <= intervals[i][1]

def load_asn_table():
    rows = []
    with open(ASN_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 5:
                try:
                    rows.append((int(parts[0]), int(parts[1]), parts[2], parts[3], parts[4]))
                except ValueError:
                    pass
    rows.sort()
    starts = [r[0] for r in rows]
    return rows, starts

print("Loading ASN table and range files...")
asn_rows, asn_starts = load_asn_table()
res_intervals, res_starts = load_ranges(RES_RANGES_FILE)
mob_intervals, mob_starts = load_ranges(MOB_RANGES_FILE)
print(f"Loaded {len(asn_rows):,} ASN rows, {len(res_intervals):,} residential ranges, {len(mob_intervals):,} mobile ranges.")

def lookup_asn(u):
    i = bisect.bisect_right(asn_starts, u) - 1
    if i >= 0 and asn_rows[i][0] <= u <= asn_rows[i][1]:
        return asn_rows[i][2], asn_rows[i][4]
    return "0", "UNKNOWN"

RES_ASNS = {
    '54600', '138089', '21859', '149360', '142393', '34984', '210976', '28458', '141071',
    '45305', '263767', '38264', '58224', '32098', '21003', '202561', '135607', '23956',
    '270075', '4788', '37403', '38511', '55685', '45700', '29873', '20001', '27951', '272405'
}
MOB_ASNS = {'63501', '58485'}

DC_SUBS = [
    'hetzner', 'ovh', 'digitalocean', 'linode', 'vultr', 'contabo', 'scaleway', 'leaseweb',
    'colocrossing', 'psychz', 'frantech', 'hosthatch', 'racknerd', 'servermania', 'amazon',
    'aws', 'google', 'gcp', 'microsoft', 'azure', 'oracle', 'alibaba', 'tencent', 'huawei',
    'm247', 'choopa', 'melbicom', 'netcup', 'quadranet', 'gcore', 'zenlayer', 'upcloud',
    'hivelocity', 'worldstream', 'hostens', 'serverius', 'server', 'servers', 'vps',
    'dedicated', 'colo', 'colocation', 'hosting', 'host', 'hostinger', 'cloud', 'datacenter',
    'data center', 'akamai', 'fastly', 'cloudflare', 'ramnode', 'performive', 'datawagon',
    'dmit', 'colohouse', 'hostdime', 'liquidweb', 'ipxo', 'tierpoint', 'cogent', 'shinjiru',
    'fdcservers', 'intergrid', 'tzulo', 'shock', 'quadrix', 'hostkey', 'blazingfast',
    'time4vps', 'timeweb', 'ionos', 'godaddy', 'rackspace', 'equinix', 'cdn', 'freakhosting',
    'ucloud', 'ctrls', 'aeza', 'zscaler', 'gtt-backbone', 'tor-exit', 'emerald-onion'
]

MOB_SUBS = [
    'mobile', 'cellular', 'wireless', 'gsm', 'lte', '4g', '5g', 'cellco', 't-mobile',
    'turkcell', 'jio', 'reliance', 'claro', 'movistar', 'vodafone', 'airtel', 'smartfren',
    'telkomsel', 'indosat', 'zain', 'etisalat', 'safaricom', 'mtn', 'ooredoo'
]

ISP_SUBS = [
    'telecom', 'telekom', 'telephon', 'telecomunicacoes', 'telecomunicaciones', 'broadband',
    'cable', 'communication', 'comunicaciones', 'comunicacion', 'online', 'jaringan', 'internet',
    'fiber', 'fibre', 'fibra', 'dsl', 'adsl', 'isp', 'telefonica', 'telia', 'telenor', 'kpn',
    'swisscom', 'comcast', 'verizon', 'charter', 'cox', 'centurylink', 'frontier',
    'windstream', 'mediacom', 'altice', 'rogers', 'bell canada', 'telus', 'shaw',
    'videotron', 'at&t', 'bellsouth', 'telkom', 'telstra', 'optus', 'iinet', 'tpg',
    'vocus', 'singtel', 'starhub', 'pccw', 'hkt', 'china telecom', 'china unicom',
    'chinanet', 'kddi', 'softbank', 'biglobe', 'plala', 'so-net', 'jcom', 'viettel',
    'vnpt', 'fpt', 'pln', 'ufinet', 'cantv', 'myrepublic', 'tot-net', 'net',
    'idnic', 'redes', 'kabel', 'satelit', 'starlink'
]

def classify(u, asn, asn_name):
    d = asn_name.lower()
    asn_num = str(asn).upper().replace("AS", "").strip()
    
    # 1. Explicit ASNs
    if asn_num in MOB_ASNS:
        return "MOBILE"
    if asn_num in RES_ASNS:
        return "RESIDENTIAL"

    # 2. Datacenter keywords
    for dc in DC_SUBS:
        if dc in d:
            return "DATACENTER"

    # 3. Mobile ranges / keywords
    if in_intervals(u, mob_intervals, mob_starts) or any(m in d for m in MOB_SUBS):
        return "MOBILE"

    # 4. Residential ranges / ISP keywords
    if in_intervals(u, res_intervals, res_starts) or any(isp in d for isp in ISP_SUBS):
        return "RESIDENTIAL"

    return "UNKNOWN"

# Read master_fast.txt to identify FAST exits
fast_exits = set()
if os.path.exists(MASTER_FAST_FILE):
    with open(MASTER_FAST_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                fast_exits.add(parts[1])

# Parse master_pool.txt
classified_rows = []
residential_exits = []

with open(MASTER_POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        proxy_addr = parts[0]
        exit_ip = parts[1]
        
        # port
        proxy_port = proxy_addr.split(":")[-1] if ":" in proxy_addr else ""
        
        # tier
        tier = "FAST" if exit_ip in fast_exits else "SLOW"
        if len(parts) >= 4:
            try:
                ttfb = int(parts[2])
                kbps = float(parts[3])
                if ttfb < 1000 and kbps >= 300.0:
                    tier = "FAST"
            except ValueError:
                pass
        
        try:
            u = ip_to_u32(exit_ip)
            asn, asn_name = lookup_asn(u)
            cls = classify(u, asn, asn_name)
        except Exception:
            asn, asn_name = "0", "UNKNOWN"
            cls = "UNKNOWN"
            
        classified_rows.append((exit_ip, proxy_port, asn, asn_name, cls, tier))
        if cls == "RESIDENTIAL":
            residential_exits.append((exit_ip, proxy_port))

# Write master_pool_classified.tsv
with open(OUT_TSV, "w", encoding="utf-8", newline="\n") as f:
    f.write("exit_ip\tproxy_port\tasn\tasn_name\tclass\ttier\n")
    for row in classified_rows:
        f.write(f"{row[0]}\t{row[1]}\t{row[2]}\t{row[3]}\t{row[4]}\t{row[5]}\n")

print(f"Wrote {len(classified_rows)} classified records to {OUT_TSV}")

# Counts breakdown
total_counts = Counter()
fast_counts = Counter()
slow_counts = Counter()

for row in classified_rows:
    cls = row[4]
    tier = row[5]
    total_counts[cls] += 1
    if tier == "FAST":
        fast_counts[cls] += 1
    else:
        slow_counts[cls] += 1

print("\n=== CLASSIFICATION SUMMARY ===")
print(f"{'CLASS':<15} {'TOTAL':<10} {'FAST':<10} {'SLOW':<10}")
print("-" * 45)
for c in ["RESIDENTIAL", "MOBILE", "DATACENTER", "UNKNOWN"]:
    print(f"{c:<15} {total_counts[c]:<10} {fast_counts[c]:<10} {slow_counts[c]:<10}")
print("-" * 45)
total_all = len(classified_rows)
total_fast = len(fast_exits)
total_slow = total_all - total_fast
print(f"{'TOTAL':<15} {total_all:<10} {total_fast:<10} {total_slow:<10}")

# STEP 3 - Build residential snowball
print("\nBuilding residential snowball from RESIDENTIAL exits...")
snowball_targets = set()

for exit_ip, proxy_port in residential_exits:
    if not proxy_port:
        continue
    octets = exit_ip.split(".")
    if len(octets) != 4:
        continue
    prefix = f"{octets[0]}.{octets[1]}.{octets[2]}"
    self_last = int(octets[3])
    
    for last_octet in range(1, 255):
        if last_octet == self_last:
            continue
        snowball_targets.add(f"{prefix}.{last_octet}:{proxy_port}")

os.makedirs(os.path.dirname(OUT_SNOWBALL), exist_ok=True)
with open(OUT_SNOWBALL, "w", encoding="utf-8", newline="\n") as f:
    for target in sorted(snowball_targets):
        f.write(target + "\n")

print(f"Wrote {len(snowball_targets):,} snowball targets to {OUT_SNOWBALL}")
print(f"Residential seed exits: {len(residential_exits):,}")
print(f"Unique /24 expansion lines generated: {len(snowball_targets):,}")
