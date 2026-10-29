"""
tools/run_15min_decision_trial.py
Snapshots trial start baseline, then at 15 minutes evaluates:
- Fresh candidates emitted during the 15-minute trial
- Strictly verifies them with multi-target TLS probe
- Promotes survivors to real_pool.txt
- Computes genuine found, genuine/hour vs 29.5 baseline, and yield per 1,000 IPs
"""
import argparse
import asyncio
import collections
import glob
import json
import os
import socket
import ssl
import struct
import subprocess
import sys
import time
import bisect

ROOT = r"D:\DEpinFarm"
TRIAL_STATE_JSON = os.path.join(ROOT, "work", "decision_trial_15min_state.json")
REPORT_TXT = os.path.join(ROOT, "work", "DECISION_TRIAL_15MIN.txt")
REAL_POOL_PATH = os.path.join(ROOT, "ip", "harvest", "real_pool.txt")
ASN_FILE = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")

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
    if not asn_starts: load_asn_table()
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

def start_trial():
    subprocess.run(["git", "-C", ROOT, "fetch", "origin"], check=False)
    subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "origin", "main"], check=False)
    
    res = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True)
    head_commit = res.stdout.strip()
    
    # Measure starting offsets
    worker_offsets = {}
    for s in range(20):
        stag = f"{s:02d}"
        for w in [0, 1]:
            wtag = f"{stag}_w{w}"
            cur_path = os.path.join(ROOT, "ip", "harvest", f"shodan_progress_v98_{wtag}.txt")
            cur_off = 0
            if os.path.exists(cur_path):
                try:
                    for l in open(cur_path):
                        if l.strip().isdigit():
                            cur_off = int(l.strip())
                            break
                except Exception: pass
            worker_offsets[wtag] = cur_off

    now = time.time()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    
    state = {
        "start_time_str": now_str,
        "start_epoch": now,
        "start_commit": head_commit,
        "worker_offsets": worker_offsets,
        "baseline_benchmark_hr": 29.50
    }
    
    os.makedirs(os.path.dirname(TRIAL_STATE_JSON), exist_ok=True)
    with open(TRIAL_STATE_JSON, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        
    print(f"[{now_str}] 15-MINUTE DECISION TRIAL STARTED")
    print(f"Start Commit    : {head_commit}")
    print(f"Tracking Workers: {len(worker_offsets)} worker streams across 20 shards")
    print(f"Benchmark Target: 29.50 genuine/hr")
    print(f"Trial finishes in exactly 15 minutes.")

def finish_trial():
    if not os.path.exists(TRIAL_STATE_JSON):
        print("ERROR: Trial state JSON not found.")
        sys.exit(1)
        
    with open(TRIAL_STATE_JSON, "r", encoding="utf-8") as f:
        state = json.load(f)
        
    subprocess.run(["git", "-C", ROOT, "fetch", "origin"], check=False)
    subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "origin", "main"], check=False)
    
    now = time.time()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    elapsed_sec = now - state["start_epoch"]
    elapsed_hrs = max(0.01, elapsed_sec / 3600.0)
    
    # 1. Calculate IPs scanned during trial
    total_ips_scanned = 0
    start_offsets = state["worker_offsets"]
    for s in range(20):
        stag = f"{s:02d}"
        for w in [0, 1]:
            wtag = f"{stag}_w{w}"
            base_off = start_offsets.get(wtag, 0)
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

    # 2. Extract fresh candidates emitted since start commit
    start_commit = state["start_commit"]
    diff_res = subprocess.run(
        ["git", "-C", ROOT, "diff", start_commit, "HEAD", "--", "ip/harvest/verified_alive_part_*.txt"],
        capture_output=True, text=True
    )
    fresh_candidates = set()
    for l in diff_res.stdout.splitlines():
        if l.startswith("+") and not l.startswith("+++"):
            parts = l[1:].strip().split()
            if parts and ":" in parts[0]:
                ip_p = parts[0].split("\t")[0]
                fresh_candidates.add(ip_p)

    # Load master real pool
    real_pool = set()
    if os.path.exists(REAL_POOL_PATH):
        for l in open(REAL_POOL_PATH, errors="ignore"):
            l = l.strip()
            if l and ":" in l:
                real_pool.add(l.split()[0].split("\t")[0])

    unverified_fresh = [c for c in sorted(fresh_candidates) if c not in real_pool]

    # 3. Strictly verify newly emitted candidates
    verified_survivors = []
    if unverified_fresh:
        print(f"Strictly verifying {len(unverified_fresh)} unverified fresh candidates...")
        sem = asyncio.Semaphore(50)
        async def verify_all():
            return await asyncio.gather(*[strict_verify_proxy(p, sem) for p in unverified_fresh])
        res = asyncio.run(verify_all())
        verified_survivors = [p for p, ok, tgt in res if ok]
        print(f"Strict verification complete: {len(verified_survivors)}/{len(unverified_fresh)} passed.")

    # 4. Promote survivors
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

    # Genuine proxies found in this 15-minute trial
    trial_genuine = [c for c in fresh_candidates if c in real_pool]
    genuine_found_count = len(trial_genuine)
    genuine_per_hr = genuine_found_count / elapsed_hrs if elapsed_hrs > 0 else 0.0
    yield_1k = (genuine_found_count / max(1, total_ips_scanned)) * 1000.0 if total_ips_scanned > 0 else 0.0
    scan_rate_ips = total_ips_scanned / elapsed_sec if elapsed_sec > 0 else 0.0
    benchmark = state.get("baseline_benchmark_hr", 29.50)
    perf_pct = ((genuine_per_hr - benchmark) / benchmark) * 100.0 if benchmark > 0 else 0.0

    report = []
    report.append("=" * 80)
    report.append(f"15-MINUTE DECISION TRIAL RESULTS ({now_str})")
    report.append("=" * 80)
    report.append(f"Trial Start Time         : {state['start_time_str']}")
    report.append(f"Trial End Time           : {now_str}")
    report.append(f"Duration                 : {elapsed_sec/60:.2f} minutes ({elapsed_hrs:.4f} hrs)")
    report.append(f"Total Datacenter IPs     : {total_ips_scanned:,} IPs")
    report.append(f"Fleet Scan Rate          : {scan_rate_ips:,.0f} IPs/s")
    report.append(f"Raw Candidates Emitted   : {len(fresh_candidates)} proxies")
    report.append(f"Genuine Proxies Found    : {genuine_found_count} proxies")
    report.append(f"Master Real Pool Total   : {len(real_pool):,} proxies")
    report.append("-" * 80)
    report.append(f"GENUINE / HOUR (TRIAL)   : {genuine_per_hr:.2f} / hr")
    report.append(f"TARGET 29.5 BASELINE     : {benchmark:.2f} / hr")
    report.append(f"PERFORMANCE VS BASELINE  : {perf_pct:+.1f}% {'(BEATS BASELINE)' if genuine_per_hr >= benchmark else '(BELOW BASELINE)'}")
    report.append(f"CONVERSION YIELD PER 1K  : {yield_1k:.6f} genuine / 1k IPs")
    report.append("=" * 80)

    report_text = "\n".join(report)
    with open(REPORT_TXT, "w", encoding="utf-8") as rf:
        rf.write(report_text + "\n")
    print("\n" + report_text)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", action="store_true", help="Start the 15-minute trial baseline")
    parser.add_argument("--finish", action="store_true", help="Finish the 15-minute trial and evaluate")
    args = parser.parse_args()
    
    if args.finish:
        finish_trial()
    else:
        start_trial()
