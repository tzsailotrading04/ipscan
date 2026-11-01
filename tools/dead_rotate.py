#!/usr/bin/env python3
"""
tools/dead_rotate.py
Dead pool rotation manager:
Takes 50,000 lines per hour from the full 240,000 dead entries on a 5-hour cycle
instead of 10,000 on 24.
- Reads cache/pool_dead.txt
- Extracts valid public endpoints
- Drops any endpoint already in ip/harvest/real_pool.txt
- Writes batch to ip/harvest/queue/ as q_a4_dead_<ts>_<nn>.txt
- Tracks rotating cursor in work/dead_rotate_state.json
- Runs once with --once or continuously on a 1-hour interval
"""

import os
import sys
import time
import json
import re
import ipaddress

REPO_ROOT = r"D:\DEpinFarm" if os.path.exists(r"D:\DEpinFarm") else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEAD_FILE = os.path.join(REPO_ROOT, "cache", "pool_dead.txt")
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
QUEUE_DIR = os.path.join(REPO_ROOT, "ip", "harvest", "queue")
WORK_DIR = os.path.join(REPO_ROOT, "work")
STATE_FILE = os.path.join(WORK_DIR, "dead_rotate_state.json")

BATCH_SIZE = 50000
CYCLE_HOURS = 5

EP_REGEX = re.compile(r'\b((?:[0-9]{1,3}\.){3}[0-9]{1,3}:\d+)\b')

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
        if ip_str.startswith("100."):
            second_octet = int(ip_str.split(".")[1])
            if 64 <= second_octet <= 127:
                return False
        return True
    except Exception:
        return False

def load_real_pool():
    pool_eps = set()
    if os.path.exists(POOL_FILE):
        with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                l = line.strip()
                if l:
                    ep = l.split("\t")[0].split()[0].strip()
                    if ":" in ep:
                        pool_eps.add(ep)
    return pool_eps

def load_dead_entries():
    if not os.path.exists(DEAD_FILE):
        return []
    entries = []
    seen = set()
    with open(DEAD_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = EP_REGEX.search(line)
            if m:
                ep = m.group(1)
                if ep not in seen and is_valid_public_endpoint(ep):
                    seen.add(ep)
                    entries.append(ep)
    return entries

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"cursor": 0, "cycle_count": 0, "last_ts": 0}

def save_state(state):
    os.makedirs(WORK_DIR, exist_ok=True)
    try:
        with open(STATE_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(STATE_FILE + ".tmp", STATE_FILE)
    except Exception:
        pass

def rotate_dead_batch():
    os.makedirs(QUEUE_DIR, exist_ok=True)
    os.makedirs(WORK_DIR, exist_ok=True)

    dead_entries = load_dead_entries()
    total_dead = len(dead_entries)
    if total_dead == 0:
        print("[DEAD_ROTATE] No dead entries found in cache/pool_dead.txt.")
        return

    real_pool = load_real_pool()
    state = load_state()
    cursor = state.get("cursor", 0)
    cycle_count = state.get("cycle_count", 0)

    if cursor >= total_dead:
        cursor = 0
        cycle_count += 1

    end_idx = cursor + BATCH_SIZE
    if end_idx <= total_dead:
        slice_entries = dead_entries[cursor:end_idx]
        next_cursor = end_idx if end_idx < total_dead else 0
    else:
        # Wrap around to start of file
        slice_entries = dead_entries[cursor:] + dead_entries[:end_idx - total_dead]
        next_cursor = end_idx - total_dead
        cycle_count += 1

    # Filter out entries already in real_pool
    batch = [ep for ep in slice_entries if ep not in real_pool]

    ts = int(time.time())
    file_tag = (cursor // BATCH_SIZE) + 1
    out_filename = f"q_a4_dead_{ts}_{file_tag:02d}.txt"
    out_path = os.path.join(QUEUE_DIR, out_filename)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(batch) + "\n")

    state["cursor"] = next_cursor
    state["cycle_count"] = cycle_count
    state["last_ts"] = ts
    save_state(state)

    print("=" * 60)
    print(f"[DEAD_ROTATE] 50,000 lines/hr cycle (5-hour full 240k rotation)")
    print(f"  Total dead entries: {total_dead:,}")
    print(f"  Slice taken: [{cursor:,} : {cursor + len(slice_entries):,}] ({len(slice_entries):,} entries)")
    print(f"  Filtered (in real_pool): {len(slice_entries) - len(batch):,}")
    print(f"  Written to queue: {len(batch):,} -> {out_filename}")
    print(f"  Next cursor: {next_cursor:,} (Cycle #{cycle_count})")
    print("=" * 60)

def main():
    if "--once" in sys.argv:
        rotate_dead_batch()
        return

    print("[DEAD_ROTATE] Starting hourly dead rotation daemon (50,000 lines/hr on 5h cycle)...")
    rotate_dead_batch()
    while True:
        time.sleep(3600)
        try:
            rotate_dead_batch()
        except Exception as e:
            print(f"[ERROR] Exception in dead rotate cycle: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
