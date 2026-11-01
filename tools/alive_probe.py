#!/usr/bin/env python3
"""
tools/alive_probe.py - Sample and probe endpoints from real_pool.txt
Strict CONNECT + 0x16 TLS check identical to kaggle/cl_shodan_00/run.py
Concurrency 100, 5s timeout, multiple targets.
"""
import os
import sys
import ssl
import socket
import random
import math
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT = r"D:\DEpinFarm"
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
SSL_CTX = ssl.create_default_context()

SAMPLE_SIZE = 400
CONCURRENCY = 100
TIMEOUT = 5.0

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
        parts = resp.split(b"\r\n\r\n", 1)
        trailing = parts[1] if len(parts) > 1 else b""
        if trailing and trailing[:1] != b"\x16":
            return False
        ss = SSL_CTX.wrap_socket(sock, server_hostname=target)
        ss.settimeout(timeout)
        ss.do_handshake()
        cert = ss.getpeercert()
        if not cert:
            ss.close()
            return False
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

def probe_endpoint(item):
    ip, port = item
    # Primary target probe with connected socket
    s = None
    try:
        s = socket.create_connection((ip, port), timeout=TIMEOUT)
        if sync_tls_handshake(s, TARGETS[0], timeout=TIMEOUT):
            return ip, port, True, TARGETS[0]
    except Exception:
        if s:
            try:
                s.close()
            except Exception:
                pass

    # Fallback targets
    for t in TARGETS[1:]:
        if sync_probe_target(ip, port, t, timeout=TIMEOUT):
            return ip, port, True, t

    return ip, port, False, None

def main():
    if not os.path.exists(POOL_FILE):
        print(f"Error: Pool file not found at {POOL_FILE}")
        sys.exit(1)

    print(f"Reading {POOL_FILE}...")
    with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = [line.strip() for line in f if line.strip()]

    pool_total = len(lines)
    print(f"Total pool size: {pool_total:,} endpoints")

    if pool_total == 0:
        print("Pool is empty.")
        return

    n = min(SAMPLE_SIZE, pool_total)
    sample_lines = random.sample(lines, n)

    endpoints = []
    for line in sample_lines:
        ep = line.split()[0].split("\t")[0]
        if ":" in ep:
            parts = ep.rsplit(":", 1)
            try:
                endpoints.append((parts[0], int(parts[1])))
            except ValueError:
                pass

    print(f"Probing {len(endpoints)} random endpoints (concurrency={CONCURRENCY}, timeout={TIMEOUT}s)...")

    alive_count = 0
    tested = 0
    target_hits = {t: 0 for t in TARGETS}

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = {executor.submit(probe_endpoint, ep): ep for ep in endpoints}
        for future in as_completed(futures):
            ip, port, is_alive, target = future.result()
            tested += 1
            if is_alive:
                alive_count += 1
                target_hits[target] += 1
            if tested % 50 == 0 or tested == len(endpoints):
                pct_so_far = (alive_count / tested) * 100
                print(f"  Progress: {tested}/{len(endpoints)} tested, {alive_count} alive ({pct_so_far:.2f}%)", flush=True)

    # Statistical calculations
    p = alive_count / n
    # Finite Population Correction (FPC)
    fpc = math.sqrt((pool_total - n) / (pool_total - 1)) if pool_total > 1 else 1.0
    se = math.sqrt((p * (1 - p)) / n) * fpc
    z = 1.95996  # 95% critical value

    margin_pct = z * se * 100
    p_low = max(0.0, p - z * se)
    p_high = min(1.0, p + z * se)

    scaled_est = int(round(pool_total * p))
    ci_low = int(round(pool_total * p_low))
    ci_high = int(round(pool_total * p_high))

    print("\n" + "=" * 60)
    print("PROBE RESULTS & STATISTICAL ESTIMATE")
    print("=" * 60)
    print(f"Pool Total             : {pool_total:,}")
    print(f"Sample Tested          : {n}")
    print(f"Alive in Sample        : {alive_count}")
    print(f"Alive Percentage       : {p * 100:.2f}% (±{margin_pct:.2f}%)")
    print(f"95% CI for Proportion  : [{p_low * 100:.2f}%, {p_high * 100:.2f}%]")
    print(f"Scaled Alive Estimate  : {scaled_est:,} endpoints")
    print(f"95% CI for Alive Total : [{ci_low:,}, {ci_high:,}] endpoints")
    print("-" * 60)
    print("Alive hits by target   : " + ", ".join(f"{t}: {c}" for t, c in target_hits.items()))
    print("=" * 60)

if __name__ == "__main__":
    main()
