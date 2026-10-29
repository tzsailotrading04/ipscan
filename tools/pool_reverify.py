#!/usr/bin/env python3
"""
Pool Reverify Daemon - Strict TLS Handshake & CA Chain Verification
Verifies every proxy in real_pool.txt via:
  - HTTP CONNECT to speed.cloudflare.com, www.google.com, one.one.one.one
  - Expects HTTP 200
  - TLS ClientHello with SNI
  - Validates ServerHello (0x16) & full TLS handshake against System CA chain
  - Concurrency: 400, Timeout: 3.5s
  - Survivors written atomically via real_pool.txt.tmp -> real_pool.txt
  - Dead entries appended to cache/pool_dead.txt
  - Loops every 1200s
"""
import os
import sys
import ssl
import time
import asyncio
import traceback

REPO_ROOT = r"D:\DEpinFarm"
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
TEMP_POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt.tmp")
DEAD_FILE = os.path.join(REPO_ROOT, "cache", "pool_dead.txt")

TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
CONCURRENCY = 400
TIMEOUT = 3.5

SSL_CTX = ssl.create_default_context()

async def verify_proxy_entry(entry, sem):
    async with sem:
        raw = entry.strip()
        if not raw:
            return None, False, "EMPTY"

        endpoint = raw.split("\t")[0].split()[0]
        try:
            ip, port = endpoint.split(":")
            port = int(port)
        except Exception:
            return raw, False, "BAD_FORMAT"

        # Test against targets
        for target in TARGETS:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, port), timeout=TIMEOUT
                )
                connect_req = f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n".encode()
                writer.write(connect_req)
                await asyncio.wait_for(writer.drain(), timeout=TIMEOUT)

                # Expect HTTP 200
                resp = await asyncio.wait_for(reader.read(1024), timeout=TIMEOUT)
                if not (b" 200 " in resp or b" 200\r\n" in resp or b"HTTP/1.1 200" in resp or b"HTTP/1.0 200" in resp):
                    writer.close()
                    await writer.wait_closed()
                    continue

                # TLS ClientHello with SNI & full handshake validated against System CA
                loop = asyncio.get_running_loop()
                protocol = writer.transport.get_protocol()
                tls_transport = await asyncio.wait_for(
                    loop.start_tls(writer.transport, protocol, SSL_CTX, server_hostname=target),
                    timeout=TIMEOUT
                )
                tls_transport.close()
                return raw, True, "OK"
            except Exception:
                continue

        return raw, False, "FAIL_TLS_OR_CONNECT"

async def run_verification_pass():
    if not os.path.exists(POOL_FILE):
        print(f"Error: {POOL_FILE} does not exist.")
        return 0, 0, 0

    with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
        entries = [line.strip() for line in f if line.strip()]

    tested = len(entries)
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting strict pool reverification pass on {tested} proxies...")

    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [verify_proxy_entry(e, sem) for e in entries]
    results = await asyncio.gather(*tasks)

    survivors = []
    dead = []
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    for raw, ok, reason in results:
        if raw is None:
            continue
        if ok:
            survivors.append(raw)
        else:
            dead.append(f"[{ts}] {raw}\tREASON:{reason}")

    survived_cnt = len(survivors)
    died_cnt = len(dead)
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

    # Append dead entries to cache/pool_dead.txt
    if dead:
        os.makedirs(os.path.dirname(DEAD_FILE), exist_ok=True)
        with open(DEAD_FILE, "a", encoding="utf-8") as df:
            for d in dead:
                df.write(d + "\n")

    pool_size = survived_cnt
    print(f"PASS RESULT: tested={tested} survived={survived_cnt} died={died_cnt} survival={survival_pct:.1f}% pool_size={pool_size}")
    return tested, survived_cnt, died_cnt

def main():
    print("=================================================================")
    print("       POOL REVERIFY DAEMON - STRICT TLS HANDSHAKE & CA")
    print("=================================================================")

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        asyncio.run(run_verification_pass())
        return

    while True:
        try:
            asyncio.run(run_verification_pass())
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
