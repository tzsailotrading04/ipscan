"""
compare_concurrency_40_vs_250.py
Runs the exact same fixed 500 proxies:
- Pass 1: concurrency = 40
- Pass 2: concurrency = 250
Outputs side-by-side comparison of pass rates, durations, and socket errors.
"""
import asyncio
import os
import socket
import ssl
import time

ROOT = r"D:\DEpinFarm"
FIXED_500_FILE = os.path.join(ROOT, "ip", "harvest", "test_fixed_500.txt")

TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
CLIENT_HELLOS = {}
for _t in TARGETS:
    _ctx = ssl.create_default_context()
    _bio_in, _bio_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    _sslobj = _ctx.wrap_bio(_bio_in, _bio_out, server_hostname=_t)
    try:
        _sslobj.do_handshake()
    except ssl.SSLWantReadError:
        pass
    CLIENT_HELLOS[_t] = _bio_out.read()

async def inline_probe_connected(s, target, timeout=5.0):
    try:
        loop = asyncio.get_running_loop()
        req = f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n".encode()
        await loop.sock_sendall(s, req)
        resp = b""
        t_end = time.monotonic() + timeout
        while b"\r\n\r\n" not in resp:
            if time.monotonic() > t_end:
                return False
            c = await asyncio.wait_for(loop.sock_recv(s, 512), timeout=timeout)
            if not c:
                return False
            resp += c
        first_line = resp.split(b"\r\n")[0]
        if not (resp.startswith(b"HTTP/") and (b" 200" in first_line or b" 2" in first_line)):
            return False
        parts = resp.split(b"\r\n\r\n", 1)
        trailing = parts[1] if len(parts) > 1 else b""
        if trailing:
            return trailing[:1] == b"\x16"
        await loop.sock_sendall(s, CLIENT_HELLOS[target])
        b1 = await asyncio.wait_for(loop.sock_recv(s, 1), timeout=timeout)
        return b1 == b"\x16"
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass

async def probe_single_target(ip, port, target, timeout=5.0):
    loop = asyncio.get_running_loop()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setblocking(False)
    try:
        await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=timeout)
        return await inline_probe_connected(s, target, timeout=timeout)
    except Exception:
        try:
            s.close()
        except Exception:
            pass
        return False

async def verify_proxy(ip, port, sem):
    async with sem:
        loop = asyncio.get_running_loop()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        try:
            await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=5.0)
        except Exception:
            try:
                s.close()
            except Exception:
                pass
            return False

        if await inline_probe_connected(s, "speed.cloudflare.com", timeout=5.0):
            return True

        for t in ["www.google.com", "one.one.one.one"]:
            if await probe_single_target(ip, port, t, timeout=5.0):
                return True

        return False

async def run_pass(proxies, concurrency):
    sem = asyncio.Semaphore(concurrency)
    t0 = time.time()
    tasks = []
    for p in proxies:
        ip, p_str = p.split(":")
        tasks.append(verify_proxy(ip, int(p_str), sem))
    results = await asyncio.gather(*tasks)
    dt = time.time() - t0
    passed = sum(1 for r in results if r)
    rate = (passed / len(proxies)) * 100
    speed = len(proxies) / dt
    return {
        "concurrency": concurrency,
        "total": len(proxies),
        "passed": passed,
        "rate_pct": rate,
        "duration_sec": round(dt, 2),
        "speed_per_sec": round(speed, 1),
        "passed_proxies": [p for p, r in zip(proxies, results) if r]
    }

async def main():
    with open(FIXED_500_FILE, "r") as f:
        proxies = [l.strip() for l in f if l.strip()]

    print("=" * 70, flush=True)
    print(f"CONCURRENCY COMPARISON EXPERIMENT ON {len(proxies)} FIXED PROXIES", flush=True)
    print("=" * 70, flush=True)

    print("\n--- Pass 1: Concurrency = 40 ---", flush=True)
    res_40 = await run_pass(proxies, 40)
    print(f"Passed: {res_40['passed']}/{res_40['total']} ({res_40['rate_pct']:.2f}%) in {res_40['duration_sec']}s ({res_40['speed_per_sec']}/s)", flush=True)

    # Sleep 3 seconds to let sockets drain
    await asyncio.sleep(3)

    print("\n--- Pass 2: Concurrency = 250 ---", flush=True)
    res_250 = await run_pass(proxies, 250)
    print(f"Passed: {res_250['passed']}/{res_250['total']} ({res_250['rate_pct']:.2f}%) in {res_250['duration_sec']}s ({res_250['speed_per_sec']}/s)", flush=True)

    set_40 = set(res_40["passed_proxies"])
    set_250 = set(res_250["passed_proxies"])
    both = set_40 & set_250
    only_40 = set_40 - set_250
    only_250 = set_250 - set_40

    print("\n" + "=" * 70, flush=True)
    print("COMPARISON RESULTS:", flush=True)
    print(f"  Concurrency 40 : {res_40['passed']:3} passed ({res_40['rate_pct']:5.2f}%) | Time: {res_40['duration_sec']:5.1f}s | Speed: {res_40['speed_per_sec']:4.1f}/s", flush=True)
    print(f"  Concurrency 250: {res_250['passed']:3} passed ({res_250['rate_pct']:5.2f}%) | Time: {res_250['duration_sec']:5.1f}s | Speed: {res_250['speed_per_sec']:4.1f}/s", flush=True)
    print("-" * 70, flush=True)
    print(f"  Passed by both:      {len(both)}", flush=True)
    print(f"  Passed only at C=40: {len(only_40)}", flush=True)
    print(f"  Passed only at C=250:{len(only_250)}", flush=True)
    delta = res_250["rate_pct"] - res_40["rate_pct"]
    print(f"  Net Difference:      {delta:+.2f}%", flush=True)
    print("=" * 70, flush=True)

if __name__ == "__main__":
    asyncio.run(main())
