"""
tools/harvest_loop_novelty.py
Novelty-Driven Harvest Engine (High-Performance Streaming):
1. Fresh endpoint rotation from 13,437 cached endpoints.
2. Alternate Port Scanning (8880, 8082, 8084, 8086, 8088, 8091, 8110, 8121, 8125-8139).
3. Strict cert-validating TLS probe (speed.cloudflare.com / www.google.com).
4. Strictly NOVEL survivors promoted to real_pool.txt (zero duplicates).
5. 2-cycle zero-addition pruning per endpoint.
6. Rate reporting: NEW-TO-POOL additions / hour.
"""
import asyncio
import bisect
import collections
import glob
import json
import os
import re
import socket
import ssl
import struct
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = r"D:\DEpinFarm"
ENDPOINTS_PATH = os.path.join(ROOT, "cache", "endpoints.txt")
PRUNED_ENDPOINTS_PATH = os.path.join(ROOT, "cache", "pruned_endpoints.txt")
TELEMETRY_PATH = os.path.join(ROOT, "cache", "endpoint_telemetry.json")
OFFSET_PATH = os.path.join(ROOT, "cache", "novelty_offset.json")
REAL_POOL_PATH = os.path.join(ROOT, "ip", "harvest", "real_pool.txt")
SEEN_SET_PATH = os.path.join(ROOT, "cache", "harvest_seen_set.txt")
STATUS_REPORT = os.path.join(ROOT, "work", "HARVEST_NOVELTY_STATUS.txt")
ASN_FILE = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")

CONCURRENCY = 400
FETCH_WORKERS = 48
BATCH_SIZE = 250  # 250 endpoints per cycle
MAX_UNSEEN_PER_CYCLE = 30000

# Alternate ports the lists don't carry
ALTERNATE_PORTS = [8880, 8082, 8084, 8086, 8088, 8091, 8110, 8121] + list(range(8125, 8140))

TARGETS = ["speed.cloudflare.com", "www.google.com"]
SSL_CTX = ssl.create_default_context()

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

def load_seen_set():
    seen = set()
    if os.path.exists(SEEN_SET_PATH):
        with open(SEEN_SET_PATH, "r", encoding="utf-8", errors="ignore") as f:
            for l in f:
                l = l.strip()
                if l and ":" in l:
                    seen.add(l.split()[0].split("\t")[0])
    if os.path.exists(REAL_POOL_PATH):
        with open(REAL_POOL_PATH, "r", encoding="utf-8", errors="ignore") as f:
            for l in f:
                l = l.strip()
                if l and ":" in l:
                    seen.add(l.split()[0].split("\t")[0])
    return seen

def update_seen_set(new_entries):
    os.makedirs(os.path.dirname(SEEN_SET_PATH), exist_ok=True)
    with open(SEEN_SET_PATH, "a", encoding="utf-8") as f:
        for p in new_entries:
            f.write(f"{p}\n")

