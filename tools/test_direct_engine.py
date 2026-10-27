import asyncio
import time

SCAN_MODE = "direct"
DIRECT_PORTS = [8080, 3128, 1080, 8000]

async def check_direct_port(ip, port):
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=1.0)
        w.close()
        try:
            await w.wait_closed()
        except Exception:
            pass
        return port
    except Exception:
        return None

async def scan_direct(ip):
    res = await asyncio.gather(*[check_direct_port(ip, p) for p in DIRECT_PORTS], return_exceptions=True)
    return [p for p in res if isinstance(p, int)]

async def main():
    ips = [f"104.16.0.{i}" for i in range(1, 10)]
    results = await asyncio.gather(*[scan_direct(ip) for ip in ips])
    for ip, hits in zip(ips, results):
        print(f"{ip}: {hits}")

if __name__ == "__main__":
    asyncio.run(main())
