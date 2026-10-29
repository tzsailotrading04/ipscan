#!/usr/bin/env python3
r"""
DEpin Farm ASN Range Builder (v98.180)
- Parses data/ip2asn-v4-u32.tsv
- Builds data/res_subnets.txt (consumer ISP ASNs: India first, then US, UK, DE, BR, ID, PH)
- Builds data/mob_subnets.txt (mobile carriers, same country order)
- Preserves data/dc_subnets.txt
- Strictly excludes AWS, Azure, GCP, Oracle, Alibaba
- Prints subnet and IP counts per file and the grand total
"""
import os
import sys
import time
from collections import OrderedDict

REPO_ROOT = r"D:\DEpinFarm"
ASN_FILE = os.path.join(REPO_ROOT, "data", "ip2asn-v4-u32.tsv")
RES_OUT_FILE = os.path.join(REPO_ROOT, "data", "res_subnets.txt")
MOB_OUT_FILE = os.path.join(REPO_ROOT, "data", "mob_subnets.txt")
DC_FILE = os.path.join(REPO_ROOT, "data", "dc_subnets.txt")

COUNTRY_ORDER = ["IN", "US", "GB", "DE", "BR", "ID", "PH"]

EXCLUDE_HYPERSCALERS = [
    "amazon", "aws", "microsoft", "azure", "google", "oracle", "alibaba", "aliyun"
]

MOB_PATTERNS = [
    "mobility", "cellular", "gprs", "wireless", "lte", "gsm", "t-mobile",
    "verizon wire", "att mob", "telkomsel", "smart comm", "dito tele",
    "three uk", "ee limit", "o2 uk", "telefonica o2", "vodafone idea"
]

RES_PATTERNS = [
    "broadband", "telemedia", "fiber", "fibernet", "cable", "dsl", "consumer",
    "hathway", "act fiber", "beam telecom", "bsnl", "reliance jio", "reliancejio",
    "comcast", "charter", "spectrum", "fios", "cox comm", "centurylink", "lumen",
    "frontier", "optimum", "altice", "windstream", "bt-", "british telecom",
    "virgin media", "sky broad", "talktalk", "plusnet", "zen internet",
    "deutsche telekom", "telekom deutschland", "versatel", "netcologne",
    "claro", "vivo", "net servicos", "oi fixo", "algar", "brisanet",
    "indihome", "telkom ind", "first media", "biznet", "myrepublic",
    "pldt", "converge ict", "globe tele"
]

def u24_to_str(u24):
    return f"{(u24 >> 16) & 0xFF}.{(u24 >> 8) & 0xFF}.{u24 & 0xFF}"

def is_private_or_bogon(s, e):
    o1 = (s >> 24) & 0xFF
    if o1 in (0, 10, 127):
        return True
    if o1 >= 224:
        return True
    if o1 == 172 and 16 <= ((s >> 16) & 0xFF) <= 31:
        return True
    if o1 == 192 and ((s >> 16) & 0xFF) == 168:
        return True
    if o1 == 169 and ((s >> 16) & 0xFF) == 254:
        return True
    if o1 == 100 and 64 <= ((s >> 16) & 0xFF) <= 127:
        return True
    return False

