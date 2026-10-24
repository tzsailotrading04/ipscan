#!/usr/bin/env python3
"""
tools/merge_hits.py - Merge hits/hits_*.txt into master_pool.txt
Deduplicates by proxy address (IP:PORT) and exit IP.
"""
import os
import glob
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER_POOL = os.path.join(ROOT, "master_pool.txt")
HITS_DIR = os.path.join(ROOT, "hits")

def main():
    existing_proxies = set()
    existing_lines = []
    
    if os.path.exists(MASTER_POOL):
        with open(MASTER_POOL, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                existing_proxies.add(parts[0])
                existing_lines.append(line)
                
    initial_count = len(existing_lines)
    print(f"Initial master_pool.txt count: {initial_count}")
    
    hit_files = sorted(glob.glob(os.path.join(HITS_DIR, "hits_*.txt")),
                       key=lambda x: int(os.path.basename(x).split('_')[1].split('.')[0]) if os.path.basename(x).split('_')[1].split('.')[0].isdigit() else 999)
    
    total_hit_rows = 0
    new_rows = []
    
    for hf in hit_files:
        bname = os.path.basename(hf)
        count = 0
        with open(hf, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                count += 1
                total_hit_rows += 1
                parts = line.split()
                proxy = parts[0]
                if proxy not in existing_proxies:
                    existing_proxies.add(proxy)
                    new_rows.append(line)
        print(f"  {bname:12s}: {count:5d} rows")
        
    print(f"Total raw hit rows: {total_hit_rows}")
    print(f"Appended new unique rows: {len(new_rows)}")
    
    if new_rows:
        with open(MASTER_POOL, "a", encoding="utf-8", newline="\n") as f:
            for nr in new_rows:
                f.write(nr + "\n")
                
    final_count = initial_count + len(new_rows)
    print(f"Final master_pool.txt count: {final_count}")

if __name__ == "__main__":
    main()
