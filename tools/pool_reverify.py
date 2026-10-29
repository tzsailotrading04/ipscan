#!/usr/bin/env python3
"""
Pool Reverify Daemon - Strict TLS Handshake & CA Chain Verification (v3)
- Matches Kaggle Shard Probe exactly:
    - Plain socket CONNECT
    - Expect HTTP 200
    - SSL_CTX.wrap_socket(s, server_hostname=target)
    - ss.do_handshake() & ss.getpeercert()
- CONCURRENCY: 150 (ThreadPoolExecutor)
- TIMEOUT: 8.0s
- Consecutive failure counter:
    - Fails 1st pass: marked "suspect", stored in cache/pool_suspect.txt, STAYS in pool
    - Fails 2nd consecutive pass: removed from pool, appended to cache/pool_dead.txt
- Atomic update: real_pool.txt.tmp -> real_pool.txt
- Loops every 1200s
"""
import os
import sys
import ssl
import time
import socket
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT = r"D:\DEpinFarm"
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
TEMP_POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt.tmp")
DEAD_FILE = os.path.join(REPO_ROOT, "cache", "pool_dead.txt")
SUSPECT_FILE = os.path.join(REPO_ROOT, "cache", "pool_suspect.txt")

TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
CONCURRENCY = 150
TIMEOUT = 8.0

SSL_CTX = ssl.create_default_context()

def load_suspect_set():
    suspects = set()
    if os.path.exists(SUSPECT_FILE):
        try:
            with open(SUSPECT_FILE, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    raw = line.strip()
                    if raw:
                        endpoint = raw.split("\t")[0].split()[0]
                        suspects.add(endpoint)
        except Exception:
            pass
    return suspects

def save_suspect_set(suspect_entries):
    os.makedirs(os.path.dirname(SUSPECT_FILE), exist_ok=True)
    with open(SUSPECT_FILE, "w", encoding="utf-8") as f:
        for entry in suspect_entries:
            f.write(entry + "\n")

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

def verify_proxy_worker(entry):
    raw = entry.strip()
    if not raw:
        return None, False, "EMPTY"

    endpoint = raw.split("\t")[0].split()[0]
    try:
        ip, port_str = endpoint.split(":")
        port = int(port_str)
    except Exception:
        return raw, False, "BAD_FORMAT"

    # Test against targets exactly like shard probe
    for target in TARGETS:
        if sync_probe_target(ip, port, target, timeout=TIMEOUT):
            return raw, True, target

    return raw, False, "FAIL_TLS_OR_CONNECT"

def run_verification_pass():
    if not os.path.exists(POOL_FILE):
        print(f"Error: {POOL_FILE} does not exist.")
        return 0, 0, 0, 0, 0.0

    with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
        entries = [line.strip() for line in f if line.strip()]

    tested = len(entries)
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting strict pool reverification pass on {tested} proxies (CONCURRENCY={CONCURRENCY}, TIMEOUT={TIMEOUT}s)...")

    previous_suspects = load_suspect_set()
    print(f"Loaded {len(previous_suspects)} previously suspect proxies from {SUSPECT_FILE}")

    results = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = {executor.submit(verify_proxy_worker, e): e for e in entries}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                e = futures[future]
                results.append((e, False, f"EXC:{exc}"))

    survivors = []
    dead = []
    current_suspects = []
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    for raw, ok, reason in results:
        if raw is None:
            continue
        endpoint = raw.split("\t")[0].split()[0]
        if ok:
            # Passed verification: survives, not suspect
            survivors.append(raw)
        else:
            # Failed verification
            if endpoint in previous_suspects:
                # SECOND consecutive failure: remove from pool and mark dead
                dead.append(f"[{ts}] {raw}\tREASON:{reason}\tCONSECUTIVE_FAIL:2")
            else:
                # FIRST failure: mark as suspect, but KEEP IN POOL
                survivors.append(raw)
                current_suspects.append(raw)

    survived_cnt = len(survivors)
    died_cnt = len(dead)
    suspect_cnt = len(current_suspects)
    survival_pct = (survived_cnt / tested * 100) if tested > 0 else 0.0

    # Atomic write to real_pool.txt.tmp, then rename over real_pool.txt
    os.makedirs(os.path.dirname(TEMP_POOL_FILE), exist_ok=True)
    with open(TEMP_POOL_FILE, "w", encoding="utf-8") as tf:
        for s in survivors:
            tf.write(s + "\n")
        tf.flush()
        os.fsync(tf.fileno())

    # Atomic replacement
    os.replace(TEMP_POOL_FILE, POOL_FILE)

    # Save current suspects for next pass
    save_suspect_set(current_suspects)

    # Append confirmed dead entries to cache/pool_dead.txt
    if dead:
        os.makedirs(os.path.dirname(DEAD_FILE), exist_ok=True)
        with open(DEAD_FILE, "a", encoding="utf-8") as df:
            for d in dead:
                df.write(d + "\n")

    pool_size = survived_cnt
    print(f"PASS RESULT: tested={tested} survived={survived_cnt} died={died_cnt} suspects={suspect_cnt} survival={survival_pct:.1f}% pool_size={pool_size}")
    return tested, survived_cnt, died_cnt, suspect_cnt, survival_pct

def main():
    print("=================================================================")
    print("  POOL REVERIFY DAEMON v3 (EXACT SHARD PROBE, CONCURRENCY 150)")
    print("=================================================================")

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_verification_pass()
        return

    while True:
        try:
            run_verification_pass()
            print(f"Sleeping 1200 seconds until next reverify pass...")
            time.sleep(1200)
        except KeyboardInterrupt:
            print("Stopping pool reverify daemon.")
            break
        except Exception as e:
            print(f"Reverify cycle error: {e}")
            traceback.print_exc()
            time.sleep(30)

if __name__ == "__main__":
    main()
