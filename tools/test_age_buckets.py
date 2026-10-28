"""
test_age_buckets.py
1. Maps 273,988 pool proxies to commit timestamps from git history.
2. Reports the age distribution across the whole pool:
   - under 1h
   - 1-3h
   - 3-6h
   - over 6h
3. Analyzes file ordering in backup_pool_20261028_182133.txt.
4. Samples up to 500 proxies per age bucket (total 2,000 proxies).
5. Strictly probes each bucket with multi-target probe (speed.cloudflare.com, www.google.com, one.one.one.one, 5s timeout, 0x16 ServerHello check).
6. Reports pass rate per bucket.
"""
import asyncio
import os
import random
import socket
import ssl
import subprocess
import time
from collections import Counter

ROOT = r"D:\DEpinFarm"
POOL_BACKUP = os.path.join(ROOT, "ip", "harvest", "backup_pool_20261028_182133.txt")

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

async def test_bucket(name, proxies, concurrency=40):
    print(f"\nTesting Bucket [{name}]: {len(proxies)} proxies...", flush=True)
    t0 = time.time()
    sem = asyncio.Semaphore(concurrency)
    tasks = []
    for p in proxies:
        ip, port_str = p.split(":")
        tasks.append(verify_proxy(ip, int(port_str), sem))
    results = await asyncio.gather(*tasks)
    passed = sum(1 for r in results if r)
    dt = time.time() - t0
    rate = (passed / max(1, len(proxies))) * 100
    print(f"Bucket [{name}]: {passed}/{len(proxies)} passed ({rate:.2f}%) in {dt:.1f}s ({len(proxies)/dt:.1f}/s)", flush=True)
    return {"bucket": name, "total": len(proxies), "passed": passed, "rate_pct": rate, "duration_sec": round(dt, 1)}

def extract_commit_times():
    print("Extracting commit timestamps from git log...", flush=True)
    t0 = time.time()
    cmd = ["git", "-C", ROOT, "log", "--format=COMMIT %ct", "-p", "--", "ip/harvest/verified_alive_part_*.txt"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, errors="ignore")

    proxy_time = {}
    curr_t = 0
    for line in proc.stdout:
        if line.startswith("COMMIT "):
            try:
                curr_t = int(line.split()[1])
            except Exception:
                pass
        elif line.startswith("+") and not line.startswith("+++"):
            parts = line[1:].strip().split()
            if parts and ":" in parts[0]:
                addr = parts[0]
                if addr not in proxy_time and curr_t > 0:
                    proxy_time[addr] = curr_t
    proc.wait()
    print(f"Extracted timestamps for {len(proxy_time):,} proxies in {time.time()-t0:.2f}s", flush=True)
    return proxy_time

async def main():
    proxy_time = extract_commit_times()

    # Load all unique proxies from backup
    all_proxies = []
    seen = set()
    with open(POOL_BACKUP, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            addr = line.split("\t")[0].split()[0]
            if ":" in addr and addr not in seen:
                seen.add(addr)
                all_proxies.append(addr)

    total_pool = len(all_proxies)
    print(f"Total Master Pool: {total_pool:,} unique proxies", flush=True)

    # File ordering inspection
    first_5 = all_proxies[:5]
    last_5 = all_proxies[-5:]
    print("\n--- File Ordering Check ---")
    print(f"First 5: {first_5}")
    print(f"Last 5:  {last_5}")

    # Determine age for each proxy
    # For proxies not in part files git log (e.g. from legacy verified_alive.txt), assign timestamp 24h ago
    now = time.time()
    bucket_lists = {
        "under 1h": [],
        "1-3h": [],
        "3-6h": [],
        "over 6h": []
    }

    for addr in all_proxies:
        ct = proxy_time.get(addr, now - 86400) # default > 24h old if not recent
        age_sec = now - ct
        if age_sec < 3600:
            bucket_lists["under 1h"].append(addr)
        elif age_sec < 3 * 3600:
            bucket_lists["1-3h"].append(addr)
        elif age_sec < 6 * 3600:
            bucket_lists["3-6h"].append(addr)
        else:
            bucket_lists["over 6h"].append(addr)

    print("\n" + "=" * 70)
    print("AGE DISTRIBUTION ACROSS ENTIRE 273,988 POOL:")
    for bname in ["under 1h", "1-3h", "3-6h", "over 6h"]:
        cnt = len(bucket_lists[bname])
        pct = (cnt / total_pool) * 100
        print(f"  {bname:<10}: {cnt:7,} proxies ({pct:5.2f}%)")
    print("=" * 70)

    # Sample 2,000 proxies across buckets
    random.seed(42)
    sample_sizes = {}
    # Take up to 500 from each bucket
    u1h_avail = len(bucket_lists["under 1h"])
    n_u1h = min(500, u1h_avail)
    remaining_needed = 2000 - n_u1h
    # Split remaining across other 3 buckets
    n_other = remaining_needed // 3

    samples = {}
    samples["under 1h"] = random.sample(bucket_lists["under 1h"], n_u1h)
    samples["1-3h"] = random.sample(bucket_lists["1-3h"], min(n_other, len(bucket_lists["1-3h"])))
    samples["3-6h"] = random.sample(bucket_lists["3-6h"], min(n_other, len(bucket_lists["3-6h"])))
    samples["over 6h"] = random.sample(bucket_lists["over 6h"], 2000 - len(samples["under 1h"]) - len(samples["1-3h"]) - len(samples["3-6h"]))

    total_sampled = sum(len(s) for s in samples.values())
    print(f"\nSampled {total_sampled:,} proxies across the 4 age buckets for strict verification test.")
    for bname, s in samples.items():
        print(f"  {bname:<10}: {len(s):,} proxies sampled")

    print("\n" + "=" * 70)
    print("STRICT MULTI-TARGET VERIFICATION BY AGE BUCKET (2,000 PROXIES)")
    print("=" * 70)

    results = []
    for bname in ["under 1h", "1-3h", "3-6h", "over 6h"]:
        r = await test_bucket(bname, samples[bname], concurrency=40)
        results.append(r)

    print("\n" + "=" * 70)
    print("SUMMARY: GENUINE PASS RATE BY COMMIT AGE:")
    print("=" * 70)
    for r in results:
        print(f"  {r['bucket']:<10}: {r['passed']:3,} passed / {r['total']:4,} tested -> {r['rate_pct']:5.2f}%")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
