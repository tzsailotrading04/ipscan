#!/usr/bin/env python3
r"""
DEpin Farm Recover from Part Files (v98.180)
STEP 1: Count lines in verified_alive_part_*.txt, overlap in real_pool.txt, and in harvest_seen_set.txt but not pool.
STEP 2: Write recoverable set to cache/recover_queue.txt (deduped, private ranges dropped). Print wc -l.
STEP 3: Strict verifier against recover_queue.txt at 400 concurrency, 8s timeout, survivors appended to real_pool.txt.
        Progress every 2,000: tested, survived, rate. Final: tested, survived, rate, new pool size.
STEP 4: Print pool size, dead size, and recoverable set remaining.
"""
import os
import sys
import glob
import time
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT = r"D:\DEpinFarm"
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
SEEN_FILE = os.path.join(REPO_ROOT, "cache", "harvest_seen_set.txt")
DEAD_FILE = os.path.join(REPO_ROOT, "cache", "pool_dead.txt")
QUEUE_FILE = os.path.join(REPO_ROOT, "cache", "recover_queue.txt")

TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
CONCURRENCY = 400
TIMEOUT = 8.0
SSL_CTX = ssl.create_default_context()

def is_valid_public_ipv4(ip_str, port_int):
    if not (1 <= port_int <= 65535):
        return False
    parts = ip_str.split('.')
    if len(parts) != 4:
        return False
    try:
        o1, o2, o3, o4 = (int(p) for p in parts)
    except ValueError:
        return False
    if not (0 <= o1 <= 255 and 0 <= o2 <= 255 and 0 <= o3 <= 255 and 0 <= o4 <= 255):
        return False
    if o1 in (0, 10, 127) or o1 >= 224:
        return False
    if o1 == 192 and o2 == 168:
        return False
    if o1 == 172 and (16 <= o2 <= 31):
        return False
    if o1 == 169 and o2 == 254:
        return False
    if o1 == 100 and (64 <= o2 <= 127):
        return False
    return True

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

def verify_candidate(entry):
    raw = entry.strip()
    if not raw:
        return None, False, "EMPTY", ""
    endpoint = raw.split("\t")[0].split()[0]
    try:
        ip, port_str = endpoint.split(":")
        port = int(port_str)
    except Exception:
        return raw, False, "BAD_FORMAT", ""

    # Primary target probe
    s = None
    try:
        s = socket.create_connection((ip, port), timeout=TIMEOUT)
    except Exception:
        return raw, False, "CONNECT_FAIL", ""

    if sync_tls_handshake(s, "speed.cloudflare.com", timeout=TIMEOUT):
        return raw, True, "speed.cloudflare.com", endpoint

    # Fallback targets
    for target in ["www.google.com", "one.one.one.one"]:
        if sync_probe_target(ip, port, target, timeout=TIMEOUT):
            return raw, True, target, endpoint

    return raw, False, "TLS_FAIL", ""

def count_lines(filepath):
    if not os.path.exists(filepath):
        return 0
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0

