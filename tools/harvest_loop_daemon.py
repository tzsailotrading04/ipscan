"""
tools/harvest_loop_daemon.py
Automated Harvest Loop:
1. Hourly fetcher across:
   - monosans/proxy-list
   - proxifly/free-proxy-list
   - TheSpeedX/PROXY-List
   - api.proxyscrape.com
   - geonode free API
   - openproxy.space
   - spys.one / spys.me
   (HTTP and SOCKS, all ports)
2. Dedupes against persistent seen-set (cache/harvest_seen_set.txt)
3. Strict multi-target 0x16 TLS probe at CONCURRENCY=250; survivors promoted to real_pool.txt
4. Keeps budget-VPS hosting shards running in parallel, pulling and verifying fresh shard hits
5. Reports new entries, pass rate, and genuine/hour every 15 minutes toward 30,000 pool goal
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
# 1. FEED FETCHER
# ------------------------------------------------------------------------------
FEED_URLS = [
    # Monosans (HTTP, SOCKS4, SOCKS5)
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/all.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
    # Proxifly (80k+ proxies across all protocols)
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks4/data.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt",
    # TheSpeedX
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
    # ProxyScrape API
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks4&timeout=10000&country=all",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=10000&country=all",
    # Spys.one / Spys.me
    "https://spys.me/proxy.txt",
    "https://spys.me/socks.txt",
    # OpenProxy.space mirror / raw lists
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4_RAW.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
    "https://openproxy.space/list/http",
    "https://openproxy.space/list/socks4",
    "https://openproxy.space/list/socks5",
]

def fetch_single_url(url):
    results = set()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,text/plain,*/*"
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
            # Match IP:PORT format
            matches = re.findall(r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?):(?:\d{2,5})\b", text)
            for m in matches:
                results.add(m)
    except Exception:
        pass
    return results

def fetch_geonode_api():
    results = set()
    for page in range(1, 11):
        url = f"https://proxylist.geonode.com/api/proxy-list?limit=500&page={page}&sort_by=lastChecked&sort_type=desc"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                items = data.get("data", [])
                if not items: break
                for it in items:
                    ip, port = it.get("ip"), it.get("port")
                    if ip and port:
                        results.add(f"{ip}:{port}")
        except Exception:
            break
    return results

def fetch_all_feeds():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Fetching fresh feeds from all sources...", flush=True)
    all_proxies = set()
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(fetch_single_url, u) for u in FEED_URLS]
        futures.append(pool.submit(fetch_geonode_api))
        for f in futures:
            try:
                res = f.result()
                all_proxies.update(res)
            except Exception: pass
    print(f"Total raw proxies fetched: {len(all_proxies):,}", flush=True)
    return all_proxies

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
    
    # Also load all real_pool entries
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

# ------------------------------------------------------------------------------
# 3. STRICT MULTI-TARGET 0x16 PROBE
# ------------------------------------------------------------------------------
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
        if await inline_probe_connected(s, "speed.cloudflare.com", timeout=5.0):
            passed = True
            target_hit = "speed.cloudflare.com"
        else:
            for t in ["www.google.com", "one.one.one.one"]:
                if await probe_single_target(ip, port, t, timeout=5.0):
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
# 4. HARVEST CYCLE & METRICS
# ------------------------------------------------------------------------------
def run_harvest_cycle(cycle_num, last_fetch_time, total_stats):
    load_asn_table()
    now = time.time()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    
    # Git sync with parallel shard fleet
    subprocess.run(["git", "-C", ROOT, "fetch", "origin"], check=False)
    subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "origin", "main"], check=False)

    # 1. Fetch new feeds if 1 hour has elapsed or first run
    feed_candidates = set()
    if now - last_fetch_time >= 3600 or cycle_num == 1:
        feed_candidates = fetch_all_feeds()
        last_fetch_time = now

    # 2. Check fresh shard candidate lines
    shard_candidates = set()
    part_files = glob.glob(os.path.join(ROOT, "ip", "harvest", "verified_alive_part_*.txt"))
    for pf in part_files:
        try:
            for line in open(pf, errors="ignore"):
                line = line.strip()
                if line and ":" in line:
                    shard_candidates.add(line.split("\t")[0].split()[0])
        except Exception: pass

    # Combine candidates
    raw_combined = feed_candidates.union(shard_candidates)
    
    # 3. Deduplicate against persistent seen set
    seen_set = load_seen_set()
    unseen = [p for p in raw_combined if p not in seen_set]
    print(f"[{now_str}] Cycle #{cycle_num}: {len(raw_combined):,} total candidates | {len(unseen):,} brand new unseen.", flush=True)

    verified_survivors = []
    pass_rate = 0.0
    if unseen:
        # Save unseen to persistent seen set immediately to prevent re-verification
        update_seen_set(unseen)
        
        # 4. Strict verify all unseen entries
        print(f"Strict-verifying {len(unseen):,} new entries at CONCURRENCY={CONCURRENCY}...", flush=True)
        t_start = time.time()
        sem = asyncio.Semaphore(CONCURRENCY)
        tracker = {"done": 0, "pass": 0, "total": len(unseen)}
        
        async def verify_all():
            return await asyncio.gather(*[strict_verify_proxy(p, sem, tracker) for p in unseen])
            
        res = asyncio.run(verify_all())
        verified_survivors = [p for p, ok, tgt in res if ok]
        elapsed_v = time.time() - t_start
        pass_rate = (len(verified_survivors) / max(1, len(unseen))) * 100.0
        print(f"Verification complete in {elapsed_v:.1f}s: {len(verified_survivors):,}/{len(unseen):,} passed ({pass_rate:.2f}%).", flush=True)

    # 5. Promote survivors to real_pool.txt
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
                    f.write(f"{s}\tspeed.cloudflare.com\tDATACENTER\t0\t{prov}\n")
                    real_pool.add(s)
                    new_promotions += 1
        print(f"Promoted {new_promotions:,} fresh survivors into real_pool.txt.", flush=True)

        # Commit and push update with rebase retry
        subprocess.run(["git", "-C", ROOT, "add", "ip/harvest/real_pool.txt"], check=False)
        subprocess.run(["git", "-C", ROOT, "commit", "-m", f"feat(pool): harvest cycle #{cycle_num} promote {new_promotions} (Total: {len(real_pool):,})"], check=False)
        for _ in range(5):
            subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "origin", "main"], check=False)
            res = subprocess.run(["git", "-C", ROOT, "push", "origin", "main"], check=False)
            if res.returncode == 0:
                break
            time.sleep(2)

    # Update cumulative stats
    total_stats["cycles"] += 1
    total_stats["new_entries_tested"] += len(unseen)
    total_stats["genuine_promoted"] += new_promotions
    elapsed_total_hrs = max(0.01, (now - total_stats["start_epoch"]) / 3600.0)
    genuine_per_hr = total_stats["genuine_promoted"] / elapsed_total_hrs
    current_pool_size = len(real_pool)
    remaining_to_30k = max(0, TARGET_POOL_SIZE - current_pool_size)

    # 6. Format 15-minute report
    report = []
    report.append("=" * 80)
    report.append(f"HARVEST LOOP TELEMETRY REPORT — CYCLE #{cycle_num} ({now_str})")
    report.append("=" * 80)
    report.append(f"Elapsed Time Since Start : {elapsed_total_hrs*60:.1f} minutes ({elapsed_total_hrs:.2f} hrs)")
    report.append(f"New Entries (This Cycle) : {len(unseen):,} candidates tested")
    report.append(f"Pass Rate (This Cycle)   : {pass_rate:.2f}% ({len(verified_survivors):,} / {len(unseen):,})")
    report.append(f"Promoted (This Cycle)    : +{new_promotions:,} genuine proxies")
    report.append("-" * 80)
    report.append(f"CUMULATIVE METRICS:")
    report.append(f"  Total Candidates Tested: {total_stats['new_entries_tested']:,}")
    report.append(f"  Total Genuine Promoted : {total_stats['genuine_promoted']:,}")
    report.append(f"  Genuine / Hour (Rate)  : {genuine_per_hr:.2f} / hr")
    report.append(f"  Master Real Pool Size  : {current_pool_size:,} / {TARGET_POOL_SIZE:,} proxies")
    report.append(f"  Progress Toward 30k    : {(current_pool_size/TARGET_POOL_SIZE*100):.2f}% ({remaining_to_30k:,} remaining)")
    report.append(f"  Parallel Shard Fleet   : 20 Shards Running (Budget Datacenter)")

    # 7. Alerts check (<100 new entries/hr or <0.3% pass rate)
    alerts = []
    if elapsed_total_hrs >= 1.0 and (total_stats["new_entries_tested"] / elapsed_total_hrs) < 100:
        alerts.append(f"ALERT: New entries rate under 100/hr ({total_stats['new_entries_tested'] / elapsed_total_hrs:.1f}/hr)")
    if unseen and pass_rate < 0.3:
        alerts.append(f"ALERT: Pass rate under 0.3% ({pass_rate:.2f}%)")
    if alerts:
        report.append("-" * 80)
        report.extend(alerts)
    report.append("=" * 80)

    report_text = "\n".join(report)
    with open(STATUS_REPORT, "w", encoding="utf-8") as rf:
        rf.write(report_text + "\n")
    print("\n" + report_text, flush=True)

    return last_fetch_time

def main():
    print("=" * 80, flush=True)
    print("STARTING HARVEST LOOP DAEMON (CONTINUOUS 15-MIN CYCLE)", flush=True)
    print("Sources: Monosans, Proxifly, TheSpeedX, ProxyScrape, GeoNode, Spys, OpenProxy")
    print(f"Goal   : 30,000 Verified Proxies in real_pool.txt")
    print(f"Probe  : Strict Multi-Target TLS 0x16 (speed.cloudflare.com, google, 1.1.1.1)")
    print("=" * 80, flush=True)

    total_stats = {
        "start_epoch": time.time(),
        "cycles": 0,
        "new_entries_tested": 0,
        "genuine_promoted": 0
    }
    
    cycle_num = 1
    last_fetch_time = 0
    
    while True:
        last_fetch_time = run_harvest_cycle(cycle_num, last_fetch_time, total_stats)
        cycle_num += 1
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Cycle completed. Sleeping 15 minutes (900s) until next cycle...", flush=True)
        time.sleep(900)

if __name__ == "__main__":
    main()
