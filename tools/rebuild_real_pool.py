#!/usr/bin/env python3
"""
tools/rebuild_real_pool.py - Full strict pass to rebuild real_pool.txt with only clean passes.
- No two-strike suspect buffer.
- Keeps ONLY clean passes in real_pool.txt.
- Moves failures to cache/pool_dead.txt.
- Concurrency: 500, Timeout: 8.0s.
"""
import os
import sys
import ssl
import time
import socket
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT = r"D:\DEpinFarm"
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
TEMP_POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt.tmp")
DEAD_FILE = os.path.join(REPO_ROOT, "cache", "pool_dead.txt")
SUSPECT_FILE = os.path.join(REPO_ROOT, "cache", "pool_suspect.txt")

CONCURRENCY = 500
TIMEOUT = 8.0
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

def verify_proxy_worker(raw):
    line = raw.strip()
    if not line:
        return None, False, "EMPTY"
    endpoint = line.split("\t")[0].split()[0]
    try:
        ip, port_str = endpoint.split(":")
        port = int(port_str)
    except Exception:
        return line, False, "BAD_FORMAT"

    s = None
    try:
        s = socket.create_connection((ip, port), timeout=TIMEOUT)
    except Exception:
        return line, False, "CONNECT_FAIL"

    if sync_tls_handshake(s, "speed.cloudflare.com", timeout=TIMEOUT):
        return line, True, "speed.cloudflare.com"

    for target in ["www.google.com", "one.one.one.one"]:
        if sync_probe_target(ip, port, target, timeout=TIMEOUT):
            return line, True, target

    return line, False, "FAIL_TLS_OR_CONNECT"

def rebuild_pool():
    if not os.path.exists(POOL_FILE):
        print(f"Error: {POOL_FILE} does not exist.")
        return

    with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as pf:
        candidates = [line.strip() for line in pf if line.strip()]

    total = len(candidates)
    print(f"Starting strict rebuild on {total} pool members (Concurrency: {CONCURRENCY}, Timeout: {TIMEOUT}s)...")
    t0 = time.time()

    survivors = []
    dead = []
    tested = 0
    last_print = time.time()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = {executor.submit(verify_proxy_worker, raw): raw for raw in candidates}
        for fut in as_completed(futures):
            tested += 1
            raw = futures[fut]
            try:
                item, ok, reason = fut.result()
            except Exception:
                item, ok, reason = raw, False, "EXCEPTION"

            if ok and item:
                survivors.append(item)
            else:
                if item:
                    dead.append(f"[{ts}] {item}\tREASON:{reason}\tCONSECUTIVE_FAIL:2")

            now = time.time()
            if tested % 2000 == 0 or (now - last_print) >= 10:
                last_print = now
                rate = (len(survivors) / tested * 100) if tested > 0 else 0.0
                elapsed = now - t0
                print(f"[{time.strftime('%H:%M:%S')}] Tested: {tested}/{total} ({tested/total*100:.1f}%) | "
                      f"Survived: {len(survivors)} ({rate:.1f}%) | Died: {len(dead)} | Elapsed: {elapsed:.0f}s", flush=True)

    survived_cnt = len(survivors)
    died_cnt = len(dead)
    survival_pct = (survived_cnt / total * 100) if total > 0 else 0.0
    elapsed_total = time.time() - t0

    print("=" * 80)
    print(f"REBUILD PASS COMPLETE in {elapsed_total:.1f}s")
    print(f"  Tested:           {total}")
    print(f"  Clean Survivors:  {survived_cnt} ({survival_pct:.1f}%)")
    print(f"  Died:             {died_cnt}")
    print("=" * 80)

    # 1. Atomic write survivors to real_pool.txt
    os.makedirs(os.path.dirname(TEMP_POOL_FILE), exist_ok=True)
    with open(TEMP_POOL_FILE, "w", encoding="utf-8") as tf:
        for s in survivors:
            tf.write(s + "\n")
        tf.flush()
        os.fsync(tf.fileno())
    os.replace(TEMP_POOL_FILE, POOL_FILE)

    # 2. Append dead to cache/pool_dead.txt
    if dead:
        os.makedirs(os.path.dirname(DEAD_FILE), exist_ok=True)
        with open(DEAD_FILE, "a", encoding="utf-8") as df:
            for d in dead:
                df.write(d + "\n")

    # 3. Clear suspects file since all pool members are clean passes
    if os.path.exists(SUSPECT_FILE):
        with open(SUSPECT_FILE, "w", encoding="utf-8") as sf:
            pass

    print(f"Successfully rebuilt {POOL_FILE} with {survived_cnt} clean proxies.")
    return total, survived_cnt, died_cnt, survival_pct

if __name__ == "__main__":
    rebuild_pool()