def build_ranges():
    t0 = time.time()
    print("=" * 80)
    print("  BUILDING ASN RANGES (RESIDENTIAL & MOBILE) - v98.180")
    print(f"  Source: {ASN_FILE}")
    print(f"  Country Order: {', '.join(COUNTRY_ORDER)}")
    print(f"  Excluded Hyperscalers: {', '.join(EXCLUDE_HYPERSCALERS)}")
    print("=" * 80)

    if not os.path.exists(ASN_FILE):
        print(f"ERROR: {ASN_FILE} not found!")
        sys.exit(1)

    # Buckets by country
    res_subnets_by_cc = {cc: set() for cc in COUNTRY_ORDER}
    mob_subnets_by_cc = {cc: set() for cc in COUNTRY_ORDER}

    lines_processed = 0
    with open(ASN_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            lines_processed += 1
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 5:
                continue

            cc = parts[3].strip()
            if cc not in COUNTRY_ORDER:
                continue

            desc = parts[4].lower()
            if any(h in desc for h in EXCLUDE_HYPERSCALERS):
                continue

            try:
                s = int(parts[0])
                e = int(parts[1])
            except ValueError:
                continue

            if is_private_or_bogon(s, e):
                continue

            is_mob = any(m in desc for m in MOB_PATTERNS)
            is_res = any(r in desc for r in RES_PATTERNS)

            s_u24 = s >> 8
            e_u24 = e >> 8

            if is_mob:
                for u in range(s_u24, e_u24 + 1):
                    mob_subnets_by_cc[cc].add(u)
            elif is_res:
                for u in range(s_u24, e_u24 + 1):
                    res_subnets_by_cc[cc].add(u)

    print(f"Processed {lines_processed:,} lines from ASN database in {time.time()-t0:.2f}s.")

    # Write data/res_subnets.txt with IN first, then US, GB, DE, BR, ID, PH
    all_res_subnets = []
    print("\n--- RESIDENTIAL CONSUMER ISP SUBNETS ---")
    for cc in COUNTRY_ORDER:
        sorted_cc = sorted(res_subnets_by_cc[cc])
        all_res_subnets.extend(sorted_cc)
        print(f"  {cc:<3}: {len(sorted_cc):>8,} /24 subnets ({len(sorted_cc)*256:>12,} IPs)")

    os.makedirs(os.path.dirname(RES_OUT_FILE), exist_ok=True)
    with open(RES_OUT_FILE, "w", encoding="utf-8") as rf:
        for u in all_res_subnets:
            rf.write(u24_to_str(u) + "\n")

    # Write data/mob_subnets.txt with IN first, then US, GB, DE, BR, ID, PH
    all_mob_subnets = []
    print("\n--- MOBILE CARRIER SUBNETS ---")
    for cc in COUNTRY_ORDER:
        sorted_cc = sorted(mob_subnets_by_cc[cc])
        all_mob_subnets.extend(sorted_cc)
        print(f"  {cc:<3}: {len(sorted_cc):>8,} /24 subnets ({len(sorted_cc)*256:>12,} IPs)")

    os.makedirs(os.path.dirname(MOB_OUT_FILE), exist_ok=True)
    with open(MOB_OUT_FILE, "w", encoding="utf-8") as mf:
        for u in all_mob_subnets:
            mf.write(u24_to_str(u) + "\n")

    # Inspect data/dc_subnets.txt
    dc_count = 0
    if os.path.exists(DC_FILE):
        with open(DC_FILE, "r", encoding="utf-8", errors="ignore") as df:
            dc_count = sum(1 for line in df if line.strip() and not line.startswith("#"))
    else:
        print(f"WARNING: {DC_FILE} not found!")

    total_subnets = len(all_res_subnets) + len(all_mob_subnets) + dc_count
    total_ips = total_subnets * 256

    print("\n" + "=" * 80)
    print("  SUBNETS AND IP COUNTS SUMMARY")
    print("=" * 80)
    print(f"  data/res_subnets.txt:  {len(all_res_subnets):>10,} /24 subnets ({len(all_res_subnets)*256:>14,} IPs)")
    print(f"  data/mob_subnets.txt:  {len(all_mob_subnets):>10,} /24 subnets ({len(all_mob_subnets)*256:>14,} IPs)")
    print(f"  data/dc_subnets.txt:   {dc_count:>10,} /24 subnets ({dc_count*256:>14,} IPs)")
    print("-" * 80)
    print(f"  GRAND TOTAL:           {total_subnets:>10,} /24 subnets ({total_ips:>14,} IPs)")
    print(f"  Completed in {time.time()-t0:.2f}s.")
    print("=" * 80)

if __name__ == "__main__":
    build_ranges()
