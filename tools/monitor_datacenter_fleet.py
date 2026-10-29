"""
tools/monitor_datacenter_fleet.py
Monitors the Datacenter-Only Looping fleet:
- Pulls origin/main
- Extracts exact newly emitted candidates since deployment (e6f80cfef)
- Strictly verifies them with the multi-target 0x16 TLS probe
- Promotes genuine survivors to ip/harvest/real_pool.txt
- Computes genuine/hour vs 29.50/hr trial benchmark
- Calculates per-provider yield (genuine / 1,000 IPs)
- Flags providers with yield < 0.02 per 1,000 for pruning
- Writes work/DATACENTER_30MIN.txt and work/PRUNE_PROVIDERS.txt
"""
import asyncio
import collections
import glob
import json
import os
import socket
import ssl
import struct
import subprocess
import time
import bisect

ROOT = r"D:\DEpinFarm"
DEPLOY_COMMIT = "e6f80cfef"
DEPLOY_TIME_EPOCH = 1793256289.0 # 2026-10-29 12:14:49 Local / 06:44:49 UTC
REPORT_TXT = os.path.join(ROOT, "work", "DATACENTER_30MIN.txt")
PRUNE_TXT = os.path.join(ROOT, "work", "PRUNE_PROVIDERS.txt")
REAL_POOL_PATH = os.path.join(ROOT, "ip", "harvest", "real_pool.txt")
ASN_FILE = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")
HOST_FILE = os.path.join(ROOT, "data", "hosting_subnets.txt")
BASELINE_JSON = os.path.join(ROOT, "work", "datacenter_loop_baseline.json")

TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
CLIENT_HELLOS = {}
for _t in TARGETS:
    _ctx = ssl.create_default_context()
    _bio_in, _bio_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    _sslobj = _ctx.wrap_bio(_bio_in, _bio_out, server_hostname=_t)
    try: _sslobj.do_handshake()
    except ssl.SSLWantReadError: pass
    CLIENT_HELLOS[_t] = _bio_out.read()

# Load ASN table
asn_rows, asn_starts = [], []
def load_asn_table():
    global asn_rows, asn_starts
    if asn_starts: return
    if os.path.exists(ASN_FILE):
        rows = []
        with open(ASN_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) >= 5:
                    try: rows.append((int(p[0]), int(p[1]), p[4].upper().split()[0].strip(",.-")))
                    except ValueError: pass
        rows.sort()
        asn_starts = [r[0] for r in rows]
        asn_rows = rows

def lookup_prov(ip_str):
    if not asn_starts: return "UNKNOWN"
    try:
        u = struct.unpack("!I", socket.inet_aton(ip_str))[0]
        i = bisect.bisect_right(asn_starts, u) - 1
        if i >= 0 and asn_rows[i][0] <= u <= asn_rows[i][1]:
            return asn_rows[i][2]
    except Exception: pass
    return "UNKNOWN"

async def inline_probe_connected(s, target, timeout=5.0):
    try:
        loop = asyncio.get_running_loop()
        req = f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n".encode()
        await loop.sock_sendall(s, req)
        resp = b""
        t_end = time.monotonic() + timeout
        while b"\r\n\r\n" not in resp:
            if time.monotonic() > t_end: return False
            c = await asyncio.wait_for(loop.sock_recv(s, 512), timeout=timeout)
            if not c: return False
            resp += c
        first_line = resp.split(b"\r\n")[0]
        if not (resp.startswith(b"HTTP/") and (b" 200" in first_line or b" 2" in first_line)):
            return False
        parts = resp.split(b"\r\n\r\n", 1)
        trailing = parts[1] if len(parts) > 1 else b""
        if trailing: return trailing[:1] == b"\x16"
        await loop.sock_sendall(s, CLIENT_HELLOS[target])
        b1 = await asyncio.wait_for(loop.sock_recv(s, 1), timeout=timeout)
        return b1 == b"\x16"
    except Exception: return False
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
        except Exception: return ip_port, False, "BAD_FMT"

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

