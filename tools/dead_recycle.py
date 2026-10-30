#!/usr/bin/env python3
"""
tools/dead_recycle.py - Dead Proxy Recycling Engine
- Reads cache/pool_dead.txt
- Takes the 2,000 oldest entries with RETRY count below 2 and not marked RETIRED
- Strict verifies with 200 concurrency, 8s timeout, exact proven probe:
    - Plain TCP CONNECT
    - HTTP 200 verification
    - TLS wrap and handshake to speed.cloudflare.com (fallbacks: google.com, 1.1.1.1)
- Survivors go back into ip/harvest/real_pool.txt; their line in pool_dead.txt is removed
- Failures get RETRY incremented; on failure reaching 2 (third failure overall), marked RETIRED
- Prints per run: scanned, revived, failed, retired_total
- Runs every 6 hours (or once via --once), exits cleanly, never deletes the dead file.
"""
import os
import sys
import ssl
import time
import socket
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT = r"D:\DEpinFarm"
DEAD_FILE = os.path.join(REPO_ROOT, "cache", "pool_dead.txt")
TEMP_DEAD_FILE = os.path.join(REPO_ROOT, "cache", "pool_dead.txt.tmp")
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
LAST_RUN_FILE = os.path.join(REPO_ROOT, "work", "dead_recycle_last_run.txt")

BATCH_SIZE = 2000
CONCURRENCY = 200
TIMEOUT = 8.0
CYCLE_INTERVAL_SEC = 6 * 3600  # 6 hours

SSL_CTX = ssl.create_default_context()

def sync_tls_handshake(sock, target, timeout=TIMEOUT):
    try:
        sock.setblocking(True)
        sock.settimeout(timeout)
        req = f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n".encode()
        sock.sendall(req)
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = sock.recv(512)
            if not chunk:
                return False
            resp += chunk
            if len(resp) > 2048:
                return False
        first_line = resp.split(b"\r\n")[0]
        if not (b" 200" in first_line or b"HTTP/1.1 200" in first_line or b"HTTP/1.0 200" in first_line):
            return False
        ss = SSL_CTX.wrap_socket(sock, server_hostname=target)
        ss.settimeout(timeout)
        ss.do_handshake()
        _ = ss.getpeercert()
        ss.close()
        return True
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        return False

def sync_probe_target(ip, port, target, timeout=TIMEOUT):
    s = None
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        return sync_tls_handshake(s, target, timeout=timeout)
    except Exception:
        if s:
            try:
                s.close()
            except Exception:
                pass
        return False

def verify_dead_worker(candidate):
    idx, endpoint, clean_line, retry_cnt = candidate
    try:
        ip, port_str = endpoint.split(":")
        port = int(port_str)
    except Exception:
        return idx, False, "BAD_FORMAT"

    s = None
    try:
        s = socket.create_connection((ip, port), timeout=TIMEOUT)
    except Exception:
        return idx, False, "CONNECT_FAIL"

    if sync_tls_handshake(s, "speed.cloudflare.com", timeout=TIMEOUT):
        return idx, True, "speed.cloudflare.com"

    for target in ["www.google.com", "one.one.one.one"]:
        if sync_probe_target(ip, port, target, timeout=TIMEOUT):
            return idx, True, target

    return idx, False, "FAIL_TLS_OR_CONNECT"

def parse_dead_line(line):
    s = line.strip()
    if not s:
        return None
    m = re.match(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] (.*)$", s)
    payload = m.group(1) if m else s
    parts = payload.split("\t")
    endpoint = parts[0].split()[0]

    is_retired = "RETIRED" in parts
    retry_cnt = 0
    clean_parts = []
    for p in parts:
        if p.startswith("RETRY:"):
            try:
                retry_cnt = int(p.split(":")[1])
            except Exception:
                pass
        elif p.startswith("REASON:") or p.startswith("CONSECUTIVE_FAIL:") or p == "RETIRED":
            continue
        else:
            clean_parts.append(p)
    clean_line = "\t".join(clean_parts)
    return endpoint, retry_cnt, is_retired, clean_line

