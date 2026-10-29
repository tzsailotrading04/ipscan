"""
test_strict_probe_8.py
Tests the strict TLS 0x16 probe against 8 known-good proxies with detailed stage diagnostics:
Stage 1: TCP connect
Stage 2: HTTP CONNECT request
Stage 3: HTTP 200 reply parse
Stage 4: Post-reply trailing check
Stage 5: Send CLIENT_HELLO (with SNI internetdb.shodan.io)
Stage 6: Read first byte from target (timeout 5s), verify b'\\x16'
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

def make_client_hello(hostname=HOST):
    ctx = ssl.create_default_context()
    bio_in, bio_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    sslobj = ctx.wrap_bio(bio_in, bio_out, server_hostname=hostname)
    try:
        sslobj.do_handshake()
    except ssl.SSLWantReadError:
        pass
    return bio_out.read()

CLIENT_HELLO = make_client_hello(HOST)

async def probe_proxy(addr):
    ip, port_str = addr.split(":")
    port = int(port_str)
    
    stage = "INIT"
    t0 = time.monotonic()
    
    try:
        # Stage 1: TCP Connect
        stage = "STAGE_1_TCP_CONNECT"
        loop = asyncio.get_running_loop()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=5.0)
        t_conn = time.monotonic() - t0
        
        # Stage 2: Send HTTP CONNECT
        stage = "STAGE_2_SEND_CONNECT"
        req = f"CONNECT {HOST}:443 HTTP/1.1\r\nHost: {HOST}:443\r\n\r\n".encode()
        await loop.sock_sendall(s, req)
        
        # Stage 3: Read HTTP 200 reply
        stage = "STAGE_3_RECV_CONNECT_REPLY"
        resp = b""
        t_end = time.monotonic() + 5.0
        while b"\r\n\r\n" not in resp:
            if time.monotonic() > t_end:
                raise TimeoutError("Timeout waiting for \\r\\n\\r\\n in CONNECT reply")
            c = await asyncio.wait_for(loop.sock_recv(s, 256), timeout=5.0)
            if not c:
                raise ConnectionResetError("Connection closed before full HTTP reply")
            resp += c
            
        first_line = resp.split(b"\r\n")[0].decode(errors="ignore")
        if not (resp.startswith(b"HTTP/") and (" 200" in first_line or " 2" in first_line)):
            raise ValueError(f"Non-200 CONNECT reply: {first_line}")
            
        parts = resp.split(b"\r\n\r\n", 1)
        trailing = parts[1] if len(parts) > 1 else b""
        
        # Stage 4: Trailing inspection or Stage 5/6: TLS Handshake
        if trailing:
            b1 = trailing[:1]
            if b1 == b"\x16":
                s.close()
                return {
                    "addr": addr,
                    "passed": True,
                    "stage": "PASS_TRAILING",
                    "status_line": first_line,
                    "b1": b1,
                    "total_ms": (time.monotonic() - t0) * 1000
                }
            else:
                s.close()
                raise ValueError(f"Trailing byte after 200 is {repr(b1)} (not 0x16 TLS ServerHello)")
                
        # Stage 5: Send CLIENT_HELLO into established tunnel
        stage = "STAGE_5_SEND_CLIENT_HELLO"
        await loop.sock_sendall(s, CLIENT_HELLO)
        
        # Stage 6: Read first byte of TLS ServerHello with 5s timeout
        stage = "STAGE_6_RECV_SERVER_HELLO"
        b1 = await asyncio.wait_for(loop.sock_recv(s, 1), timeout=5.0)
        s.close()
        
        if b1 == b"\x16":
            return {
                "addr": addr,
                "passed": True,
                "stage": "PASS_TLS_0x16",
                "status_line": first_line,
                "b1": b1,
                "total_ms": (time.monotonic() - t0) * 1000
            }
        else:
            raise ValueError(f"First byte received after ClientHello is {repr(b1)} (expected 0x16)")
            
    except Exception as e:
        try:
            s.close()
        except Exception:
            pass
        return {
            "addr": addr,
            "passed": False,
            "stage": stage,
            "error": str(e) or repr(e),
            "total_ms": (time.monotonic() - t0) * 1000
        }

async def main():
    print("=" * 70)
    print("STRICT 0x16 PROBE VERIFICATION SUITE")
    print(f"Target Host: {HOST}:443")
    print(f"CLIENT_HELLO Byte Length: {len(CLIENT_HELLO)} bytes")
    has_sni = HOST.encode() in CLIENT_HELLO
    print(f"CLIENT_HELLO Carries Valid SNI for '{HOST}': {has_sni}")
    print(f"Post-CONNECT Read Timeout: 5.0 seconds")
    print("=" * 70)
    
    tasks = [probe_proxy(p) for p in PROXIES]
    results = await asyncio.gather(*tasks)
    
    passed_count = sum(1 for r in results if r["passed"])
    
    print("\nPROBE RESULTS:")
    print("-" * 70)
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        if r["passed"]:
            print(f"[{status}] {r['addr']:<22} | {r['total_ms']:6.1f}ms | Reply: {r['status_line']} | Byte: {r['b1']}")
        else:
            print(f"[{status}] {r['addr']:<22} | {r['total_ms']:6.1f}ms | Stage: {r['stage']} | Error: {r['error']}")
            
    print("-" * 70)
    print(f"Summary: {passed_count}/{len(PROXIES)} PASSED ({passed_count/len(PROXIES)*100:.1f}%)")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
