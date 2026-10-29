"""
tools/test_worker_load_comparison.py
Compares the SHARD probe config at 6 workers vs 2 workers vs 1 worker:
- Tests the exact same fixed 500 known-good proxies
- Uses the exact shard probe config:
  - Connect timeout 1.8s
  - Multi-target probe: speed.cloudflare.com, www.google.com, one.one.one.one
  - 5s per stage, ServerHello 0x16 check
  - Multi-process execution (each worker is an isolated Python process)
- Measures pass rate, elapsed time, and proxies/sec for 6, 2, and 1 worker processes.
"""
import asyncio
import os
import socket
import ssl
import sys
import time
import multiprocessing

ROOT = r"D:\DEpinFarm"
KNOWN_GOOD_PATH = os.path.join(ROOT, "ip", "harvest", "test_500_known_good.txt")

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
        try: s.close()
        except Exception: pass

async def probe_single_target(ip, port, target, timeout=5.0):
    loop = asyncio.get_running_loop()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setblocking(False)
    try:
        await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=timeout)
        return await inline_probe_connected(s, target, timeout=timeout)
    except Exception:
        try: s.close()
        except Exception: pass
        return False

async def check_proxy_shard_config(ip_port, sem):
    async with sem:
        try:
            ip, port_s = ip_port.split(":", 1)
            port = int(port_s)
        except Exception:
            return ip_port, False

        loop = asyncio.get_running_loop()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        try:
            # Exact shard connect timeout
            await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=1.8)
        except Exception:
            try: s.close()
            except Exception: pass
            return ip_port, False

        if await inline_probe_connected(s, "speed.cloudflare.com", timeout=5.0):
            return ip_port, True

        for t in ["www.google.com", "one.one.one.one"]:
            if await probe_single_target(ip, port, t, timeout=5.0):
                return ip_port, True

        return ip_port, False

def worker_process_func(worker_id, num_workers, proxy_subset, return_dict):
    async def run_subset():
        # Exact shard semaphore
        sem = asyncio.Semaphore(2500)
        tasks = [check_proxy_shard_config(p, sem) for p in proxy_subset]
        results = await asyncio.gather(*tasks)
        passed = [ip_port for ip_port, ok in results if ok]
        return passed

    res = asyncio.run(run_subset())
    return_dict[worker_id] = res

def run_test_suite(num_workers, all_proxies):
    print(f"\n>>> TESTING WITH {num_workers} PARALLEL WORKER PROCESS{'ES' if num_workers > 1 else ''} <<<", flush=True)
    manager = multiprocessing.Manager()
    return_dict = manager.dict()

    # Split into strides per worker
    workers = []
    t0 = time.time()
    for w in range(num_workers):
        subset = all_proxies[w::num_workers]
        p = multiprocessing.Process(target=worker_process_func, args=(w, num_workers, subset, return_dict))
        workers.append(p)
        p.start()

    for p in workers:
        p.join()

    elapsed = time.time() - t0
    total_passed = sum(len(return_dict[w]) for w in range(num_workers))
    pass_rate = (total_passed / len(all_proxies)) * 100.0
    ips_s = len(all_proxies) / max(0.001, elapsed)

    print(f"[{num_workers} Workers Result]:", flush=True)
    print(f"  Tested    : {len(all_proxies)} proxies", flush=True)
    print(f"  Passed    : {total_passed} proxies", flush=True)
    print(f"  Pass Rate : {pass_rate:.2f}%", flush=True)
    print(f"  Elapsed   : {elapsed:.2f} seconds", flush=True)
    print(f"  Speed     : {ips_s:.1f} proxies/s", flush=True)

    return {
        "workers": num_workers,
        "tested": len(all_proxies),
        "passed": total_passed,
        "pass_rate": pass_rate,
        "elapsed": elapsed,
        "speed_ips_s": ips_s,
    }

def main():
    if not os.path.exists(KNOWN_GOOD_PATH):
        print(f"Missing {KNOWN_GOOD_PATH}!")
        return

    with open(KNOWN_GOOD_PATH) as f:
        proxies = [line.strip() for line in f if line.strip() and ":" in line]

    print("=" * 70, flush=True)
    print(f"SHARD PROBE LOAD BENCHMARK (500 KNOWN-GOOD PROXIES)", flush=True)
    print(f"Total proxies to test: {len(proxies)}", flush=True)
    print("=" * 70, flush=True)

    results = []

    # (1) 6 workers
    res_6 = run_test_suite(6, proxies)
    results.append(res_6)

    # (2) 2 workers
    res_2 = run_test_suite(2, proxies)
    results.append(res_2)

    # (3) 1 worker
    res_1 = run_test_suite(1, proxies)
    results.append(res_1)

    print("\n" + "=" * 70, flush=True)
    print("FINAL COMPARISON TABLE", flush=True)
    print("=" * 70, flush=True)
    print(f"{'Workers':<10} {'Passed':<12} {'Pass Rate':<12} {'Elapsed (s)':<14} {'Proxies/s':<12}", flush=True)
    print("-" * 70, flush=True)
    for r in results:
        print(f"{r['workers']:<10} {r['passed']:<12} {r['pass_rate']:<10.2f}% {r['elapsed']:<14.2f} {r['speed_ips_s']:<12.1f}", flush=True)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
