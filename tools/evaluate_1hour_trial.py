"""
tools/evaluate_1hour_trial.py
Evaluates the 1-hour production trial (2 workers, batch 500):
- Pulls origin/main
- Compares candidates, offsets, and genuine yield against trial_2w_baseline.json
- Strictly verifies newly discovered candidates with the multi-target 0x16 probe
- Computes genuine-per-hour and genuine-per-1,000
- Compares against baseline targets:
  - Benchmark targets: 16 genuine/hr, 0.0004 per 1k
  - Recommends whether to keep 2 workers or revert to 6 workers
"""
import asyncio
import glob
import json
import os
import socket
import ssl
import subprocess
import time

ROOT = r"D:\DEpinFarm"
BASELINE_PATH = os.path.join(ROOT, "work", "trial_2w_baseline.json")
REPORT_PATH = os.path.join(ROOT, "work", "trial_1hour_report.json")

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
    print("=" * 70)
    print("1-HOUR PRODUCTION TRIAL EVALUATION (2 Workers, Batch 500)")
    print("=" * 70)

    if not os.path.exists(BASELINE_PATH):
        print(f"Error: Missing baseline file {BASELINE_PATH}!")
        return

    with open(BASELINE_PATH, "r", encoding="utf-8") as f:
        baseline = json.load(f)

    # Git fetch and pull latest shard commits
    print("Pulling latest commits from origin/main...")
    subprocess.run(["git", "-C", ROOT, "fetch", "origin"], check=False)
    subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "origin", "main"], check=False)

    now_epoch = time.time()
    elapsed_sec = now_epoch - baseline["start_epoch"]
    elapsed_hours = elapsed_sec / 3600.0

    # Current state
    part_files = glob.glob(os.path.join(ROOT, "ip", "harvest", "verified_alive_part_*.txt"))
    current_candidates = set()
    for pf in part_files:
        with open(pf, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line and ":" in line:
                    current_candidates.add(line.split()[0].split("\t")[0])

    # Calculate total offset
    prog_files = glob.glob(os.path.join(ROOT, "ip", "harvest", "shodan_progress_*.txt"))
    current_offset = 0
    for prog in prog_files:
        try:
            line = open(prog).readline().strip()
            if line.isdigit():
                current_offset += int(line)
        except Exception:
            pass

    delta_offset = max(0, current_offset - baseline["total_offset"])
    delta_cands_count = len(current_candidates) - baseline["unique_candidates"]

    # Load master pool to see what's already known
    real_pool_path = os.path.join(ROOT, "ip", "harvest", "real_pool.txt")
    known_pool = set(line.strip().split()[0].split("\t")[0] for line in open(real_pool_path, errors="ignore") if line.strip() and ":" in line)

    # Identify fresh candidates
    fresh_candidates = [c for c in current_candidates if c not in known_pool]

    print(f"\nElapsed Time          : {elapsed_sec:.1f} s ({elapsed_hours:.2f} hrs)")
    print(f"IPs Scanned in Trial  : {delta_offset:,}")
    print(f"Raw Candidates Found  : {len(fresh_candidates):,} fresh candidates")

    # Strict multi-target verification of fresh candidates
    verified_genuine = []
    if fresh_candidates:
        print(f"Strictly verifying {len(fresh_candidates)} fresh candidates...")
        sem = asyncio.Semaphore(100)
        async def run_all():
            return await asyncio.gather(*[strict_verify_proxy(c, sem) for c in fresh_candidates])
        res = asyncio.run(run_all())
        verified_genuine = [c for c, ok, tgt in res if ok]
    
    genuine_count = len(verified_genuine)
    genuine_per_hour = genuine_count / max(0.01, elapsed_hours)
    genuine_per_1000 = (genuine_count / max(1, delta_offset)) * 1000.0 if delta_offset > 0 else 0.0

    print("\n" + "=" * 70)
    print("1-HOUR TRIAL METRICS vs LAST NIGHT BASELINE")
    print("=" * 70)
    print(f"{'Metric':<30} {'Last Night (6W/B1500)':<22} {'Trial (2W/B500)':<20}")
    print("-" * 70)
    print(f"{'Genuine Found':<30} {'--':<22} {f'{genuine_count} proxies':<20}")
    print(f"{'Genuine / Hour':<30} {'16.0 / hr':<22} {f'{genuine_per_hour:.2f} / hr':<20}")
    print(f"{'Genuine / 1,000 IPs':<30} {'0.0004 / 1k':<22} {f'{genuine_per_1000:.6f} / 1k':<20}")
    print(f"{'IPs Scanned':<30} {'1,242,138,596':<22} {f'{delta_offset:,}':<20}")
    print("-" * 70)

    # Decision rule:
    # "If it does not beat 16/hr, revert to 6 workers."
    beats_baseline = genuine_per_hour >= 16.0
    action = "KEEP 2 WORKERS (Beats 16/hr)" if beats_baseline else "REVERT TO 6 WORKERS (Does not beat 16/hr)"
    print(f"\nDECISION: {action}")
    print("=" * 70)

    report = {
        "timestamp_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "elapsed_hours": round(elapsed_hours, 3),
        "ips_scanned": delta_offset,
        "raw_candidates_found": len(fresh_candidates),
        "genuine_verified": genuine_count,
        "genuine_per_hour": round(genuine_per_hour, 2),
        "genuine_per_1000": round(genuine_per_1000, 6),
        "last_night_per_hour": 16.0,
        "last_night_per_1000": 0.0004,
        "beats_16_per_hr": beats_baseline,
        "decision": action,
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report

if __name__ == "__main__":
    main()
