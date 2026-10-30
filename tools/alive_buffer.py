#!/usr/bin/env python3
"""
tools/alive_buffer.py
Strict-verifies proxy candidates from real_pool.txt and maintains a verified alive buffer.
- Probe: HTTP CONNECT, HTTP 200, 0x16 ServerHello check, system CA chain verification, 8s timeout.
- Priority: FAST and MED tiers first, then SLOW, then other.
- Output: cache/alive_buffer.txt
- Refills continuously and stops when buffer depth holds 500.
- Removes entries once consumed.
"""
import os
import sys
import time
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
BUFFER_FILE = os.path.join(REPO_ROOT, "cache", "alive_buffer.txt")
MAX_BUFFER = 500

SSL_CTX = ssl.create_default_context()
PROBE_TARGETS = ["speed.cloudflare.com", "one.one.one.one"]

def strict_probe_endpoint(endpoint, timeout=8.0):
    """
    Strict-verifies candidate:
    1) TCP connection to proxy (timeout=8s)
    2) HTTP CONNECT to target:443
    3) Response boundary and status HTTP 200
    4) 0x16 TLS ServerHello record check
    5) Full TLS handshake validated against system CA chain
    """
    try:
        ip, port_str = endpoint.strip().split(":")
        port = int(port_str)
    except Exception:
        return endpoint, False, None

    for target in PROBE_TARGETS:
        s = None
        try:
            s = socket.create_connection((ip, port), timeout=timeout)
            s.settimeout(timeout)
            req = f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n".encode()
            s.sendall(req)

            resp = b""
            while b"\r\n\r\n" not in resp:
                chunk = s.recv(512)
                if not chunk or len(resp) > 2048:
                    break
                resp += chunk

            if b"\r\n\r\n" not in resp:
                s.close()
                continue

            first_line = resp.split(b"\r\n")[0]
            if not (b" 200" in first_line or b"HTTP/1.1 200" in first_line or b"HTTP/1.0 200" in first_line):
                s.close()
                continue

            parts = resp.split(b"\r\n\r\n", 1)
            trailing = parts[1] if len(parts) > 1 else b""
            if trailing and trailing[:1] != b"\x16":
                s.close()
                continue

            ss = SSL_CTX.wrap_socket(s, server_hostname=target)
            ss.settimeout(timeout)
            ss.do_handshake()
            cert = ss.getpeercert()
            ss.close()
            if cert:
                return endpoint, True, target
        except Exception:
            if s:
                try:
                    s.close()
                except Exception:
                    pass
    return endpoint, False, None

def load_buffer():
    if not os.path.exists(BUFFER_FILE):
        return []
    with open(BUFFER_FILE, "r", encoding="utf-8", errors="ignore") as f:
        return [l.strip() for l in f if l.strip()]

def append_to_buffer(endpoint):
    os.makedirs(os.path.dirname(BUFFER_FILE), exist_ok=True)
    with open(BUFFER_FILE, "a", encoding="utf-8") as f:
        f.write(endpoint + "\n")
        f.flush()

def pop_from_buffer(count=1):
    """
    Consumes count entries from cache/alive_buffer.txt and removes them.
    Returns list of consumed endpoints.
    """
    if not os.path.exists(BUFFER_FILE):
        return []
    with open(BUFFER_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = [l.strip() for l in f if l.strip()]
    if not lines:
        return []
    consumed = lines[:count]
    remaining = lines[count:]
    with open(BUFFER_FILE, "w", encoding="utf-8") as f:
        for l in remaining:
            f.write(l + "\n")
    return consumed

def load_sorted_pool_candidates():
    if not os.path.exists(REAL_POOL_FILE):
        return []
    with open(REAL_POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = [l.strip() for l in f if l.strip()]

    candidates = []
    seen = set()
    for l in lines:
        parts = l.split("\t")
        ep = parts[0].strip()
        if not ep or ":" not in ep or ep in seen:
            continue
        seen.add(ep)

        # Tier detection: FAST (0), MED (1), SLOW (2), other (3)
        tier = 3
        lat = 999999
        for c_idx, p in enumerate(parts):
            if p == "FAST":
                tier = 0
                if c_idx > 0 and parts[c_idx-1].isdigit():
                    lat = int(parts[c_idx-1])
                break
            elif p == "MED":
                tier = 1
                if c_idx > 0 and parts[c_idx-1].isdigit():
                    lat = int(parts[c_idx-1])
                break
            elif p == "SLOW":
                tier = 2
                if c_idx > 0 and parts[c_idx-1].isdigit():
                    lat = int(parts[c_idx-1])
                break

        candidates.append((tier, lat, ep))

    candidates.sort(key=lambda x: (x[0], x[1]))
    return [c[2] for c in candidates]

def run_buffer_refill_loop():
    print(f"[{time.strftime('%H:%M:%S')}] Alive Buffer Daemon initialized (Target: {MAX_BUFFER}).", flush=True)
    all_candidates = load_sorted_pool_candidates()
    print(f"[{time.strftime('%H:%M:%S')}] Loaded {len(all_candidates)} unique candidates from real_pool.txt (FAST/MED first).", flush=True)

    cand_idx = 0
    buffer_ready_printed = False

    while True:
        buf = load_buffer()
        current_depth = len(buf)

        if current_depth >= MAX_BUFFER:
            if not buffer_ready_printed:
                print(f"[{time.strftime('%H:%M:%S')}] Buffer reached {current_depth}/{MAX_BUFFER}. BUFFER_READY", flush=True)
                buffer_ready_printed = True
            time.sleep(10)
            continue

        buffer_ready_printed = False
        needed = MAX_BUFFER - current_depth
        existing_set = set(buf)

        # Batch up to 100 at a time
        batch = []
        while len(batch) < min(needed * 2, 100) and cand_idx < len(all_candidates):
            c = all_candidates[cand_idx]
            cand_idx += 1
            if c not in existing_set:
                batch.append(c)

        if cand_idx >= len(all_candidates):
            cand_idx = 0
            if not batch:
                time.sleep(10)
                continue

        with ThreadPoolExecutor(max_workers=60) as ex:
            futures = [ex.submit(strict_probe_endpoint, ep) for ep in batch]
            for fut in as_completed(futures):
                try:
                    ep, ok, tgt = fut.result()
                    if ok:
                        buf = load_buffer()
                        if len(buf) < MAX_BUFFER and ep not in set(buf):
                            append_to_buffer(ep)
                            current_depth = len(buf) + 1
                            if current_depth >= MAX_BUFFER:
                                break
                except Exception:
                    pass

        buf = load_buffer()
        current_depth = len(buf)
        print(f"[{time.strftime('%H:%M:%S')}] Buffer depth: {current_depth}/{MAX_BUFFER}", flush=True)
        if current_depth >= MAX_BUFFER:
            print("BUFFER_READY", flush=True)
            buffer_ready_printed = True

        time.sleep(1)

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--depth":
        buf = load_buffer()
        print(f"BUFFER_DEPTH: {len(buf)}")
        return
    elif len(sys.argv) > 1 and sys.argv[1] == "--pop":
        cnt = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        popped = pop_from_buffer(cnt)
        for p in popped:
            print(p)
        return
    else:
        run_buffer_refill_loop()

if __name__ == "__main__":
    main()
