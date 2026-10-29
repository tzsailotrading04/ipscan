"""
run_strict_test_final.py
Executes the read-only strict probe test as specified by the user:
(1) Runs strict probe against the 8 known-good proxies
(2) Prints CLIENT_HELLO byte length and whether it carries valid SNI for internetdb.shodan.io
(3) Prints exact stage and error for any failure
(4) Uses post-CONNECT read timeout = 5.0s
Also reports comparative behavior with speed.cloudflare.com to highlight target-specific ACL filtering.
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

HOST = "internetdb.shodan.io"

def build_client_hello(hostname):
    ctx = ssl.create_default_context()
    bio_in, bio_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    sslobj = ctx.wrap_bio(bio_in, bio_out, server_hostname=hostname)
    try:
        sslobj.do_handshake()
    except ssl.SSLWantReadError:
        pass
    return bio_out.read()

CLIENT_HELLO = build_client_hello(HOST)

async def probe_proxy(addr, target_host=HOST, timeout=5.0):
    ip, port_str = addr.split(":")
    port = int(port_str)
    ch = build_client_hello(target_host)
    
    stage = "STAGE_1_TCP_CONNECT"
    t0 = time.monotonic()
    s = None
    
    try:
        loop = asyncio.get_running_loop()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=5.0)
        t_conn = time.monotonic() - t0
        
        stage = "STAGE_2_SEND_CONNECT"
        req = f"CONNECT {target_host}:443 HTTP/1.1\r\nHost: {target_host}:443\r\n\r\n".encode()
        await loop.sock_sendall(s, req)
        
        stage = "STAGE_3_RECV_CONNECT_REPLY"
        resp = b""
        t_end = time.monotonic() + timeout
        while b"\r\n\r\n" not in resp:
            if time.monotonic() > t_end:
                raise TimeoutError(f"{timeout}s timeout waiting for \\r\\n\\r\\n header boundary")
            c = await asyncio.wait_for(loop.sock_recv(s, 512), timeout=timeout)
            if not c:
                raise ConnectionResetError(f"Connection closed by proxy (received {len(resp)} bytes: {repr(resp[:100])})")
            resp += c
            
        first_line = resp.split(b"\r\n")[0].decode(errors="ignore")
        if not (resp.startswith(b"HTTP/") and (" 200" in first_line or " 2" in first_line)):
            raise ValueError(f"HTTP reply status: {first_line}")
            
        parts = resp.split(b"\r\n\r\n", 1)
        trailing = parts[1] if len(parts) > 1 else b""
        
        if trailing:
            b1 = trailing[:1]
            if b1 == b"\x16":
                return {
                    "addr": addr,
                    "target": target_host,
                    "passed": True,
                    "stage": "PASS",
                    "status_line": first_line,
                    "first_byte": b1,
                    "total_ms": (time.monotonic() - t0) * 1000
                }
            else:
                raise ValueError(f"Trailing byte after 200 is {repr(b1)} (fake HTTP router response)")
                
        stage = "STAGE_5_SEND_CLIENT_HELLO"
        await loop.sock_sendall(s, ch)
        
        stage = "STAGE_6_RECV_SERVER_HELLO_0x16"
        b1 = await asyncio.wait_for(loop.sock_recv(s, 1), timeout=timeout)
        if b1 == b"\x16":
            return {
                "addr": addr,
                "target": target_host,
                "passed": True,
                "stage": "PASS",
                "status_line": first_line,
                "first_byte": b1,
                "total_ms": (time.monotonic() - t0) * 1000
            }
        else:
            raise ValueError(f"First byte received after ClientHello is {repr(b1)} (expected 0x16)")
            
    except Exception as e:
        return {
            "addr": addr,
            "target": target_host,
            "passed": False,
            "stage": stage,
            "error": str(e) or repr(e),
            "total_ms": (time.monotonic() - t0) * 1000
        }
    finally:
        if s:
            try:
                s.close()
            except Exception:
                pass

async def main():
    print("=" * 80)
    print("STRICT 0x16 TLS PROBE READ-ONLY VERIFICATION")
    print(f"Target: {HOST}:443")
    print(f"CLIENT_HELLO Byte Length: {len(CLIENT_HELLO)} bytes")
    has_sni = HOST.encode() in CLIENT_HELLO
    sni_offset = CLIENT_HELLO.find(HOST.encode()) if has_sni else -1
    print(f"CLIENT_HELLO Carries Valid SNI for '{HOST}': {has_sni} (at byte offset {sni_offset})")
    print(f"Post-CONNECT Read Timeout: 5.0 seconds")
    print("=" * 80)
    
    # Run against internetdb.shodan.io:443
    tasks_shodan = [probe_proxy(p, HOST, timeout=5.0) for p in PROXIES]
    res_shodan = await asyncio.gather(*tasks_shodan)
    
    print("\n--- RESULTS AGAINST internetdb.shodan.io:443 ---")
    print(f"{'Proxy':<22} | {'Result':<6} | {'Time (ms)':<9} | {'Stage / Status / Error'}")
    print("-" * 80)
    for r in res_shodan:
        status = "PASS" if r["passed"] else "FAIL"
        if r["passed"]:
            print(f"{r['addr']:<22} | {status:<6} | {r['total_ms']:7.1f}ms | {r['status_line']} -> Byte: {r['first_byte']}")
        else:
            print(f"{r['addr']:<22} | {status:<6} | {r['total_ms']:7.1f}ms | {r['stage']}: {r['error']}")
            
    print("\n" + "=" * 80)
    print("COMPARATIVE CHECK: TARGET ACL SENSITIVITY (speed.cloudflare.com:443)")
    print("=" * 80)
    tasks_cf = [probe_proxy(p, "speed.cloudflare.com", timeout=5.0) for p in PROXIES]
    res_cf = await asyncio.gather(*tasks_cf)
    for r in res_cf:
        status = "PASS" if r["passed"] else "FAIL"
        if r["passed"]:
            print(f"{r['addr']:<22} | {status:<6} | {r['total_ms']:7.1f}ms | {r['status_line']} -> Byte: {r['first_byte']}")
        else:
            print(f"{r['addr']:<22} | {status:<6} | {r['total_ms']:7.1f}ms | {r['stage']}: {r['error']}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
