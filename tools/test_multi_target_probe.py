"""
test_multi_target_probe.py
Multi-target probe test:
Tries speed.cloudflare.com:443, www.google.com:443, and one.one.one.one:443 in turn.
Pass if ANY returns 0x16, 5s timeout per stage.
Tests the 8 known-good proxies.
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

TARGETS = [
    "speed.cloudflare.com",
    "www.google.com",
    "one.one.one.one",
]

CLIENT_HELLOS = {}
for t in TARGETS:
    ctx = ssl.create_default_context()
    bio_in, bio_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    sslobj = ctx.wrap_bio(bio_in, bio_out, server_hostname=t)
    try:
        sslobj.do_handshake()
    except ssl.SSLWantReadError:
        pass
    CLIENT_HELLOS[t] = bio_out.read()

async def probe_single_target(ip, port, target, timeout=5.0):
    loop = asyncio.get_running_loop()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setblocking(False)
    try:
        # Stage 1: TCP connect
        await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=timeout)
        
        # Stage 2: Send CONNECT
        req = f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n".encode()
        await loop.sock_sendall(s, req)
        
        # Stage 3: Recv reply
        resp = b""
        t_end = time.monotonic() + timeout
        while b"\r\n\r\n" not in resp:
            if time.monotonic() > t_end:
                return False, "Timeout waiting for \\r\\n\\r\\n"
            c = await asyncio.wait_for(loop.sock_recv(s, 512), timeout=timeout)
            if not c:
                return False, f"Connection closed early ({resp[:50]})"
            resp += c
            
        first_line = resp.split(b"\r\n")[0].decode(errors="ignore")
        if not (resp.startswith(b"HTTP/") and (" 200" in first_line or " 2" in first_line)):
            return False, f"Status: {first_line}"
            
        parts = resp.split(b"\r\n\r\n", 1)
        trailing = parts[1] if len(parts) > 1 else b""
        if trailing:
            if trailing[:1] == b"\x16":
                return True, f"PASS (trailing 0x16) via {target}"
            return False, f"Trailing non-TLS byte: {repr(trailing[:1])}"
            
        # Stage 4: Send ClientHello
        await loop.sock_sendall(s, CLIENT_HELLOS[target])
        
        # Stage 5: Recv ServerHello 0x16
        b1 = await asyncio.wait_for(loop.sock_recv(s, 1), timeout=timeout)
        if b1 == b"\x16":
            return True, f"PASS (ServerHello 0x16) via {target}"
        return False, f"Non-0x16 byte: {repr(b1)}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    finally:
        try:
            s.close()
        except Exception:
            pass

async def probe_proxy_multi(addr):
    ip, port_str = addr.split(":")
    port = int(port_str)
    
    t0 = time.monotonic()
    details = []
    
    for target in TARGETS:
        ok, msg = await probe_single_target(ip, port, target, timeout=5.0)
        details.append(f"{target} -> {msg}")
        if ok:
            dt = (time.monotonic() - t0) * 1000
            return {
                "addr": addr,
                "passed": True,
                "winning_target": target,
                "msg": msg,
                "total_ms": dt,
                "all_details": details
            }
            
    dt = (time.monotonic() - t0) * 1000
    return {
        "addr": addr,
        "passed": False,
        "winning_target": None,
        "msg": details[-1],
        "total_ms": dt,
        "all_details": details
    }

async def main():
    print("=" * 80)
    print("MULTI-TARGET STRICT PROBE TEST (5s/stage)")
    print(f"Candidate Targets: {', '.join(TARGETS)}")
    print("=" * 80)
    
    tasks = [probe_proxy_multi(p) for p in PROXIES]
    results = await asyncio.gather(*tasks)
    
    passed_cnt = sum(1 for r in results if r["passed"])
    
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        win = f"[{r['winning_target']}]" if r["winning_target"] else "[NONE]"
        print(f"[{status}] {r['addr']:<22} | {win:<24} | {r['total_ms']:6.1f}ms | {r['msg']}")
        if not r["passed"]:
            for d in r["all_details"]:
                print(f"       -> {d}")
                
    print("-" * 80)
    print(f"Final Result: {passed_cnt}/{len(PROXIES)} PASSED ({passed_cnt/len(PROXIES)*100:.1f}%)")
    print("Requirement: 7 of 8 must pass (103.78.98.74 is dead).")
    if passed_cnt >= 7:
        print(">>> REQUIREMENT SATISFIED: 7 of 8 PASSED! <<<")
    else:
        print(f">>> NOT MET: {passed_cnt}/8 <<<")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