def step1_and_step2():
    print("=" * 80)
    print("STEP 1 - COUNT WHAT IS ACTUALLY THERE AND UNREACHED")
    print("=" * 80)

    part_files = glob.glob(os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive_part_*.txt"))
    pool_endpoints = set()
    if os.path.exists(POOL_FILE):
        with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                ep = line.strip().split()[0] if line.strip() else ""
                if ep: pool_endpoints.add(ep)

    seen_endpoints = set()
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                ep = line.strip().split()[0] if line.strip() else ""
                if ep: seen_endpoints.add(ep)

    total_lines = 0
    part_entries = {}
    for pf in part_files:
        try:
            with open(pf, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    total_lines += 1
                    raw = line.strip()
                    if not raw: continue
                    ep = raw.split()[0]
                    if ep not in part_entries:
                        part_entries[ep] = raw
        except Exception:
            pass

    overlap_count = sum(1 for ep in part_entries if ep in pool_endpoints)
    # in harvest_seen_set.txt but not in pool
    recoverable_eps = [ep for ep in part_entries if ep in seen_endpoints and ep not in pool_endpoints]

    print(f"Total lines across verified_alive_part_*.txt: {total_lines:,}")
    print(f"Endpoints already in real_pool.txt (overlap): {overlap_count:,}")
    print(f"Endpoints already in harvest_seen_set.txt but not in pool: {len(recoverable_eps):,}")
    print(f"The recoverable set: {len(recoverable_eps):,}")

    print("\n" + "=" * 80)
    print("STEP 2 - WRITE THE RECOVERABLE SET TO cache/recover_queue.txt")
    print("=" * 80)

    # Filter private / bogon ranges
    valid_recoverable = []
    for ep in recoverable_eps:
        try:
            ip, port_str = ep.split(":")
            if is_valid_public_ipv4(ip, int(port_str)):
                valid_recoverable.append(part_entries[ep])
        except Exception:
            pass

    os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)
    with open(QUEUE_FILE, "w", encoding="utf-8") as qf:
        for entry in valid_recoverable:
            qf.write(entry + "\n")

    wc_l = count_lines(QUEUE_FILE)
    print(f"cache/recover_queue.txt written with {wc_l:,} lines (wc -l = {wc_l}).")
    return valid_recoverable

def step3_and_step4(candidates):
    print("\n" + "=" * 80)
    print(f"STEP 3 - RUN STRICT VERIFIER (CONCURRENCY={CONCURRENCY}, TIMEOUT={TIMEOUT}s)")
    print("=" * 80)
    print(f"Starting verification pass on {len(candidates):,} candidates...")
    sys.stdout.flush()

    total_to_test = len(candidates)
    tested_count = 0
    survived_count = 0
    t_start = time.time()

    pool_fp = open(POOL_FILE, "a", encoding="utf-8")

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        future_map = {executor.submit(verify_candidate, c): c for c in candidates}
        for future in as_completed(future_map):
            tested_count += 1
            try:
                raw, ok, reason, endpoint = future.result()
                if ok:
                    survived_count += 1
                    # Format entry with target for real_pool.txt
                    parts = raw.split("\t")
                    if len(parts) >= 2:
                        pool_entry = f"{parts[0]}\t{reason}\t" + "\t".join(parts[2:]) if len(parts) > 2 else f"{parts[0]}\t{reason}\tRECOVERED\t0\tUNKNOWN"
                    else:
                        pool_entry = f"{raw}\t{reason}\tRECOVERED\t0\tUNKNOWN"
                    pool_fp.write(pool_entry + "\n")
                    pool_fp.flush()
            except Exception:
                pass

            if tested_count % 2000 == 0:
                rate = (survived_count / tested_count) * 100.0
                dt = time.time() - t_start
                rate_s = tested_count / max(0.1, dt)
                print(f"[PROGRESS] tested={tested_count:,} | survived={survived_count:,} | rate={rate:.2f}% | speed={rate_s:.1f} req/s", flush=True)

    pool_fp.close()
    final_rate = (survived_count / total_to_test * 100.0) if total_to_test > 0 else 0.0
    final_pool_size = count_lines(POOL_FILE)

    print("\n--- FINAL VERIFICATION RESULTS ---")
    print(f"Tested:        {tested_count:,}")
    print(f"Survived:      {survived_count:,}")
    print(f"Survival Rate: {final_rate:.2f}%")
    print(f"New Pool Size: {final_pool_size:,}")

    print("\n" + "=" * 80)
    print("STEP 4 - FINAL STATUS")
    print("=" * 80)
    pool_sz = count_lines(POOL_FILE)
    dead_sz = count_lines(DEAD_FILE)
    rec_remaining = total_to_test - tested_count
    print(f"real_pool.txt size:         {pool_sz:,}")
    print(f"pool_dead.txt size:         {dead_sz:,}")
    print(f"Recoverable set remaining:  {rec_remaining:,}")

def main():
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, "r", encoding="utf-8", errors="ignore") as f:
            candidates = [l.strip() for l in f if l.strip()]
        print(f"Loaded {len(candidates):,} candidates from {QUEUE_FILE}")
    else:
        candidates = step1_and_step2()
    step3_and_step4(candidates)

if __name__ == "__main__":
    main()
