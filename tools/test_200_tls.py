import asyncio
import ssl

async def test_proxy_tls(proxy, target="blnc.traffmonetizer.com", target_ip="88.99.65.143", port=443, timeout=6.0):
    p_ip, p_port = proxy.strip().split(":")
    p_port = int(p_port)
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(p_ip, p_port), timeout=timeout)
        req = f"CONNECT {target_ip}:{port} HTTP/1.1\r\nHost: {target}:{port}\r\n\r\n".encode()
        writer.write(req)
        await asyncio.wait_for(writer.drain(), timeout=timeout)
        resp = await asyncio.wait_for(reader.read(1024), timeout=timeout)
        if not (b" 200" in resp or b"HTTP/1.1 200" in resp or b"HTTP/1.0 200" in resp):
            writer.close()
            return proxy, False, f"CONNECT_REJECTED_{resp.split(b'\\r\\n')[0].decode(errors='ignore')[:30]}"
            
        # Upgrade socket to TLS
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        
        loop = asyncio.get_running_loop()
        # Extract underlying transport socket
        sock = writer.get_extra_info('socket')
        
        # Test SSL handshake
        tls_reader, tls_writer = await asyncio.wait_for(
            asyncio.open_connection(sock=sock, ssl=ssl_ctx, server_hostname=target),
            timeout=timeout
        )
        tls_writer.close()
        await tls_writer.wait_closed()
        return proxy, True, "TLS_HANDSHAKE_SUCCESS"
    except Exception as e:
        return proxy, False, f"TLS_FAIL_{type(e).__name__}: {str(e)[:40]}"

async def main():
    with open(r"D:\DEpinFarm\work\traff_200_proxies.txt", "r") as f:
        proxies = [l.strip() for l in f if l.strip()]

    print(f"Testing real TLS Handshake over proxy tunnel for {len(proxies)} proxies...")
    sem = asyncio.Semaphore(40)
    async def worker(p):
        async with sem:
            return await test_proxy_tls(p)

    results = await asyncio.gather(*[worker(p) for p in proxies])
    ok_proxies = [p for p, ok, _ in results if ok]
    print(f"\nREAL TLS RESULTS: {len(ok_proxies)} / {len(proxies)} passed TLS Handshake ({(len(ok_proxies)/len(proxies))*100:.1f}%)")
    for p, ok, reason in results[:20]:
        print(f"  {p}: {'PASS' if ok else 'FAIL'} ({reason})")

if __name__ == "__main__":
    asyncio.run(main())
