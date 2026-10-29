import asyncio
import time

async def probe_proxy(proxy, sem, target="88.99.65.143", port=443, timeout=5.0):
    async with sem:
        p_ip, p_port = proxy.strip().split(":")
        p_port = int(p_port)
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(p_ip, p_port), timeout=timeout)
            connect_req = f"CONNECT {target}:{port} HTTP/1.1\r\nHost: {target}:{port}\r\n\r\n".encode()
            writer.write(connect_req)
            await asyncio.wait_for(writer.drain(), timeout=timeout)
            resp = await asyncio.wait_for(reader.read(1024), timeout=timeout)
            writer.close()
            await writer.wait_closed()
            if b" 200" in resp or b"HTTP/1.1 200" in resp or b"HTTP/1.0 200" in resp:
                return proxy, True, "200_OK"
            else:
                return proxy, False, resp.split(b"\r\n")[0].decode(errors='ignore')
        except Exception as e:
            return proxy, False, type(e).__name__

async def main():
    with open(r"D:\DEpinFarm\work\traff_200_proxies.txt", "r") as f:
        proxies = [l.strip() for l in f if l.strip()]

    sem = asyncio.Semaphore(50)
    print(f"Probing {len(proxies)} proxies against Traffmonetizer balancer (88.99.65.143:443)...")
    tasks = [probe_proxy(p, sem) for p in proxies]
    results = await asyncio.gather(*tasks)

    ok_count = sum(1 for _, ok, _ in results if ok)
    print(f"\nRESULTS:")
    print(f"Total tested: {len(proxies)}")
    print(f"Successfully connected to Traffmonetizer balancer: {ok_count} ({(ok_count/len(proxies))*100:.1f}%)")
    for p, ok, reason in results[:15]:
        print(f"  {p}: {'OK' if ok else 'FAIL'} ({reason})")

if __name__ == "__main__":
    asyncio.run(main())
