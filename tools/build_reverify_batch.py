#!/usr/bin/env python3
"""
tools/build_reverify_batch.py
Builds the queue batch from cache/pool_dead.txt and app_pool.txt:
- Strips to plain ip:port
- Dedupes
- Drops anything already in real_pool.txt
- Drops private, loopback, reserved, multicast, link-local, and carrier-grade NAT ranges
- Writes to ip/harvest/queue/q_region_<ts>.txt
- Commits and pushes to git origin main for Kaggle shard pickup
"""
import os
import sys
import time
import ipaddress
import subprocess

REPO_ROOT = r"D:\DEpinFarm"
DEAD_FILE = os.path.join(REPO_ROOT, "cache", "pool_dead.txt")
APP_POOL_FILES = [
    os.path.join(REPO_ROOT, "app_pool.txt"),
    os.path.join(REPO_ROOT, "ip", "harvest", "app_pool.txt")
]
REAL_POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
QUEUE_DIR = os.path.join(REPO_ROOT, "ip", "harvest", "queue")

def is_valid_public_endpoint(ep):
    try:
        parts = ep.split(":")
        if len(parts) != 2:
            return False
        ip_str, port_str = parts[0].strip(), parts[1].strip()
        port = int(port_str)
        if not (1 <= port <= 65535):
            return False
        ip_obj = ipaddress.ip_address(ip_str)
        if ip_obj.version != 4:
            return False
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_multicast:
            return False
        # Carrier-grade NAT (100.64.0.0/10)
        if ip_str.startswith("100."):
            second_octet = int(ip_str.split(".")[1])
            if 64 <= second_octet <= 127:
                return False
        return True
    except Exception:
        return False

def main():
    os.makedirs(QUEUE_DIR, exist_ok=True)
    ts = int(time.time())
    out_filename = f"q_region_{ts}.txt"
    out_path = os.path.join(QUEUE_DIR, out_filename)

    # 1. Load real_pool.txt
    real_pool = set()
    if os.path.exists(REAL_POOL_FILE):
        with open(REAL_POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line:
                    ep = line.split("\t")[0].split()[0].strip()
                    if ":" in ep:
                        real_pool.add(ep)
    print(f"Loaded {len(real_pool)} existing entries in real_pool.txt.")

    raw_candidates = set()
    dead_lines = 0

    # 2. Source 1: cache/pool_dead.txt
    if os.path.exists(DEAD_FILE):
        with open(DEAD_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                dead_lines += 1
                for tok in line.split():
                    if ":" in tok and not tok.startswith("["):
                        ep = tok.split("\t")[0].strip()
                        if is_valid_public_endpoint(ep):
                            raw_candidates.add(ep)
                            break
    print(f"Read {dead_lines} lines from cache/pool_dead.txt -> candidates collected so far: {len(raw_candidates)}")

    # 3. Source 2: app_pool.txt
    app_lines = 0
    seen_app_files = set()
    for ap in APP_POOL_FILES:
        if os.path.exists(ap) and ap not in seen_app_files:
            seen_app_files.add(ap)
            with open(ap, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    app_lines += 1
                    for tok in line.split():
                        if ":" in tok:
                            ep = tok.split("\t")[0].strip()
                            if is_valid_public_endpoint(ep):
                                raw_candidates.add(ep)
                                break
    print(f"Read {app_lines} lines from app_pool.txt -> total unique valid candidates: {len(raw_candidates)}")

    # 4. Filter against real_pool
    batch = sorted([ep for ep in raw_candidates if ep not in real_pool])
    print(f"Total candidates after deduplication and dropping real_pool & private ranges: {len(batch)}")

    # 5. Write to output queue file
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        for ep in batch:
            f.write(ep + "\n")
    print(f"Successfully wrote {len(batch)} entries to {out_path}")

    # 6. Commit and push to git
    try:
        subprocess.run(["git", "-C", REPO_ROOT, "add", os.path.relpath(out_path, REPO_ROOT)], check=True)
        c_res = subprocess.run(["git", "-C", REPO_ROOT, "commit", "-m", f"Add {out_filename} ({len(batch)} rejected candidates for re-verification)"], capture_output=True, text=True)
        print("Git commit:", c_res.stdout.strip())
        p_res = subprocess.run(["git", "-C", REPO_ROOT, "push", "origin", "main"], capture_output=True, text=True)
        print("Git push:", p_res.stdout.strip() if p_res.stdout else p_res.stderr.strip())
    except Exception as e:
        print(f"Git commit/push warning: {e}")

    print(f"\nBATCH_FILE: {out_filename}")
    print(f"BATCH_COUNT: {len(batch)}")

if __name__ == "__main__":
    main()
