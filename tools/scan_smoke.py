import asyncio
import time
import sys

TARGET_PORTS = [8080, 3128, 1080, 8000]

async def check_port(sem, ip, port, hits):
    async with sem:
        try:
            r, w = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=1.0)
            hits.append(f"{ip}:{port}")
            w.close()
            try:
                await w.wait_closed()
            except Exception:
                pass
        except Exception:
            pass

async def main():
    # 256 IPs from 104.16.0.0/16
    ips = [f"104.16.1.{i}" for i in range(1, 257)]
    sem = asyncio.Semaphore(500)
    hits = []

    t0 = time.monotonic()
    tasks = [check_port(sem, ip, port, hits) for ip in ips for port in TARGET_PORTS]
    await asyncio.gather(*tasks)
    elapsed = time.monotonic() - t0

    total_probes = len(ips) * len(TARGET_PORTS)
    connects_per_sec = total_probes / max(0.001, elapsed)

    print("=== SMOKE TEST RESULTS ===")
    print(f"IPs scanned: {len(ips)}")
    print(f"Seconds elapsed: {elapsed:.2f}s")
    print(f"connects/s: {connects_per_sec:.1f}/s")
    print(f"hits found: {len(hits)}")
    if hits:
        print("Sample hits:")
        for h in hits[:5]:
            print(f"  {h}")
    else:
        print("SMOKEFAIL")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
