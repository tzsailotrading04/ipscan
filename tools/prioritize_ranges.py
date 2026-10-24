#!/usr/bin/env python3
"""
tools/prioritize_ranges.py
Sorts and interleaves CIDRs by historical productivity across 20 kernel slices,
so each kernel gets a disjoint slice of 43,376 CIDRs with the most productive
CIDRs first and barren ones last.
"""
import ipaddress
import bisect
import os
import glob

ROOT = r"D:\DEpinFarm"

def main():
    # 1. Collect all known productive IP addresses
    known_ips = set()

    # master_pool.txt
    mp_file = os.path.join(ROOT, "master_pool.txt")
    if os.path.exists(mp_file):
        with open(mp_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line:
                    p = line.split()[0]
                    ip = p.split(':')[0]
                    known_ips.add(ip)

    # hits/*.txt
    for hf in glob.glob(os.path.join(ROOT, "hits", "hits_*.txt")):
        with open(hf, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line:
                    p = line.split()[0]
                    ip = p.split(':')[0]
                    known_ips.add(ip)

    # verified_alive.txt
    va_file = os.path.join(ROOT, "ip", "harvest", "verified_alive.txt")
    if os.path.exists(va_file):
        with open(va_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line:
                    p = line.split()[0]
                    ip = p.split(':')[0]
                    known_ips.add(ip)

    print(f"Total unique known productive IPs: {len(known_ips)}")

    known_ints = []
    for ip_str in known_ips:
        try:
            known_ints.append(int(ipaddress.IPv4Address(ip_str)))
        except Exception:
            pass
    known_ints.sort()

    ranges_file = os.path.join(ROOT, "data", "ranges_all.txt")
    with open(ranges_file, "r", encoding="utf-8") as f:
        cidrs = [line.strip() for line in f if line.strip()]

    total_cidrs = len(cidrs)
    print(f"Total CIDRs: {total_cidrs}")

    # Count hits per CIDR
    scored_cidrs = []
    for idx, c in enumerate(cidrs):
        try:
            net = ipaddress.IPv4Network(c)
            net_start = int(net.network_address)
            net_end = int(net.broadcast_address)
            i_left = bisect.bisect_left(known_ints, net_start)
            i_right = bisect.bisect_right(known_ints, net_end)
            hits = i_right - i_left
            scored_cidrs.append((hits, idx, c))
        except Exception:
            scored_cidrs.append((0, idx, c))

    # Sort descending by hits, then original idx
    scored_cidrs.sort(key=lambda x: (-x[0], x[1]))

    productive_count = sum(1 for x in scored_cidrs if x[0] > 0)
    print(f"Productive CIDRs (hits > 0): {productive_count}")

    # Distribute round-robin into 20 slices so each slice has top productive CIDRs at the front
    num_slices = 20
    slice_buckets = [[] for _ in range(num_slices)]
    for rank, item in enumerate(scored_cidrs):
        bucket_idx = rank % num_slices
        slice_buckets[bucket_idx].append(item[2])

    # Recombine in order of slices: Slice 0, Slice 1, ..., Slice 19
    reordered_cidrs = []
    for s_idx, bucket in enumerate(slice_buckets):
        reordered_cidrs.extend(bucket)

    assert len(reordered_cidrs) == total_cidrs, f"Mismatch: {len(reordered_cidrs)} vs {total_cidrs}"

    # Write out new ranges_all.txt
    with open(ranges_file, "w", encoding="utf-8", newline="\n") as f:
        for c in reordered_cidrs:
            f.write(c + "\n")

    print(f"Successfully wrote {len(reordered_cidrs)} prioritized CIDRs to {ranges_file}")

    # Print bounds per slice
    print("\nSlice block bounds (43,376 per kernel):")
    for s in range(num_slices):
        start = s * 43376
        end = min((s + 1) * 43376 - 1, total_cidrs - 1)
        count = end - start + 1
        print(f"  Kernel {s:2d} (cl_{chr(ord('a')+s)}): [{start:6d}, {end:6d}] (count={count})")

if __name__ == "__main__":
    main()
