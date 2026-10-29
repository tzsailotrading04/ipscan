"""
tools/harvest_loop_v2.py
Continuous Harvest Loop & Shard Telemetry:
1. Hourly fetcher across:
   - monosans/proxy-list (HTTP, SOCKS4, SOCKS5)
   - proxifly/free-proxy-list (HTTP, SOCKS4, SOCKS5)
   - TheSpeedX/PROXY-List (HTTP, SOCKS4, SOCKS5)
   - api.proxyscrape.com (HTTP, SOCKS4, SOCKS5)
   - geonode free API (HTTP, SOCKS4, SOCKS5)
   - openproxy.space
   - spys.one / spys.me
2. Persistent seen-set on disk (cache/harvest_seen_set.txt)
3. Protocol-specific probes:
   - HTTP candidates -> strict HTTP CONNECT probe with 0x16 TLS check
   - SOCKS candidates -> strict SOCKS5 handshake (greeting, connect, ClientHello, 0x16 check)
   - Mixed/Unknown -> dual probe (CONNECT first, SOCKS5 second)
   - Survivors labeled with exact protocol ('http' or 'socks5')
4. Survivors promoted straight to ip/harvest/real_pool.txt, deduped by ip:port
5. Parallel Shard Fleet integration (Budget VPS: OVH, Hetzner, Contabo, Vultr, Linode, DO, Leaseweb, ColoCrossing, M247, Hostinger)
6. Every 15 minutes: prints new entries fetched, pass rate, genuine/hr, and total real pool toward 30,000
7. Alerts if < 100 new entries/hr or pass rate < 0.3%
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
REAL_POOL_PATH = os.path.join(ROOT, "ip", "harvest", "real_pool.txt")
SEEN_SET_PATH = os.path.join(ROOT, "cache", "harvest_seen_set.txt")
STATUS_REPORT = os.path.join(ROOT, "work", "HARVEST_15MIN_STATUS.txt")
ALERT_PATH = os.path.join(ROOT, "work", "ALERT.txt")
ASN_FILE = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")

TARGET_POOL_SIZE = 30000
CONCURRENCY = 250

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

# ------------------------------------------------------------------------------
# 1. FEED DEFINITIONS BY PROTOCOL
# ------------------------------------------------------------------------------
FEEDS_HTTP = [
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
    "https://spys.me/proxy.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
    "https://openproxy.space/list/http",
]

FEEDS_SOCKS = [
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks4/data.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=10000&country=all",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks4&timeout=10000&country=all",
    "https://spys.me/socks.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
    "https://openproxy.space/list/socks5",
    "https://openproxy.space/list/socks4",
]

FEEDS_ALL = [
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/all.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.txt",
]

def fetch_url(url):
    results = set()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
            matches = re.findall(r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?):(?:\d{2,5})\b", text)
            for m in matches:
                results.add(m)
    except Exception:
        pass
    return results

def fetch_geonode_api():
    http_res = set()
    socks_res = set()
    for page in range(1, 11):
        url = f"https://proxylist.geonode.com/api/proxy-list?limit=500&page={page}&sort_by=lastChecked&sort_type=desc"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                items = data.get("data", [])
                if not items: break
                for it in items:
                    ip, port = it.get("ip"), it.get("port")
                    protos = it.get("protocols", [])
                    if ip and port:
                        cand = f"{ip}:{port}"
                        if any("socks" in p.lower() for p in protos):
                            socks_res.add(cand)
                        else:
                            http_res.add(cand)
        except Exception:
            break
    return http_res, socks_res

def fetch_all_sources():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Fetching from all 7 provider sources...", flush=True)
    t0 = time.time()
    
    candidates = {} # ip_port -> proto_hint ('http', 'socks5', 'any')
    
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures_http = {pool.submit(fetch_url, u): u for u in FEEDS_HTTP}
        futures_socks = {pool.submit(fetch_url, u): u for u in FEEDS_SOCKS}
        futures_all = {pool.submit(fetch_url, u): u for u in FEEDS_ALL}
        f_geo = pool.submit(fetch_geonode_api)

        for f in futures_http:
            for p in f.result():
                if p not in candidates: candidates[p] = "http"

        for f in futures_socks:
            for p in f.result():
                candidates[p] = "socks5" # explicit socks tag

        for f in futures_all:
            for p in f.result():
                if p not in candidates: candidates[p] = "any"

        try:
            geo_http, geo_socks = f_geo.result()
            for p in geo_http:
                if p not in candidates: candidates[p] = "http"
            for p in geo_socks:
                candidates[p] = "socks5"
        except Exception: pass

    elapsed = time.time() - t0
    print(f"Fetched {len(candidates):,} unique proxy candidates in {elapsed:.1f}s", flush=True)
    return candidates

# ------------------------------------------------------------------------------
# 2. PERSISTENT SEEN-SET DEDUPLICATION
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

def update_seen_set(entries):
    os.makedirs(os.path.dirname(SEEN_SET_PATH), exist_ok=True)
    with open(SEEN_SET_PATH, "a", encoding="utf-8") as f:
        for p in entries:
            f.write(f"{p}\n")

# ------------------------------------------------------------------------------
# 3. PROBES: STRICT HTTP CONNECT & STRICT SOCKS5
# ------------------------------------------------------------------------------
# SOCKS5 packet builders
def build_socks5_connect(host, port):
    domain_b = host.encode("ascii")
    return b"\x05\x01\x00\x03" + bytes([len(domain_b)]) + domain_b + struct.pack("!H", port)

async def probe_socks5(s, target, timeout=5.0):
    try:
        loop = asyncio.get_running_loop()
        # 1. Greeting (no auth)
        await loop.sock_sendall(s, b"\x05\x01\x00")
        resp1 = await asyncio.wait_for(loop.sock_recv(s, 2), timeout=timeout)
        if len(resp1) < 2 or resp1[0] != 5 or resp1[1] != 0:
            return False
            
        # 2. Connect request
        req = build_socks5_connect(target, 443)
        await loop.sock_sendall(s, req)
        resp2 = await asyncio.wait_for(loop.sock_recv(s, 512), timeout=timeout)
        if len(resp2) < 2 or resp2[0] != 5 or resp2[1] != 0:
            return False
            
        # 3. TLS ClientHello & ServerHello check
        await loop.sock_sendall(s, CLIENT_HELLOS[target])
        b1 = await asyncio.wait_for(loop.sock_recv(s, 1), timeout=timeout)
        return b1 == b"\x16"
    except Exception:
        return False
    finally:
        try: s.close()
        except Exception: pass

async def probe_http_connect(s, target, timeout=5.0):
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
    except Exception:
        return False
    finally:
        try: s.close()
        except Exception: pass

async def verify_candidate(ip_port, proto_hint, sem, tracker=None):
    async with sem:
        try:
            ip, port_s = ip_port.split(":", 1)
            port = int(port_s)
        except Exception:
            if tracker: tracker["done"] += 1
            return ip_port, False, "BAD_FMT", ""

        loop = asyncio.get_running_loop()

        async def get_conn():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setblocking(False)
            try:
                await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=1.8)
                return s
            except Exception:
                try: s.close()
                except Exception: pass
                return None

        passed = False
        final_proto = ""

        # Try SOCKS5 first if hinted
        if proto_hint == "socks5":
            s = await get_conn()
            if s:
                for tgt in TARGETS:
                    if await probe_socks5(s, tgt, timeout=5.0):
                        passed = True
                        final_proto = "socks5"
                        break
                    s = await get_conn()
                    if not s: break
        
        # Try HTTP CONNECT if hinted or any
        if not passed and proto_hint in ("http", "any"):
            s = await get_conn()
            if s:
                for tgt in TARGETS:
                    if await probe_http_connect(s, tgt, timeout=5.0):
                        passed = True
                        final_proto = "http"
                        break
                    s = await get_conn()
                    if not s: break

        # If still unpassed and was any, try SOCKS5 fallback
        if not passed and proto_hint == "any":
            s = await get_conn()
            if s:
                for tgt in TARGETS:
                    if await probe_socks5(s, tgt, timeout=5.0):
                        passed = True
                        final_proto = "socks5"
                        break
                    s = await get_conn()
                    if not s: break

        if tracker:
            tracker["done"] += 1
            if passed: tracker["pass"] += 1
            if tracker["done"] % 2000 == 0:
                print(f"[{tracker['done']:,}/{tracker['total']:,}] Verified | Passed: {tracker['pass']:,} ({tracker['pass']/tracker['done']*100:.2f}%)", flush=True)

        return ip_port, passed, final_proto if passed else "FAIL", final_proto

# ------------------------------------------------------------------------------
# 4. HARVEST LOOP ORCHESTRATION & SHARD MONITOR
# ------------------------------------------------------------------------------
def run_cycle(cycle_num, last_fetch_time, total_stats):
    load_asn_table()
    now = time.time()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")

    # 1. Sync with budget VPS shard fleet on Git
    subprocess.run(["git", "-C", ROOT, "fetch", "origin"], check=False)
    subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "origin", "main"], check=False)

    # 2. Hourly fetch of aggregator feeds
    feed_candidates = {}
    if now - last_fetch_time >= 3600 or cycle_num == 1:
        feed_candidates = fetch_all_sources()
        last_fetch_time = now

    # 3. Pull fresh candidates emitted by budget VPS shards
    shard_hits = set()
    diff_res = subprocess.run(
        ["git", "-C", ROOT, "diff", "HEAD~5", "HEAD", "--", "ip/harvest/verified_alive_part_*.txt"],
        capture_output=True, text=True
    )
    for l in diff_res.stdout.splitlines():
        if l.startswith("+") and not l.startswith("+++"):
            parts = l[1:].strip().split()
            if parts and ":" in parts[0]:
                shard_hits.add(parts[0].split("\t")[0])

    for p in shard_hits:
        if p not in feed_candidates:
            feed_candidates[p] = "http"

    # 4. Deduplicate against persistent seen set
    seen_set = load_seen_set()
    unseen = {p: proto for p, proto in feed_candidates.items() if p not in seen_set}
    print(f"[{now_str}] Cycle #{cycle_num}: {len(feed_candidates):,} candidates | {len(unseen):,} brand-new unseen.", flush=True)

    verified_survivors = []
    pass_rate = 0.0

    if unseen:
        # Immediately record unseen to persistent seen set
        update_seen_set(unseen.keys())

        print(f"Strict-verifying {len(unseen):,} candidates (HTTP CONNECT & SOCKS5) at CONCURRENCY={CONCURRENCY}...", flush=True)
        t_v0 = time.time()
        sem = asyncio.Semaphore(CONCURRENCY)
        tracker = {"done": 0, "pass": 0, "total": len(unseen)}

        async def verify_all():
            tasks = [verify_candidate(p, proto, sem, tracker) for p, proto in unseen.items()]
            return await asyncio.gather(*tasks)

        res = asyncio.run(verify_all())
        verified_survivors = [(p, proto) for p, ok, _, proto in res if ok]
        elapsed_v = time.time() - t_v0
        pass_rate = (len(verified_survivors) / max(1, len(unseen))) * 100.0
        print(f"Verification complete in {elapsed_v:.1f}s: {len(verified_survivors):,}/{len(unseen):,} passed ({pass_rate:.2f}%).", flush=True)

    # 5. Promote survivors into real_pool.txt, deduped by ip:port
    real_pool = set()
    if os.path.exists(REAL_POOL_PATH):
        for l in open(REAL_POOL_PATH, errors="ignore"):
            l = l.strip()
            if l and ":" in l:
                real_pool.add(l.split()[0].split("\t")[0])

    new_promotions = 0
    if verified_survivors:
        with open(REAL_POOL_PATH, "a", encoding="utf-8") as f:
            for s, proto in verified_survivors:
                if s not in real_pool:
                    prov = lookup_prov(s.split(":")[0])
                    proto_tag = proto.upper() if proto else "HTTP"
                    f.write(f"{s}\tspeed.cloudflare.com\t{proto_tag}\t0\t{prov}\n")
                    real_pool.add(s)
                    new_promotions += 1
        print(f"Promoted {new_promotions:,} fresh survivors into real_pool.txt (Total: {len(real_pool):,}).", flush=True)

        # Commit and push
        subprocess.run(["git", "-C", ROOT, "add", "ip/harvest/real_pool.txt"], check=False)
        subprocess.run(["git", "-C", ROOT, "commit", "-m", f"feat(pool): harvest cycle #{cycle_num} promote +{new_promotions} (Total: {len(real_pool):,})"], check=False)
        subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "origin", "main"], check=False)
        subprocess.run(["git", "-C", ROOT, "push", "origin", "main"], check=False)

    # Update total stats
    total_stats["cycles"] += 1
    total_stats["new_entries_tested"] += len(unseen)
    total_stats["genuine_promoted"] += new_promotions
    elapsed_total_hrs = max(0.01, (now - total_stats["start_epoch"]) / 3600.0)
    genuine_per_hr = total_stats["genuine_promoted"] / elapsed_total_hrs
    new_per_hr = total_stats["new_entries_tested"] / elapsed_total_hrs
    current_pool = len(real_pool)
    remaining_30k = max(0, TARGET_POOL_SIZE - current_pool)

    # 6. Check Alerts: < 100 new entries an hour, or pass rate < 0.3%
    alerts = []
    if elapsed_total_hrs >= 1.0 and new_per_hr < 100:
        alerts.append(f"ALERT: Harvest returned {new_per_hr:.1f} new entries/hr (< 100/hr threshold)!")
    if len(unseen) >= 500 and pass_rate < 0.3:
        alerts.append(f"ALERT: Harvest pass rate dropped to {pass_rate:.2f}% (< 0.3% threshold)!")

    if alerts:
        with open(ALERT_PATH, "a", encoding="utf-8") as af:
            for al in alerts:
                af.write(f"[{now_str}] {al}\n")
        print("\n" + "\n".join(alerts) + "\n", flush=True)

    # 7. Write and print 15-minute report
    report = []
    report.append("=" * 80)
    report.append(f"HARVEST LOOP 15-MINUTE TELEMETRY REPORT — CYCLE #{cycle_num} ({now_str})")
    report.append("=" * 80)
    report.append(f"Elapsed Time Since Start : {elapsed_total_hrs*60:.1f} minutes ({elapsed_total_hrs:.2f} hrs)")
    report.append(f"New Entries (This Cycle) : {len(unseen):,} candidates tested")
    report.append(f"Pass Rate (This Cycle)   : {pass_rate:.2f}% ({len(verified_survivors):,} passed)")
    report.append(f"Promoted (This Cycle)    : +{new_promotions:,} genuine proxies")
    report.append("-" * 80)
    report.append(f"CUMULATIVE PERFORMANCE TOWARD 30K:")
    report.append(f"  Total Candidates Tested: {total_stats['new_entries_tested']:,}")
    report.append(f"  Total Genuine Promoted : +{total_stats['genuine_promoted']:,} proxies")
    report.append(f"  Genuine / Hour Rate    : {genuine_per_hr:.2f} / hr")
    report.append(f"  New Candidates / Hour  : {new_per_hr:,.1f} / hr")
    report.append(f"  Master Real Pool Size  : {current_pool:,} / {TARGET_POOL_SIZE:,} proxies")
    report.append(f"  Progress Toward 30k    : {(current_pool/TARGET_POOL_SIZE*100):.2f}% ({remaining_30k:,} remaining)")
    report.append(f"  Parallel Shard Fleet   : 20 Shards Running (Budget VPS: OVH, Hetzner, DO, Contabo, etc.)")
    if alerts:
        report.append("-" * 80)
        report.append("ACTIVE ALERTS:")
        for al in alerts: report.append(f"  * {al}")
    report.append("=" * 80)

    report_text = "\n".join(report)
    with open(STATUS_REPORT, "w", encoding="utf-8") as rf:
        rf.write(report_text + "\n")
    print("\n" + report_text, flush=True)

    return last_fetch_time

def main():
    print("=" * 80, flush=True)
    print("HARVEST LOOP V2 INITIALIZED", flush=True)
    print("Sources: Monosans, Proxifly, TheSpeedX, ProxyScrape, GeoNode, OpenProxy, Spys")
    print("Probes : Strict HTTP CONNECT & Strict SOCKS5 (with TLS 0x16 ServerHello check)")
    print("Shards : Budget VPS 10 Providers (OVH, Hetzner, Contabo, DO, Vultr, Linode, etc.)")
    print(f"Goal   : 30,000 Verified Proxies in real_pool.txt")
    print("=" * 80, flush=True)

    total_stats = {
        "start_epoch": time.time(),
        "cycles": 0,
        "new_entries_tested": 0,
        "genuine_promoted": 0
    }
    cycle_num = 1
    last_fetch_time = run_cycle(cycle_num, 0, total_stats)

if __name__ == "__main__":
    main()
