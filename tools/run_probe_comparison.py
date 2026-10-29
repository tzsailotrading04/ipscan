"""
run_probe_comparison.py
Probes the 8 proxies against:
1. internetdb.shodan.io:443 (as requested in user prompt)
2. speed.cloudflare.com:443 (standard fleet target)
Records exact stage, timing, status line, and first byte received.
Post-CONNECT read timeout raised to 5.0s.
"""
import asyncio
import socket
import ssl
import time

PROXIES = [
    "2.26.138.141:3128",
    "65.51.176.162:8080",
    "187.245.204.134:3128",
    "163.52.229.241:8080",
    "125.162.222.93:8080",
    "27.147.187.204:9249",
    "103.78.98.74:8888",
    "103.185.48.50:8080",
]

def make_client_hello(hostname):
    ctx = ssl.create_default_context()
    bio_in, bio_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    sslobj = ctx.wrap_bio(bio_in, bio_out, server_hostname=hostname)
    try:
        sslobj.do_handshake()
    except ssl.SSLWantReadError:
        pass
    return bio_out.read()

async def probe_one(addr, target_host):
    ip, port_str = addr.split(":")
    port = int(port_str)
    client_hello = make_client_hello(target_host)
    
    stage = "STAGE_1_TCP_CONNECT"
    t0 = time.monotonic()
    s = None
    
    try:
        loop = asyncio.get_running_loop()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=5.0)
        
        stage = "STAGE_2_SEND_CONNECT"
        req = f"CONNECT {target_host}:443 HTTP/1.1\r\nHost: {target_host}:443\r\n\r\n".encode()
        await loop.sock_sendall(s, req)
        
        stage = "STAGE_3_RECV_CONNECT_REPLY"
        resp = b""
        t_end = time.monotonic() + 5.0
        while b"\r\n\r\n" not in resp:
            if time.monotonic() > t_end:
                raise TimeoutError("5.0s timeout waiting for \\r\\n\\r\\n header boundary")
            c = await asyncio.wait_for(loop.sock_recv(s, 512), timeout=5.0)
            if not c:
                raise ConnectionResetError(f"Connection closed by proxy (received {len(resp)} bytes: {repr(resp)})")
            resp += c
            
        first_line = resp.split(b"\r\n")[0].decode(errors="ignore")
        if not (resp.startswith(b"HTTP/") and (" 200" in first_line or " 2" in first_line)):
            raise ValueError(f"HTTP reply status: {first_line}")
            
        parts = resp.split(b"\r\n\r\n", 1)
        trailing = parts[1] if len(parts) > 1 else b""
        
        if trailing:
            b1 = trailing[:1]
            if b1 == b"\x16":
                return {"pass": True, "stage": "PASS", "info": f"{first_line} | Trailing 0x16", "ms": (time.monotonic() - t0)*1000}
            else:
                raise ValueError(f"Trailing byte after 200 is {repr(b1)} (fake HTTP router response)")
                
        stage = "STAGE_5_SEND_CLIENT_HELLO"
        await loop.sock_sendall(s, client_hello)
        
        stage = "STAGE_6_RECV_TLS_0x16"
        b1 = await asyncio.wait_for(loop.sock_recv(s, 1), timeout=5.0)
        if b1 == b"\x16":
            return {"pass": True, "stage": "PASS", "info": f"{first_line} | ServerHello 0x16", "ms": (time.monotonic() - t0)*1000}
        else:
            raise ValueError(f"Byte received after ClientHello: {repr(b1)} (expected 0x16)")
            
    except Exception as e:
        return {"pass": False, "stage": stage, "info": str(e), "ms": (time.monotonic() - t0)*1000}
    finally:
        if s:
            try:
                s.close()
            except Exception:
                pass

async def run_target(target):
    ch = make_client_hello(target)
    has_sni = target.encode() in ch
    print(f"\nTarget: {target}:443")
    print(f"  CLIENT_HELLO Length: {len(ch)} bytes")
    print(f"  Carries Valid SNI:   {has_sni} (offset {ch.find(target.encode()) if has_sni else -1})")
    print(f"  Post-CONNECT Timeout: 5.0 seconds\n")
    print(f"{'Proxy':<22} | {'Result':<6} | {'Time (ms)':<9} | {'Stage / Details'}")
    print("-" * 80)
    
    tasks = [probe_one(p, target) for p in PROXIES]
    res = await asyncio.gather(*tasks)
    for p, r in zip(PROXIES, res):
        status = "PASS" if r["pass"] else "FAIL"
        print(f"{p:<22} | {status:<6} | {r['ms']:7.1f}ms | {r['stage']}: {r['info']}")

if __name__ == "__main__":
    asyncio.run(run_target("internetdb.shodan.io"))
    asyncio.run(run_target("speed.cloudflare.com"))
