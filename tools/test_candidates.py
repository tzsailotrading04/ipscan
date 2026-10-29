import asyncio
import time

async def probe(proxy, sem):
    async with sem:
        ip, port = proxy.split(":")
        t0 = time.time()
        try:
            r, w = await asyncio.wait_for(asyncio.open_connection(ip, int(port)), timeout=3.0)
            w.write(b"CONNECT 88.99.65.143:443 HTTP/1.1\r\nHost: 88.99.65.143:443\r\n\r\n")
            await asyncio.wait_for(w.drain(), timeout=3.0)
            data = await asyncio.wait_for(r.read(512), timeout=3.0)
            w.close()
            await w.wait_closed()
            dt = round((time.time() - t0) * 1000, 1)
            if b" 200" in data:
                return proxy, True, dt, data.split(b"\r\n")[0].decode(errors="ignore")
        except Exception:
            pass
        return proxy, False, None, None

async def main():
    with open(r"D:\DEpinFarm\ip\harvest\real_pool.txt", encoding="utf-8", errors="ignore") as f:
        lines = [l.strip().split("\t")[0] for l in f if l.strip()]
    candidates = [p for p in lines if not p.endswith(":80")][:100]
    sem = asyncio.Semaphore(50)
    tasks = [probe(p, sem) for p in candidates]
    res = await asyncio.gather(*tasks)
    ok = [r for r in res if r[1]]
    print(f"Tested {len(candidates)}, OK with CONNECT: {len(ok)}")
    for p, success, latency, status in sorted(ok, key=lambda x: x[2])[:15]:
        print(f"  {p} -> {latency}ms ({status})")

if __name__ == "__main__":
    asyncio.run(main())
