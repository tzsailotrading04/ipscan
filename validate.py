import asyncio, sys
SRC = sys.argv[1]; OUT = sys.argv[2]
CONC = int(sys.argv[3]) if len(sys.argv) > 3 else 800
TIO = 4.0
REQ = b"GET http://checkip.amazonaws.com/ HTTP/1.1\r\nHost: checkip.amazonaws.com\r\nUser-Agent: v\r\nConnection: close\r\n\r\n"
async def check(line):
    p = line.split(":")
    if len(p) < 2: return None
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(p[0], int(p[1])), TIO)
    except Exception:
        return None
    try:
        w.write(REQ); await w.drain()
        data = await asyncio.wait_for(r.read(256), TIO)
        if b"HTTP/" in data: return line
    except Exception:
        pass
    finally:
        try: w.close()
        except Exception: pass
    return None
async def main():
    lines = [l.strip() for l in open(SRC, encoding="utf8", errors="ignore") if l.strip()]
    sem = asyncio.Semaphore(CONC); ok = []
    async def worker(l):
        async with sem:
            if await check(l): ok.append(l)
    await asyncio.gather(*(worker(l) for l in lines))
    open(OUT, "w").write("\n".join(ok) + "\n")
    print("tested", len(lines), "alive", len(ok))
asyncio.run(main())
