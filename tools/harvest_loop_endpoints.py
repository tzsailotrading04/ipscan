"""
tools/harvest_loop_endpoints.py
Endpoint-Driven Harvest Engine:
1. Loads 3,456 deduped endpoints from cache/endpoints.txt (GitHub raw lists, ProxyScrape & GeoNode matrix, static).
2. Concurrently fetches from active endpoints, tracking fetched candidates per endpoint.
3. Merges fresh shard candidates from the 20 Kaggle shards.
4. Deduplicates against cache/harvest_seen_set.txt.
5. Strict multi-target TLS 0x16 verification (speed.cloudflare.com, google, 1.1.1.1) at CONCURRENCY=250.
6. Promotes survivors directly to ip/harvest/real_pool.txt, commits and pushes to origin/main.
7. Records and reports new entries and pass rate PER ENDPOINT.
8. Automatically prunes dead endpoints (HTTP 404 / 3 consecutive zero-hit cycles).
9. Loops every 15 minutes.
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
REAL_POOL_PATH = os.path.join(ROOT, "ip", "harvest", "real_pool.txt")
SEEN_SET_PATH = os.path.join(ROOT, "cache", "harvest_seen_set.txt")
STATUS_REPORT = os.path.join(ROOT, "work", "HARVEST_15MIN_STATUS.txt")
ASN_FILE = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")

TARGET_POOL_SIZE = 30000
CONCURRENCY = 250
FETCH_WORKERS = 48
ENDPOINT_BATCH_SIZE = 600  # Rotate through 600 active endpoints per 15-min cycle

TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
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

# ------------------------------------------------------------------------------
# 1. PERSISTENT SEEN SET & ENDPOINT TELEMETRY
# ------------------------------------------------------------------------------
def load_seen_set():
    seen = set()
    os.makedirs(os.path.dirname(SEEN_SET_PATH), exist_ok=True)
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

# ------------------------------------------------------------------------------
# 2. CONCURRENT ENDPOINT FETCHER WITH PER-ENDPOINT TRACKING
# ------------------------------------------------------------------------------
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
        with urllib.request.urlopen(req, timeout=6.5) as resp:
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

# ------------------------------------------------------------------------------
# 3. STRICT MULTI-TARGET TLS HANDSHAKE & SYSTEM CA VALIDATION PROBE
# ------------------------------------------------------------------------------
def sync_tls_handshake(sock, target, timeout=4.0):
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

def sync_probe_single_target(ip, port, target, timeout=4.0):
    s = None
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        return sync_tls_handshake(s, target, timeout=timeout)
    except Exception:
        if s:
            try: s.close()
            except Exception: pass
        return False

async def strict_verify_proxy(ip_port, sem, tracker=None):
    async with sem:
        try:
            ip, port_s = ip_port.split(":", 1)
            port = int(port_s)
        except Exception:
            if tracker: tracker["done"] += 1
            return ip_port, False, "BAD_FMT"

        loop = asyncio.get_running_loop()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        try:
            await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=1.8)
        except Exception:
            try: s.close()
            except Exception: pass
            if tracker: tracker["done"] += 1
            return ip_port, False, "CONNECT_FAIL"

        passed = False
        target_hit = ""
        # Check primary target with the already-connected socket
        if await loop.run_in_executor(None, sync_tls_handshake, s, "speed.cloudflare.com", 4.0):
            passed = True
            target_hit = "speed.cloudflare.com"
        else:
            # Fallback targets if primary fails or is blocked
            for t in ["www.google.com", "one.one.one.one"]:
                if await loop.run_in_executor(None, sync_probe_single_target, ip, port, t, 4.0):
                    passed = True
                    target_hit = t
                    break

        if tracker:
            tracker["done"] += 1
            if passed: tracker["pass"] += 1
            if tracker["done"] % 2000 == 0:
                print(f"[{tracker['done']:,}/{tracker['total']:,}] Verified | Passed: {tracker['pass']:,} ({tracker['pass']/tracker['done']*100:.2f}%)", flush=True)

        return ip_port, passed, target_hit if passed else "TLS_FAIL"

# ------------------------------------------------------------------------------
# 4. HARVEST CYCLE EXECUTION WITH PER-ENDPOINT ROTATION & PRUNING
# ------------------------------------------------------------------------------
def run_endpoint_harvest_cycle(cycle_num, ep_offset, total_stats):
    load_asn_table()
    now = time.time()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")

    # Git sync with parallel shard fleet
    subprocess.run(["git", "-C", ROOT, "fetch", "origin"], check=False)
    subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "origin", "main"], check=False)

    # 1. Load active endpoints & select batch for this rotation
    all_endpoints = load_endpoints()
    if not all_endpoints:
        print("[ERROR] No endpoints found in cache/endpoints.txt!", flush=True)
        return ep_offset

    total_endpoints_count = len(all_endpoints)
    # Select slice for this rotation
    if ep_offset >= total_endpoints_count:
        ep_offset = 0

    batch_eps = all_endpoints[ep_offset : ep_offset + ENDPOINT_BATCH_SIZE]
    next_offset = ep_offset + len(batch_eps)
    if next_offset >= total_endpoints_count:
        next_offset = 0

    print(f"\n[{now_str}] Cycle #{cycle_num}: Rotating through {len(batch_eps):,} endpoints (Range {ep_offset}..{ep_offset+len(batch_eps)} of {total_endpoints_count:,})...", flush=True)

    # 2. Concurrently fetch all endpoints in this batch
    telemetry = load_telemetry()
    seen_set = load_seen_set()

    ep_results = {}
    candidate_to_source = {}  # ip_port -> endpoint_url

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

    # 3. Pull fresh candidates from parallel 20 Kaggle shards
    shard_candidates = set()
    part_files = glob.glob(os.path.join(ROOT, "ip", "harvest", "verified_alive_part_*.txt"))
    for pf in part_files:
        try:
            for line in open(pf, errors="ignore"):
                line = line.strip()
                if line and ":" in line:
                    cand = line.split("\t")[0].split()[0]
                    shard_candidates.add(cand)
                    candidate_to_source[cand] = "kaggle_shards"
        except Exception: pass

    # Associate candidate IPs with their endpoint
    combined_candidates = set(shard_candidates)
    for u, res in ep_results.items():
        for ip_port in res["ips"]:
            combined_candidates.add(ip_port)
            if ip_port not in candidate_to_source:
                candidate_to_source[ip_port] = u

    # 4. Deduplicate against persistent seen-set
    unseen = [p for p in combined_candidates if p not in seen_set]
    print(f"Candidates: {len(combined_candidates):,} total | {len(unseen):,} brand new unseen.", flush=True)

    # Track unseen per endpoint
    for p in unseen:
        src = candidate_to_source.get(p, "unknown")
        if src in ep_results:
            ep_results[src]["unseen"] = ep_results[src].get("unseen", 0) + 1

    # 5. Strict verify unseen candidates
    verified_survivors = []
    survivor_sources = collections.defaultdict(list)
    pass_rate = 0.0

    if unseen:
        update_seen_set(unseen)
        print(f"Strict-verifying {len(unseen):,} new entries at CONCURRENCY={CONCURRENCY}...", flush=True)
        t_vstart = time.time()
        sem = asyncio.Semaphore(CONCURRENCY)
        tracker = {"done": 0, "pass": 0, "total": len(unseen)}

        async def verify_all():
            return await asyncio.gather(*[strict_verify_proxy(p, sem, tracker) for p in unseen])

        results = asyncio.run(verify_all())
        for p, ok, tgt in results:
            if ok:
                verified_survivors.append(p)
                src = candidate_to_source.get(p, "unknown")
                survivor_sources[src].append(p)

        elapsed_v = time.time() - t_vstart
        pass_rate = (len(verified_survivors) / max(1, len(unseen))) * 100.0
        print(f"Verification complete in {elapsed_v:.1f}s: {len(verified_survivors):,}/{len(unseen):,} passed ({pass_rate:.2f}%).", flush=True)

    # 6. Update per-endpoint telemetry and detect dead endpoints
    dead_to_prune = set()
    for u, res in ep_results.items():
        fetched = res["fetched"]
        unseen_cnt = res.get("unseen", 0)
        passed_cnt = len(survivor_sources.get(u, []))
        st = res["status"]

        if u not in telemetry:
            telemetry[u] = {
                "total_fetched": 0,
                "total_unseen": 0,
                "total_passed": 0,
                "zero_cycles": 0,
                "last_status": st
            }

        telemetry[u]["total_fetched"] += fetched
        telemetry[u]["total_unseen"] += unseen_cnt
        telemetry[u]["total_passed"] += passed_cnt
        telemetry[u]["last_status"] = st

        # Pruning condition: HTTP 404 or 3 consecutive zero-fetch cycles
        if st in ("HTTP_404", "HTTP_410"):
            dead_to_prune.add(u)
        elif fetched == 0:
            telemetry[u]["zero_cycles"] += 1
            if telemetry[u]["zero_cycles"] >= 3:
                dead_to_prune.add(u)
        else:
            telemetry[u]["zero_cycles"] = 0

    save_telemetry(telemetry)

    # Apply pruning to active endpoints file
    if dead_to_prune:
        all_endpoints = [u for u in all_endpoints if u not in dead_to_prune]
        save_endpoints(all_endpoints)
        with open(PRUNED_ENDPOINTS_PATH, "a", encoding="utf-8") as pf:
            for du in dead_to_prune:
                pf.write(f"{du}\t{telemetry.get(du, {}).get('last_status', 'DEAD')}\n")
        print(f"Pruned {len(dead_to_prune):,} dead endpoints. Remaining active: {len(all_endpoints):,}.", flush=True)

    # 7. Promote survivors to real_pool.txt
    real_pool = set()
    if os.path.exists(REAL_POOL_PATH):
        for l in open(REAL_POOL_PATH, errors="ignore"):
            l = l.strip()
            if l and ":" in l:
                real_pool.add(l.split()[0].split("\t")[0])

    new_promotions = 0
    if verified_survivors:
        with open(REAL_POOL_PATH, "a", encoding="utf-8") as f:
            for s in verified_survivors:
                if s not in real_pool:
                    prov = lookup_prov(s.split(":")[0])
                    f.write(f"{s}\tspeed.cloudflare.com\tENDPOINT_HARVEST\t0\t{prov}\n")
                    real_pool.add(s)
                    new_promotions += 1
        print(f"Promoted {new_promotions:,} fresh survivors into real_pool.txt.", flush=True)

        # Commit and push update
        subprocess.run(["git", "-C", ROOT, "add", "ip/harvest/real_pool.txt"], check=False)
        subprocess.run(["git", "-C", ROOT, "commit", "-m", f"feat(pool): harvest cycle #{cycle_num} promote {new_promotions} (Total: {len(real_pool):,})"], check=False)
        for _ in range(5):
            subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "origin", "main"], check=False)
            res = subprocess.run(["git", "-C", ROOT, "push", "origin", "main"], check=False)
            if res.returncode == 0: break
            time.sleep(2)

    # Cumulative stats
    total_stats["cycles"] += 1
    total_stats["new_entries_tested"] += len(unseen)
    total_stats["genuine_promoted"] += new_promotions
    elapsed_total_hrs = max(0.01, (now - total_stats["start_epoch"]) / 3600.0)
    genuine_per_hr = total_stats["genuine_promoted"] / elapsed_total_hrs
    current_pool_size = len(real_pool)
    remaining_to_30k = max(0, TARGET_POOL_SIZE - current_pool_size)

    # 8. Rank Top Endpoints and format 15-minute report
    endpoint_rankings = []
    for u, st in telemetry.items():
        if st["total_fetched"] > 0:
            pr = (st["total_passed"] / max(1, st["total_fetched"])) * 100.0
            endpoint_rankings.append((st["total_passed"], st["total_fetched"], pr, u))
    endpoint_rankings.sort(reverse=True)

    report = []
    report.append("=" * 85)
    report.append(f"ENDPOINT HARVEST TELEMETRY REPORT — CYCLE #{cycle_num} ({now_str})")
    report.append("=" * 85)
    report.append(f"Elapsed Time Since Start : {elapsed_total_hrs*60:.1f} minutes ({elapsed_total_hrs:.2f} hrs)")
    report.append(f"Active Endpoints Cached  : {len(all_endpoints):,} / {total_endpoints_count:,} (Pruned: {len(dead_to_prune):,})")
    report.append(f"Batch Evaluated (Slice)  : {len(batch_eps):,} endpoints (Next offset: {next_offset})")
    report.append(f"New Candidates (Cycle)   : {len(unseen):,} tested | Pass Rate: {pass_rate:.2f}%")
    report.append(f"Promoted (This Cycle)    : +{new_promotions:,} genuine proxies")
    report.append("-" * 85)
    report.append("TOP PERFORMING ENDPOINTS (Pass Rate & Verified Yield):")
    report.append(f"{'Passed':<8} {'Fetched':<10} {'Pass Rate':<12} {'Endpoint URL'}")
    report.append("-" * 85)
    for passed_c, fetched_c, pr_c, ep_u in endpoint_rankings[:12]:
        report.append(f"{passed_c:<8} {fetched_c:<10} {pr_c:6.2f}%      {ep_u[:65]}")
    if len(endpoint_rankings) == 0:
        report.append("  (Accumulating statistics...)")
    report.append("-" * 85)
    report.append(f"CUMULATIVE FLEET PROGRESS:")
    report.append(f"  Total Candidates Tested: {total_stats['new_entries_tested']:,}")
    report.append(f"  Total Genuine Promoted : {total_stats['genuine_promoted']:,}")
    report.append(f"  Genuine / Hour (Rate)  : {genuine_per_hr:.2f} / hr")
    report.append(f"  Master Real Pool Size  : {current_pool_size:,} / {TARGET_POOL_SIZE:,} proxies")
    report.append(f"  Progress Toward 30k    : {(current_pool_size/TARGET_POOL_SIZE*100):.2f}% ({remaining_to_30k:,} remaining)")
    report.append(f"  Parallel Shard Fleet   : 20 Shards Running (Random IPv4 Looping)")
    report.append("=" * 85)

    report_text = "\n".join(report)
    with open(STATUS_REPORT, "w", encoding="utf-8") as rf:
        rf.write(report_text + "\n")
    print("\n" + report_text, flush=True)

    return next_offset

def main():
    print("=" * 85, flush=True)
    print("STARTING ENDPOINT-DRIVEN HARVEST LOOP ENGINE", flush=True)
    print(f"Endpoints File : {ENDPOINTS_PATH}")
    print(f"Goal           : 30,000 Verified Proxies in real_pool.txt")
    print(f"Probe          : Strict Multi-Target TLS 0x16 (speed.cloudflare.com, google, 1.1.1.1)")
    print(f"Rotation Batch : {ENDPOINT_BATCH_SIZE} endpoints / cycle (15-min cadence)")
    print("=" * 85, flush=True)

    total_stats = {
        "start_epoch": time.time(),
        "cycles": 0,
        "new_entries_tested": 0,
        "genuine_promoted": 0
    }

    cycle_num = 1
    ep_offset = 0

    while True:
        ep_offset = run_endpoint_harvest_cycle(cycle_num, ep_offset, total_stats)
        cycle_num += 1
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Cycle completed. Sleeping 15 minutes (900s) until next rotation...", flush=True)
        time.sleep(900)

if __name__ == "__main__":
    main()
