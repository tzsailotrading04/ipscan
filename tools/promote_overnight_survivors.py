"""
tools/promote_overnight_survivors.py
Strictly verifies candidate proxies added overnight:
- Multi-target probe: speed.cloudflare.com, www.google.com, one.one.one.one
- 5s timeout, ServerHello 0x16 check
- Appends verified survivors to ip/harvest/real_pool.txt
- Reports final true count in real_pool.txt
"""
import asyncio
import glob
import os
import socket
import ssl
import sys
import time

ROOT = r"D:\DEpinFarm"
REAL_POOL = os.path.join(ROOT, "ip", "harvest", "real_pool.txt")
IP_DIR = os.path.join(ROOT, "ip", "harvest")

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

async def verify_proxy(ip_port, sem):
    async with sem:
        try:
            ip, port_s = ip_port.split(":", 1)
            port = int(port_s)
        except Exception:
            return ip_port, False, None

        loop = asyncio.get_running_loop()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        try:
            await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=2.0)
        except Exception:
            try: s.close()
            except Exception: pass
            return ip_port, False, None

        if await inline_probe_connected(s, "speed.cloudflare.com", timeout=5.0):
            return ip_port, True, "speed.cloudflare.com"

        for t in ["www.google.com", "one.one.one.one"]:
            if await probe_single_target(ip, port, t, timeout=5.0):
                return ip_port, True, t

        return ip_port, False, None

async def main():
    print("=" * 70, flush=True)
    print("STRICT VERIFICATION & PROMOTION OF OVERNIGHT CANDIDATES", flush=True)
    print("=" * 70, flush=True)

    # 1. Load existing real_pool.txt
    existing_real = set()
    existing_lines = []
    if os.path.exists(REAL_POOL):
        with open(REAL_POOL, "r", encoding="utf-8", errors="ignore") as f:
            for l in f:
                line = l.strip()
                if line and ":" in line:
                    ip_port = line.split()[0].split("\t")[0]
                    existing_real.add(ip_port)
                    existing_lines.append(line)

    print(f"Current real_pool.txt count: {len(existing_real):,} proxies", flush=True)

    # 2. Extract overnight candidate lines
    overnight_cands = set()
    raw_lines_map = {}

    # All files in verified_alive_part_*.txt
    for f in glob.glob(os.path.join(IP_DIR, "verified_alive_part_*.txt")):
        with open(f, "r", encoding="utf-8", errors="ignore") as fp:
            for line in fp:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                # Overnight format: contains DATACENTER or RESIDENTIAL with tabs, or from worker/res files
                is_overnight = ("\tDATACENTER\t" in line or "\tRESIDENTIAL\t" in line or "_res" in f or "_w" in f)
                if is_overnight:
                    ip_port = line.split()[0].split("\t")[0]
                    if ip_port not in existing_real:
                        overnight_cands.add(ip_port)
                        if ip_port not in raw_lines_map:
                            raw_lines_map[ip_port] = line

    print(f"Total lines added to verified_alive_part_*.txt overnight: {len(overnight_cands):,} unpromoted candidates", flush=True)
    if not overnight_cands:
        print("No new overnight candidates to verify.", flush=True)
        return

    # 3. Strictly re-verify each candidate
    cands_list = sorted(overnight_cands)
    sem = asyncio.Semaphore(50)
    print(f"Strict-verifying {len(cands_list)} candidates with multi-target 0x16 probe (concurrency 50)...", flush=True)

    t0 = time.time()
    tasks = [verify_proxy(p, sem) for p in cands_list]
    results = await asyncio.gather(*tasks)

    survivors = []
    failed = 0
    for ip_port, passed, target in results:
        if passed:
            orig_line = raw_lines_map.get(ip_port, ip_port)
            survivors.append((ip_port, orig_line, target))
            print(f"  [PASS] {ip_port} verified via {target}", flush=True)
        else:
            failed += 1

    t_elapsed = time.time() - t0
    pass_rate = (len(survivors) / max(1, len(cands_list))) * 100.0
    print("-" * 70, flush=True)
    print(f"Verification complete in {t_elapsed:.1f}s:", flush=True)
    print(f"  Tested   : {len(cands_list):,}")
    print(f"  PASSED   : {len(survivors):,} ({pass_rate:.1f}%)")
    print(f"  FAILED   : {failed:,}")

    # 4. Promote survivors into real_pool.txt
    if survivors:
        new_promoted = 0
        with open(REAL_POOL, "a", encoding="utf-8") as fp:
            for ip_port, orig_line, target in survivors:
                if ip_port not in existing_real:
                    existing_real.add(ip_port)
                    fp.write(orig_line + "\n")
                    new_promoted += 1

        print(f"Promoted {new_promoted:,} fresh survivors into {REAL_POOL}", flush=True)

    # 5. Final deduplication and line count
    final_count = sum(1 for _ in open(REAL_POOL, errors="ignore"))
    print("=" * 70, flush=True)
    print(f"FINAL TRUE COUNT IN real_pool.txt: {final_count:,} genuine proxies", flush=True)
    print("=" * 70, flush=True)

if __name__ == "__main__":
    asyncio.run(main())