def load_telemetry():
    if os.path.exists(TELEMETRY_PATH):
        try:
            with open(TELEMETRY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception: pass
    return {}

def save_telemetry(telem):
    os.makedirs(os.path.dirname(TELEMETRY_PATH), exist_ok=True)
    with open(TELEMETRY_PATH, "w", encoding="utf-8") as f:
        json.dump(telem, f, indent=2)

def load_endpoints():
    if not os.path.exists(ENDPOINTS_PATH):
        return []
    with open(ENDPOINTS_PATH, "r", encoding="utf-8", errors="ignore") as f:
        return [l.strip() for l in f if l.strip()]

def save_endpoints(ep_list):
    with open(ENDPOINTS_PATH, "w", encoding="utf-8") as f:
        for u in ep_list:
            f.write(f"{u}\n")

def load_offset():
    if os.path.exists(OFFSET_PATH):
        try:
            with open(OFFSET_PATH, "r") as f:
                return json.load(f).get("offset", 3300)
        except Exception: pass
    return 3300

def save_offset(off):
    with open(OFFSET_PATH, "w") as f:
        json.dump({"offset": off}, f)

def fetch_single_endpoint(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/plain,text/html,application/json,*/*"
        }
    )
    found_ips = set()
    status = "OK"
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
            # If GeoNode JSON format
            if "proxylist.geonode.com" in url:
                try:
                    data = json.loads(text)
                    for item in data.get("data", []):
                        ip, port = item.get("ip"), item.get("port")
                        if ip and port: found_ips.add(f"{ip}:{port}")
                except Exception: pass
            # Match standard IP:PORT
            matches = re.findall(r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?):(?:\d{2,5})\b", text)
            for m in matches:
                found_ips.add(m)
    except urllib.error.HTTPError as he:
        status = f"HTTP_{he.code}"
    except Exception as e:
        status = f"ERR_{type(e).__name__}"
    return url, found_ips, status

def sync_tls_handshake(sock, target, timeout=3.5):
    try:
        sock.setblocking(True)
        sock.settimeout(timeout)
        req = f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n".encode()
        sock.sendall(req)
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = sock.recv(512)
            if not chunk: return False
            resp += chunk
            if len(resp) > 2048: return False
        first_line = resp.split(b"\r\n")[0]
        if not (b" 200" in first_line or b"HTTP/1.1 200" in first_line or b"HTTP/1.0 200" in first_line):
            return False
        # Full TLS handshake + System CA chain validation
        ss = SSL_CTX.wrap_socket(sock, server_hostname=target)
        ss.settimeout(timeout)
        ss.do_handshake()
        _ = ss.getpeercert()
        ss.close()
        return True
    except Exception:
        try: sock.close()
        except Exception: pass
        return False

def sync_probe_single_target(ip, port, target, timeout=3.5):
    s = None
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        return sync_tls_handshake(s, target, timeout=timeout)
    except Exception:
        if s:
            try: s.close()
            except Exception: pass
        return False

async def worker(queue, tracker, results):
    loop = asyncio.get_running_loop()
    while True:
        try:
            ip_port = queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        try:
            ip, port_s = ip_port.split(":", 1)
            port = int(port_s)
        except Exception:
            tracker["done"] += 1
            queue.task_done()
            continue

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        try:
            await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=1.5)
        except Exception:
            try: s.close()
            except Exception: pass
            tracker["done"] += 1
            queue.task_done()
            continue

        passed = False
        target_hit = ""
        # Check primary target (speed.cloudflare.com)
        if await loop.run_in_executor(None, sync_tls_handshake, s, "speed.cloudflare.com", 3.5):
            passed = True
            target_hit = "speed.cloudflare.com"
        else:
            # Fallback target (www.google.com)
            if await loop.run_in_executor(None, sync_probe_single_target, ip, port, "www.google.com", 3.5):
                passed = True
                target_hit = "www.google.com"

        tracker["done"] += 1
        if passed:
            tracker["pass"] += 1
            results.append((ip_port, True, target_hit))

        if tracker["done"] % 2500 == 0:
            print(f"  [{tracker['done']:,}/{tracker['total']:,}] Checked | Passed: {tracker['pass']:,} ({tracker['pass']/max(1,tracker['done'])*100:.2f}%)", flush=True)

        queue.task_done()

def run_novelty_cycle(cycle_num, ep_offset, start_time, cumulative_added):
    load_asn_table()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")

    # 1. Load active endpoints
    all_endpoints = load_endpoints()
    if not all_endpoints:
        print("[ERROR] No endpoints found in cache/endpoints.txt!", flush=True)
        return ep_offset, cumulative_added

    total_endpoints_count = len(all_endpoints)
    if ep_offset >= total_endpoints_count:
        ep_offset = 0

    batch_eps = all_endpoints[ep_offset : ep_offset + BATCH_SIZE]
    next_offset = ep_offset + len(batch_eps)
    if next_offset >= total_endpoints_count:
        next_offset = 0
    save_offset(next_offset)

    print(f"\n=====================================================================================", flush=True)
    print(f"[{now_str}] NOVELTY HARVEST CYCLE #{cycle_num}", flush=True)
    print(f"Evaluating batch of {len(batch_eps):,} endpoints (Range {ep_offset}..{ep_offset+len(batch_eps)} of {total_endpoints_count:,})", flush=True)
    print(f"=====================================================================================", flush=True)

    # 2. Concurrently fetch all endpoints in this batch
    telemetry = load_telemetry()
    seen_set = load_seen_set()

    ep_results = {}
    candidate_to_source = {}
    candidate_is_alt_port = {}

    t_fetch_start = time.time()
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        futures = [pool.submit(fetch_single_endpoint, u) for u in batch_eps]
        for f in futures:
            try:
                u, ips, status = f.result()
                ep_results[u] = {"fetched": len(ips), "status": status, "ips": ips}
            except Exception: pass
    elapsed_fetch = time.time() - t_fetch_start
    print(f"Fetched {len(batch_eps):,} endpoints in {elapsed_fetch:.1f}s.", flush=True)

    # 3. Alternate Port Scanning (Requirement 3: scan 8880, 8082, 8084, 8086, 8088, 8091, 8110, 8121, 8125-8139)
    combined_candidates = []
    distinct_hosts = {}

    for u, res in ep_results.items():
        for ip_port in res["ips"]:
            if ip_port not in seen_set:
                combined_candidates.append(ip_port)
                if ip_port not in candidate_to_source:
                    candidate_to_source[ip_port] = u
                    candidate_is_alt_port[ip_port] = False
            try:
                h_ip = ip_port.split(":")[0]
                if h_ip not in distinct_hosts:
                    distinct_hosts[h_ip] = u
            except Exception: pass

    # Expand newly discovered host IPs with unindexed alternate ports
    alt_port_count = 0
    for h_ip, src_u in list(distinct_hosts.items())[:600]:
        for port in ALTERNATE_PORTS:
            alt_ip_port = f"{h_ip}:{port}"
            if alt_ip_port not in seen_set and alt_ip_port not in candidate_to_source:
                combined_candidates.append(alt_ip_port)
                candidate_to_source[alt_ip_port] = src_u
                candidate_is_alt_port[alt_ip_port] = True
                alt_port_count += 1

    # Deduplicate candidate list
    unseen_set = set()
    unseen = []
    for cand in combined_candidates:
        if cand not in unseen_set and cand not in seen_set:
            unseen_set.add(cand)
            unseen.append(cand)
        if len(unseen) >= MAX_UNSEEN_PER_CYCLE:
            break

    print(f"Candidates to verify: {len(unseen):,} ({alt_port_count:,} alternate ports tested across {min(len(distinct_hosts), 600):,} hosts).", flush=True)

    # 4. Strict cert-validating probe with streaming queue
    verified_survivors = []
    survivor_sources = collections.defaultdict(list)
    alt_port_survivors = 0

    if unseen:
        update_seen_set(unseen)
        print(f"Streaming {len(unseen):,} candidates across {CONCURRENCY} workers...", flush=True)
        t_vstart = time.time()
        
        async def main_verify():
            q = asyncio.Queue()
            for p in unseen:
                q.put_nowait(p)
            tracker = {"done": 0, "pass": 0, "total": len(unseen)}
            results = []
            tasks = [asyncio.create_task(worker(q, tracker, results)) for _ in range(CONCURRENCY)]
            await asyncio.gather(*tasks)
            return results

        results = asyncio.run(main_verify())
        for p, ok, tgt in results:
            if ok:
                verified_survivors.append(p)
                src = candidate_to_source.get(p, "unknown")
                survivor_sources[src].append(p)
                if candidate_is_alt_port.get(p, False):
                    alt_port_survivors += 1

        elapsed_v = time.time() - t_vstart
        print(f"Verification completed in {elapsed_v:.1f}s: {len(verified_survivors):,} NEW survivors ({alt_port_survivors} via alternate ports).", flush=True)

    # 5. Append genuinely new survivors to real_pool.txt (Duplicates strictly prevented)
    new_additions_count = len(verified_survivors)
    cumulative_added += new_additions_count

    if verified_survivors:
        existing_pool_ips = set()
        if os.path.exists(REAL_POOL_PATH):
            with open(REAL_POOL_PATH, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and ":" in line:
                        existing_pool_ips.add(line.split("\t")[0].split()[0])

        with open(REAL_POOL_PATH, "a", encoding="utf-8") as f:
            for p in verified_survivors:
                if p not in existing_pool_ips:
                    ip_only = p.split(":")[0]
                    prov = lookup_prov(ip_only)
                    f.write(f"{p}\tspeed.cloudflare.com\t{prov}\n")
                    existing_pool_ips.add(p)

    # 6. Endpoint Telemetry & 2-Cycle Zero-Addition Pruning (Requirement 5)
    dead_to_prune = set()
    endpoint_report_rows = []

    for u, res in ep_results.items():
        fetched = res["fetched"]
        new_passed = len(survivor_sources.get(u, []))
        st = res["status"]

        if u not in telemetry:
            telemetry[u] = {
                "total_fetched": 0,
                "total_new_added": 0,
                "zero_cycles": 0,
                "last_status": st
            }

        telemetry[u]["total_fetched"] += fetched
        telemetry[u]["last_status"] = st

        if new_passed > 0:
            telemetry[u]["total_new_added"] = telemetry[u].get("total_new_added", 0) + new_passed
            telemetry[u]["zero_cycles"] = 0
            ep_state = "ACTIVE (SURVIVOR)"
        else:
            telemetry[u]["zero_cycles"] = telemetry[u].get("zero_cycles", 0) + 1
            if telemetry[u]["zero_cycles"] >= 2 or st in ("HTTP_404", "HTTP_410"):
                dead_to_prune.add(u)
                ep_state = "PRUNED"
            else:
                ep_state = "WARNING (0/2)"

        endpoint_report_rows.append({
            "url": u,
            "fetched": fetched,
            "new_added": new_passed,
            "zero_cycles": telemetry[u]["zero_cycles"],
            "state": ep_state
        })

    # Save telemetry
    save_telemetry(telemetry)

    # Prune endpoints adding zero after two cycles
    if dead_to_prune:
        remaining_eps = [u for u in all_endpoints if u not in dead_to_prune]
        save_endpoints(remaining_eps)
        os.makedirs(os.path.dirname(PRUNED_ENDPOINTS_PATH), exist_ok=True)
        with open(PRUNED_ENDPOINTS_PATH, "a", encoding="utf-8") as f:
            for u in dead_to_prune:
                f.write(f"{u}\n")
        print(f"Pruned {len(dead_to_prune):,} endpoints adding zero after 2 cycles. Active endpoints: {len(remaining_eps):,}", flush=True)

    # 7. Calculate NEW-TO-POOL Rate Per Hour (Requirement 4)
    elapsed_total_hrs = max(0.001, (time.time() - start_time) / 3600.0)
    additions_per_hour = cumulative_added / elapsed_total_hrs

    # Read current real_pool.txt count
    current_pool_count = 0
    if os.path.exists(REAL_POOL_PATH):
        with open(REAL_POOL_PATH, "r", encoding="utf-8", errors="ignore") as f:
            current_pool_count = sum(1 for line in f if line.strip() and ":" in line)

    endpoint_report_rows.sort(key=lambda r: (r["new_added"], r["fetched"]), reverse=True)

    report_lines = [
        "=====================================================================================",
        f"NOVELTY-DRIVEN HARVEST TELEMETRY REPORT — CYCLE #{cycle_num} ({now_str})",
        "=====================================================================================",
        f"Elapsed Harvest Time     : {elapsed_total_hrs*60.0:.1f} minutes ({elapsed_total_hrs:.2f} hrs)",
        f"Active Endpoints Cached  : {len(all_endpoints) - len(dead_to_prune):,} (Pruned This Cycle: {len(dead_to_prune):,})",
        f"Batch Evaluated (Slice)  : {len(batch_eps):,} endpoints (Offset: {ep_offset})",
        f"Unseen Candidates Probed : {len(unseen):,} (Alternate Ports Tested: {alt_port_count:,})",
        f"NEW-TO-POOL (This Cycle) : +{new_additions_count:,} genuine survivors ({alt_port_survivors} via alternate ports)",
        f"NEW-TO-POOL ADDITION RATE: {additions_per_hour:.2f} genuine IPs / hour",
        f"CURRENT REAL POOL COUNT  : {current_pool_count:,} verified proxies",
        "-------------------------------------------------------------------------------------",
        "PER-ENDPOINT CONTRIBUTION (NEW IPs Added & Pruning Status):",
        f"{'Added':<7} {'Fetched':<9} {'ZeroCycles':<12} {'State':<18} {'Endpoint URL'}",
        "-------------------------------------------------------------------------------------"
    ]
    for r in endpoint_report_rows[:35]:
        u_trunc = r["url"] if len(r["url"]) <= 62 else r["url"][:59] + "..."
        report_lines.append(f"{r['new_added']:<7} {r['fetched']:<9} {r['zero_cycles']:<12} {r['state']:<18} {u_trunc}")

    report_lines.append("=====================================================================================")
    report_text = "\n".join(report_lines)

    os.makedirs(os.path.dirname(STATUS_REPORT), exist_ok=True)
    with open(STATUS_REPORT, "w", encoding="utf-8") as f:
        f.write(report_text)

    print("\n" + report_text, flush=True)

    return next_offset, cumulative_added

if __name__ == "__main__":
    start_time = time.time()
    offset = load_offset()
    cum_added = 0
    # Run cycle 1
    offset, cum_added = run_novelty_cycle(1, offset, start_time, cum_added)