def run_cycle():
    if not os.path.exists(DEAD_FILE):
        print(f"Error: {DEAD_FILE} does not exist.")
        return 0, 0, 0, 0

    with open(DEAD_FILE, "r", encoding="utf-8", errors="ignore") as f:
        all_lines = f.readlines()

    candidates = []  # list of (index, endpoint, clean_line, retry_cnt)
    candidate_indices = set()

    for i, line in enumerate(all_lines):
        parsed = parse_dead_line(line)
        if not parsed:
            continue
        endpoint, retry_cnt, is_retired, clean_line = parsed
        if retry_cnt < 2 and not is_retired:
            candidates.append((i, endpoint, clean_line, retry_cnt))
            candidate_indices.add(i)
            if len(candidates) >= BATCH_SIZE:
                break

    scanned = len(candidates)
    if scanned == 0:
        retired_total = sum(1 for l in all_lines if "RETIRED" in l)
        print(f"scanned={scanned} revived=0 failed=0 retired_total={retired_total}")
        return 0, 0, 0, retired_total

    # Run strict verification
    revived_items = []     # (clean_line)
    updated_failures = {}  # index -> new_line
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = {executor.submit(verify_dead_worker, c): c for c in candidates}
        for fut in as_completed(futures):
            c = futures[fut]
            idx, endpoint, clean_line, retry_cnt = c
            try:
                _, ok, reason = fut.result()
            except Exception:
                ok, reason = False, "EXCEPTION"

            if ok:
                revived_items.append(clean_line)
            else:
                new_retry = retry_cnt + 1
                if new_retry >= 2:
                    new_line = f"[{ts}] {clean_line}\tREASON:{reason}\tCONSECUTIVE_FAIL:2\tRETRY:{new_retry}\tRETIRED\n"
                else:
                    new_line = f"[{ts}] {clean_line}\tREASON:{reason}\tCONSECUTIVE_FAIL:2\tRETRY:{new_retry}\n"
                updated_failures[idx] = new_line

    revived = len(revived_items)
    failed = len(updated_failures)

    # 1. Append survivors to real_pool.txt
    if revived_items:
        existing_pool = set()
        if os.path.exists(POOL_FILE):
            with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as pf:
                for line in pf:
                    ep = line.strip().split("\t")[0].split()[0]
                    if ep:
                        existing_pool.add(ep)

        with open(POOL_FILE, "a", encoding="utf-8") as pf:
            for item in revived_items:
                ep = item.split("\t")[0].split()[0]
                if ep not in existing_pool:
                    pf.write(item + "\n")
                    existing_pool.add(ep)

    # 2. Update cache/pool_dead.txt (survivors removed, failures updated)
    new_dead_lines = []
    retired_total = 0
    for i, line in enumerate(all_lines):
        if i in candidate_indices:
            if i in updated_failures:
                up_line = updated_failures[i]
                new_dead_lines.append(up_line)
                if "RETIRED" in up_line:
                    retired_total += 1
            else:
                # Survivor: line is removed from pool_dead.txt
                pass
        else:
            new_dead_lines.append(line)
            if "RETIRED" in line:
                retired_total += 1

    # Atomic write to temporary file, then replace
    with open(TEMP_DEAD_FILE, "w", encoding="utf-8") as tf:
        tf.writelines(new_dead_lines)
        tf.flush()
        os.fsync(tf.fileno())
    os.replace(TEMP_DEAD_FILE, DEAD_FILE)

    output_str = f"scanned={scanned} revived={revived} failed={failed} retired_total={retired_total}"
    print(output_str)

    # Record last run
    os.makedirs(os.path.dirname(LAST_RUN_FILE), exist_ok=True)
    with open(LAST_RUN_FILE, "w", encoding="utf-8") as lf:
        lf.write(f"[{ts}] {output_str}\n")

    return scanned, revived, failed, retired_total

def main():
    once = ("--once" in sys.argv)
    if once:
        run_cycle()
        sys.exit(0)

    while True:
        try:
            run_cycle()
        except Exception as e:
            print(f"Error in dead_recycle cycle: {e}")
        time.sleep(CYCLE_INTERVAL_SEC)

if __name__ == "__main__":
    main()