def run_monitor_cycle():
    load_asn_table()

    # Git fetch and pull latest
    subprocess.run(["git", "-C", ROOT, "fetch", "origin"], check=False)
    subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "origin", "main"], check=False)

    now = time.time()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    elapsed_total_hrs = max(0.01, (now - DEPLOY_TIME_EPOCH) / 3600.0)

    # 1. Calculate IPs scanned since deployment
    total_ips_scanned = 0
    worker_scanned = {}
    for s in range(20):
        stag = f"{s:02d}"
        for w in [0, 1]:
            wtag = f"{stag}_w{w}"
            r = subprocess.run(["git", "-C", ROOT, "show", f"{DEPLOY_COMMIT}:ip/harvest/shodan_progress_v98_{wtag}.txt"],
                               capture_output=True, text=True)
            base_off = 0
            if r.returncode == 0:
                for l in r.stdout.splitlines():
                    if l.strip().isdigit():
                        base_off = int(l.strip())
                        break
            
            cur_path = os.path.join(ROOT, "ip", "harvest", f"shodan_progress_v98_{wtag}.txt")
            cur_off = base_off
            if os.path.exists(cur_path):
                try:
                    for l in open(cur_path):
                        if l.strip().isdigit():
                            cur_off = int(l.strip())
                            break
                except Exception: pass
                
            diff = cur_off - base_off
            if diff < 0:
                diff += 1682944 # shard wrap
            if diff > 0:
                total_ips_scanned += diff
                worker_scanned[wtag] = diff

    # 2. Extract fresh candidates since deployment commit
    diff_res = subprocess.run(
        ["git", "-C", ROOT, "diff", DEPLOY_COMMIT, "HEAD", "--", "ip/harvest/verified_alive_part_*.txt"],
        capture_output=True, text=True
    )
    fresh_candidates = set()
    for l in diff_res.stdout.splitlines():
        if l.startswith("+") and not l.startswith("+++"):
            parts = l[1:].strip().split()
            if parts and ":" in parts[0]:
                ip_p = parts[0].split("\t")[0]
                fresh_candidates.add(ip_p)

    # Existing real pool
    real_pool = set()
    if os.path.exists(REAL_POOL_PATH):
        for l in open(REAL_POOL_PATH, errors="ignore"):
            l = l.strip()
            if l and ":" in l:
                real_pool.add(l.split()[0].split("\t")[0])

    unverified_fresh = [c for c in sorted(fresh_candidates) if c not in real_pool]

    # 3. Strictly verify newly found candidates
    verified_survivors = []
    if unverified_fresh:
        print(f"Strictly verifying {len(unverified_fresh)} unverified fresh candidates...")
        sem = asyncio.Semaphore(50)
        async def verify_all():
            return await asyncio.gather(*[strict_verify_proxy(p, sem) for p in unverified_fresh])
        res = asyncio.run(verify_all())
        verified_survivors = [p for p, ok, tgt in res if ok]
        print(f"Strict verification complete: {len(verified_survivors)}/{len(unverified_fresh)} passed.")

    # 4. Promote survivors to real_pool.txt
    if verified_survivors:
        added = 0
        with open(REAL_POOL_PATH, "a", encoding="utf-8") as f:
            for s in verified_survivors:
                if s not in real_pool:
                    prov = lookup_prov(s.split(":")[0])
                    f.write(f"{s}\tspeed.cloudflare.com\tDATACENTER\t0\t{prov}\n")
                    real_pool.add(s)
                    added += 1
        print(f"Promoted {added} new survivors to real_pool.txt (Total: {len(real_pool):,}).")

    # 5. Genuine proxies found in this run
    run_genuine_proxies = [c for c in fresh_candidates if c in real_pool]

    # Provider attribution breakdown
    prov_subnets = collections.Counter()
    if os.path.exists(HOST_FILE):
        with open(HOST_FILE) as f:
            for line in f:
                line = line.strip()
                if not line: continue
                parts = list(map(int, line.split(".")))
                u = (parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8)
                i = bisect.bisect_right(asn_starts, u) - 1
                p_name = asn_rows[i][2] if (i >= 0 and asn_rows[i][0] <= u <= asn_rows[i][1]) else "UNKNOWN"
                prov_subnets[p_name] += 1

    total_subnets = max(1, sum(prov_subnets.values()))

    # Count genuine survivors per provider found in this datacenter run
    prov_genuine_run = collections.Counter()
    for s in run_genuine_proxies:
        ip = s.split(":")[0]
        prov = lookup_prov(ip)
        prov_genuine_run[prov] += 1

    # Calculate per-provider yield
    provider_report = []
    prune_list = []

    for prov, subs in prov_subnets.most_common():
        pct_subnets = subs / total_subnets
        est_ips_scanned = total_ips_scanned * pct_subnets
        gen = prov_genuine_run.get(prov, 0)
        yield_1k = (gen / max(1, est_ips_scanned)) * 1000.0 if est_ips_scanned > 0 else 0.0

        is_prune = (est_ips_scanned >= 50000 and yield_1k < 0.02)
        status = "PRUNE (<0.02)" if is_prune else "KEEP"
        if is_prune:
            prune_list.append((prov, yield_1k, est_ips_scanned, gen))

        provider_report.append({
            "provider": prov,
            "subnets": subs,
            "est_ips_scanned": int(est_ips_scanned),
            "genuine_count": gen,
            "yield_per_1000": round(yield_1k, 6),
            "status": status,
        })

    # Fleet performance metrics
    genuine_per_hr = len(run_genuine_proxies) / elapsed_total_hrs if elapsed_total_hrs > 0 else 0.0
    overall_yield_1k = (len(run_genuine_proxies) / max(1, total_ips_scanned)) * 1000.0 if total_ips_scanned > 0 else 0.0
    scan_rate_ips = total_ips_scanned / (elapsed_total_hrs * 3600.0) if elapsed_total_hrs > 0 else 0.0

    # Write PRUNE_PROVIDERS.txt
    with open(PRUNE_TXT, "w", encoding="utf-8") as pf:
        pf.write(f"# Datacenter Looping: Providers Yielding < 0.02 per 1,000 IPs\n")
        pf.write(f"# Timestamp: {now_str} | Total Scanned: {total_ips_scanned:,} IPs\n")
        pf.write(f"# Format: PROVIDER | YIELD_PER_1K | EST_IPS_SCANNED | GENUINE_FOUND\n")
        pf.write("-" * 75 + "\n")
        if not prune_list:
            pf.write("None flagged for pruning yet (requires >= 50,000 IPs scanned).\n")
        else:
            for p, y, ips, g in prune_list:
                pf.write(f"{p:<20} | {y:.6f}/1k | {int(ips):,} IPs | {g} genuine\n")

    # Write DATACENTER_30MIN.txt
    with open(REPORT_TXT, "w", encoding="utf-8") as rf:
        rf.write("=" * 80 + "\n")
        rf.write(f"FLEET STATUS REPORT: DATACENTER-ONLY LOOPING ({now_str})\n")
        rf.write("=" * 80 + "\n")
        rf.write(f"Elapsed Time Since Start : {elapsed_total_hrs:.2f} hrs ({elapsed_total_hrs*60:.1f} mins)\n")
        rf.write(f"Total Datacenter IPs     : {total_ips_scanned:,} IPs\n")
        rf.write(f"Fleet Scan Rate          : {scan_rate_ips:,.0f} IPs/s\n")
        rf.write(f"Raw Candidates Emitted   : {len(fresh_candidates)} proxies\n")
        rf.write(f"Genuine Proxies in Run   : {len(run_genuine_proxies)} proxies\n")
        rf.write(f"Master Real Pool Total   : {len(real_pool):,} proxies\n")
        rf.write("-" * 80 + "\n")
        rf.write(f"Genuine / Hour (Actual)  : {genuine_per_hr:.2f} / hr\n")
        rf.write(f"Target Trial Benchmark   : 29.50 / hr\n")
        perf_diff = ((genuine_per_hr - 29.50) / 29.50) * 100.0 if 29.50 > 0 else 0.0
        rf.write(f"Performance vs Benchmark : {perf_diff:+.1f}%\n")
        rf.write(f"Overall Yield per 1,000  : {overall_yield_1k:.6f} / 1k\n")
        rf.write("-" * 80 + "\n")
        rf.write("PER-PROVIDER YIELD BREAKDOWN (Top 20 Providers by Subnet Share):\n")
        rf.write(f"{'Provider':<20} {'Subnets':<10} {'Est. Scanned':<16} {'Genuine':<10} {'Yield / 1k':<14} {'Status':<12}\n")
        rf.write("-" * 80 + "\n")
        for r in provider_report[:20]:
            rf.write(f"{r['provider']:<20} {r['subnets']:<10,} {r['est_ips_scanned']:<16,} {r['genuine_count']:<10} {r['yield_per_1000']:<14.6f} {r['status']:<12}\n")
        rf.write("=" * 80 + "\n")

    print("\n" + open(REPORT_TXT).read())

if __name__ == "__main__":
    run_monitor_cycle()
