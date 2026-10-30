#!/usr/bin/env python3
"""
tools/probe_strict_leads.py - Full strict tunnel probe on alternate ports
Probes cache/alive_hosts.txt across ports: 3128, 8080, 8888, 443, 1080, 8118
Strict probe: TCP CONNECT -> HTTP 200 -> SSL_CTX TLS handshake to speed.cloudflare.com
Survivors saved to cache/revived_leads.txt
"""
import os
import sys
import ssl
import time
import asyncio
from datetime import datetime

# Silence Windows asyncio connection reset bug in proactor loop
if sys.platform == "win32":
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport
        orig_lost = _ProactorBasePipeTransport._call_connection_lost
        def silence_lost(self, *args, **kwargs):
            try:
                return orig_lost(self, *args, **kwargs)
            except (ConnectionResetError, OSError):
                pass
        _ProactorBasePipeTransport._call_connection_lost = silence_lost
    except Exception:
        pass

REPO_ROOT = r"D:\DEpinFarm"
HOSTS_FILE = os.path.join(REPO_ROOT, "cache", "alive_hosts.txt")
OUTPUT_FILE = os.path.join(REPO_ROOT, "cache", "revived_leads.txt")

PORTS = [3128, 8080, 8888, 443, 1080, 8118]
CONCURRENCY = 1500
CONNECT_TIMEOUT = 2.5
TLS_TIMEOUT = 3.5

SSL_CTX = ssl.create_default_context()

async def probe_endpoint(sem, ip, port):
    async with sem:
        endpoint = f"{ip}:{port}"
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port), timeout=CONNECT_TIMEOUT
            )
            req = b"CONNECT speed.cloudflare.com:443 HTTP/1.1\r\nHost: speed.cloudflare.com:443\r\n\r\n"
            writer.write(req)
            await writer.drain()

            first_line = await asyncio.wait_for(reader.readline(), timeout=TLS_TIMEOUT)
            if b" 200" not in first_line:
                writer.close()
                return endpoint, False

            # Consume headers
            while True:
                h = await asyncio.wait_for(reader.readline(), timeout=TLS_TIMEOUT)
                if h in (b"\r\n", b"\n", b""):
                    break

            # Upgrade to TLS
            loop = asyncio.get_running_loop()
            transport = writer.transport
            protocol = transport.get_protocol()
            new_transport = await asyncio.wait_for(
                loop.start_tls(transport, protocol, SSL_CTX, server_hostname="speed.cloudflare.com"),
                timeout=TLS_TIMEOUT
            )
            new_transport.close()
            return endpoint, True
        except Exception:
            return endpoint, False

async def main():
    if not os.path.exists(HOSTS_FILE):
        print(f"Error: {HOSTS_FILE} not found.")
        return

    with open(HOSTS_FILE, "r", encoding="utf-8", errors="ignore") as f:
        ips = [line.strip() for line in f if line.strip()]

    total_ips = len(ips)
    targets = [(ip, p) for ip in ips for p in PORTS]
    total_targets = len(targets)

    print(f"Loaded {total_ips} IPs -> {total_targets} targets across ports: {PORTS}")
    print(f"Starting async strict tunnel probe (Concurrency: {CONCURRENCY})...")

    t0 = time.time()
    sem = asyncio.Semaphore(CONCURRENCY)
    survivors = []
    tested = 0

    BATCH_SIZE = 6000
    for i in range(0, total_targets, BATCH_SIZE):
        batch = targets[i:i + BATCH_SIZE]
        tasks = [probe_endpoint(sem, ip, p) for ip, p in batch]
        results = await asyncio.gather(*tasks)

        for ep, ok in results:
            tested += 1
            if ok:
                survivors.append(ep)

        now = time.time()
        elapsed = now - t0
        rate = tested / elapsed if elapsed > 0 else 0.0
        pct = (len(survivors) / tested * 100) if tested > 0 else 0.0
        print(f"[{time.strftime('%H:%M:%S')}] Tested: {tested}/{total_targets} ({tested/total_targets*100:.1f}%) | "
              f"Open/Survivors: {len(survivors)} ({pct:.2f}%) | Speed: {rate:.1f} req/s | Elapsed: {elapsed:.0f}s", flush=True)

    elapsed_total = time.time() - t0
    survival_pct = (len(survivors) / tested * 100) if tested > 0 else 0.0

    print("=" * 80)
    print("STRICT TUNNEL PROBE COMPLETE:")
    print(f"  Tested:           {tested}")
    print(f"  Open (Survivors): {len(survivors)}")
    print(f"  Survival Percent: {survival_pct:.2f}%")
    print(f"  Time Taken:       {elapsed_total:.1f}s ({tested/elapsed_total:.1f} req/s)")
    print("=" * 80)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for ep in survivors:
            f.write(ep + "\n")

    print(f"Saved {len(survivors)} survivors to {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
