"""
tools/measure_trial_survivors.py
Finds and strictly verifies only the newly added candidate lines
produced during the 1-hour 2-worker trial.
"""
import asyncio
import glob
import json
import os
import socket
import ssl
import time

ROOT = r"D:\DEpinFarm"
BASELINE_PATH = os.path.join(ROOT, "work", "trial_2w_baseline.json")

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

async def strict_verify_proxy(ip_port, sem):
    async with sem:
        try:
            ip, port_s = ip_port.split(":", 1)
            port = int(port_s)
        except Exception:
            return ip_port, False, "BAD_FMT"

        loop = asyncio.get_running_loop()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        try:
            await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=1.8)
        except Exception:
            try: s.close()
            except Exception: pass
            return ip_port, False, "CONNECT_FAIL"

        if await inline_probe_connected(s, "speed.cloudflare.com", timeout=5.0):
            return ip_port, True, "speed.cloudflare.com"

        for t in ["www.google.com", "one.one.one.one"]:
            if await probe_single_target(ip, port, t, timeout=5.0):
                return ip_port, True, t

        return ip_port, False, "TLS_FAIL"

def main():
    with open(BASELINE_PATH, "r", encoding="utf-8") as f:
        baseline = json.load(f)

    # 1. Total IP offset calculation
    prog_files = glob.glob(os.path.join(ROOT, "ip", "harvest", "shodan_progress_*.txt"))
    current_offset = 0
    for prog in prog_files:
        try:
            line = open(prog).readline().strip()
            if line.isdigit():
                current_offset += int(line)
        except Exception:
            pass

    delta_ips = max(0, current_offset - baseline["total_offset"])
    elapsed_sec = time.time() - baseline["start_epoch"]
    elapsed_hours = elapsed_sec / 3600.0

    # 2. Extract git diff on verified_alive_part_*.txt since baseline commit
    # The baseline commit at trial start was f4fbe72938383d6d4a3ecfefcad67e52cf2fdfce
    # Let's inspect git log to find newly added candidate lines
    part_files = glob.glob(os.path.join(ROOT, "ip", "harvest", "verified_alive_part_*.txt"))
    current_candidates = {}
    for pf in part_files:
        with open(pf, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line and ":" in line:
                    parts = line.split("\t")
                    ip_port = parts[0]
                    prov = parts[4] if len(parts) >= 5 else "UNKNOWN"
                    current_candidates[ip_port] = (line, prov)

    # Find which ones are newly added since baseline
    # We know baseline had 185,479 unique candidates and 201,639 total lines.
    # Let's inspect git diff directly against baseline commit
    import subprocess
    cmd = ["git", "-C", ROOT, "diff", "f4fbe72938383d6d4a3ecfefcad67e52cf2fdfce", "HEAD", "--", "ip/harvest/verified_alive_part_*.txt"]
    res = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
    new_candidates = set()
    for line in res.stdout.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            l = line[1:].strip()
            if l and ":" in l:
                ip_p = l.split("\t")[0].split()[0]
                new_candidates.add(ip_p)

    print(f"=== 1-HOUR TRIAL ANALYSIS RESULTS ===")
    print(f"Elapsed Time           : {elapsed_sec:.1f} s ({elapsed_hours:.2f} hrs)")
    print(f"Total IPs Scanned      : {delta_ips:,} IPs")
    print(f"New Candidates Emitted : {len(new_candidates)} raw proxies")
    print("New candidates:", sorted(list(new_candidates)))

    # 3. Strictly verify the newly emitted candidates
    sem = asyncio.Semaphore(50)
    async def verify_batch():
        return await asyncio.gather(*[strict_verify_proxy(c, sem) for c in new_candidates])

    results = asyncio.run(verify_batch()) if new_candidates else []
    survivors = [c for c, ok, tgt in results if ok]
    failures = [(c, reason) for c, ok, reason in results if not ok]

    genuine_count = len(survivors)
    genuine_per_hour = genuine_count / max(0.01, elapsed_hours)
    genuine_per_1000 = (genuine_count / max(1, delta_ips)) * 1000.0 if delta_ips > 0 else 0.0

    print(f"\nStrict Verification Results:")
    print(f"  Tested    : {len(new_candidates)}")
    print(f"  Passed    : {genuine_count} ({genuine_count/max(1,len(new_candidates))*100:.1f}%)")
    print(f"  Failed    : {len(failures)}")
    for s in survivors:
        print(f"   [GENUINE SURVIVOR] {s}")

    print("\n" + "=" * 70)
    print("COMPARISON WITH BASELINE TARGETS")
    print("=" * 70)
    print(f"{'Metric':<25} {'Last Night (6W)':<20} {'1-Hour Trial (2W)':<20}")
    print("-" * 70)
    print(f"{'Genuine / Hour':<25} {'16.0 / hr':<20} {f'{genuine_per_hour:.2f} / hr':<20}")
    print(f"{'Genuine / 1,000 IPs':<25} {'0.0004 / 1k':<20} {f'{genuine_per_1000:.6f} / 1k':<20}")
    print(f"{'IPs Scanned in Window':<25} {'~124M / hr':<20} {f'{delta_ips:,}':<20}")
    print("-" * 70)

    beats_16 = genuine_per_hour >= 16.0
    print(f"DECISION: {'BEATS 16/HR -> KEEP 2 WORKERS' if beats_16 else 'DOES NOT BEAT 16/HR -> REVERT TO 6 WORKERS'}")
    print("=" * 70)

    report_out = {
        "elapsed_hours": elapsed_hours,
        "delta_ips": delta_ips,
        "new_candidates_count": len(new_candidates),
        "genuine_count": genuine_count,
        "genuine_per_hour": genuine_per_hour,
        "genuine_per_1000": genuine_per_1000,
        "survivors": survivors,
        "beats_16": beats_16
    }
    with open(os.path.join(ROOT, "work", "trial_1hour_report.json"), "w", encoding="utf-8") as f:
        json.dump(report_out, f, indent=2)

if __name__ == "__main__":
    main()
