#!/usr/bin/env python3
"""
tools/probe_http_forward_leads.py - Plain HTTP Forwarding Probe on Port 80
Probes cache/alive_hosts.txt on port 80
Sends GET http://example.com/ HTTP/1.1 and requires a real 200 with a body.
Survivors saved to cache/http_forward_leads.txt
"""
import os
import sys
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
OUTPUT_FILE = os.path.join(REPO_ROOT, "cache", "http_forward_leads.txt")

PORT = 80
CONCURRENCY = 1500
CONNECT_TIMEOUT = 2.5
READ_TIMEOUT = 3.5

async def probe_http_forward(sem, ip):
    async with sem:
        endpoint = f"{ip}:{PORT}"
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, PORT), timeout=CONNECT_TIMEOUT
            )
            req = (
                b"GET http://example.com/ HTTP/1.1\r\n"
                b"Host: example.com\r\n"
                b"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)\r\n"
                b"Accept: text/html,*/*\r\n"
                b"Connection: close\r\n\r\n"
            )
            writer.write(req)
            await writer.drain()

            first_line = await asyncio.wait_for(reader.readline(), timeout=READ_TIMEOUT)
            if b" 200" not in first_line:
                writer.close()
                return endpoint, False

            # Read remaining response to verify real body
            body_chunks = []
            total_bytes = 0
            while total_bytes < 4096:
                try:
                    chunk = await asyncio.wait_for(reader.read(1024), timeout=READ_TIMEOUT)
                    if not chunk:
                        break
                    body_chunks.append(chunk)
                    total_bytes += len(chunk)
                except Exception:
                    break

            writer.close()
            resp_data = b"".join(body_chunks)

            # Require a real 200 with a body from example.com
            is_valid = (
                (b"Example Domain" in resp_data) or
                (b"<html" in resp_data.lower() and total_bytes > 100) or
                (b"illustrative examples" in resp_data.lower())
            )
            return endpoint, is_valid
        except Exception:
            return endpoint, False

async def main():
    if not os.path.exists(HOSTS_FILE):
        print(f"Error: {HOSTS_FILE} not found.")
        return

    with open(HOSTS_FILE, "r", encoding="utf-8", errors="ignore") as f:
        ips = [line.strip() for line in f if line.strip()]

    total = len(ips)
    print(f"Loaded {total} IPs for Port 80 Plain HTTP Forwarding Probe (Concurrency: {CONCURRENCY})...")

    t0 = time.time()
    sem = asyncio.Semaphore(CONCURRENCY)
    survivors = []
    tested = 0

    BATCH_SIZE = 5000
    for i in range(0, total, BATCH_SIZE):
        batch = ips[i:i + BATCH_SIZE]
        tasks = [probe_http_forward(sem, ip) for ip in batch]
        results = await asyncio.gather(*tasks)

        for ep, ok in results:
            tested += 1
            if ok:
                survivors.append(ep)

        now = time.time()
        elapsed = now - t0
        rate = tested / elapsed if elapsed > 0 else 0.0
        pct = (len(survivors) / tested * 100) if tested > 0 else 0.0
        print(f"[{time.strftime('%H:%M:%S')}] Tested: {tested}/{total} ({tested/total*100:.1f}%) | "
              f"Forwarding Alive: {len(survivors)} ({pct:.2f}%) | Speed: {rate:.1f} req/s | Elapsed: {elapsed:.0f}s", flush=True)

    elapsed_total = time.time() - t0
    survival_pct = (len(survivors) / tested * 100) if tested > 0 else 0.0

    print("=" * 80)
    print("PORT 80 HTTP FORWARDING PROBE COMPLETE:")
    print(f"  Tested:           {tested}")
    print(f"  Forwarding Open:  {len(survivors)}")
    print(f"  Survival Percent: {survival_pct:.2f}%")
    print(f"  Time Taken:       {elapsed_total:.1f}s ({tested/elapsed_total:.1f} req/s)")
    print("=" * 80)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for ep in survivors:
            f.write(ep + "\n")

    print(f"Saved {len(survivors)} HTTP forward leads to {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
