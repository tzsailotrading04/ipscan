"""
tools/harvest_novel.py
Novelty Harvest Engine:
1. Sources: Rotates through 4 source families (Fresh Lists, Country Matrix, Known Ecosystem Repos, Cached Endpoint Rotation).
2. Dedup: Memory-backed seen-set + real_pool.txt. Appends to harvest_seen_set.txt BEFORE probing.
3. Verify: Strict multi-target TLS handshake + System CA certificate validation.
4. Budget: Concurrency 600, 6s per-candidate timeout, high-speed 600-thread executor.
5. Report: work/harvest_novel_status.json updated every cycle. Automatic deprioritization when new-after-dedup < 10% for 3 cycles.
6. Commit: git pull --rebase, git add, commit, push with 3 retries and jitter.
"""
import asyncio
import bisect
import collections
import glob
import json
import os
import random
import re
import signal
import socket
import ssl
import struct
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = r"D:\DEpinFarm"
CACHE_DIR = os.path.join(ROOT, "cache")
SEEN_PATH = os.path.join(CACHE_DIR, "harvest_seen_set.txt")
ENDPOINTS_CACHE_PATH = os.path.join(CACHE_DIR, "endpoints.txt")
REAL_POOL_PATH = os.path.join(ROOT, "ip", "harvest", "real_pool.txt")
STATUS_JSON_PATH = os.path.join(ROOT, "work", "harvest_novel_status.json")
STATUS_TXT_PATH = os.path.join(ROOT, "work", "HARVEST_NOVEL_STATUS.txt")
ASN_PATH = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")

CONCURRENCY = 600
PROBE_TIMEOUT = 6.0
CONNECT_TIMEOUT = 2.0
FETCH_WORKERS = 48

SSL_CTX = ssl.create_default_context()

COUNTRIES = [
    "US", "DE", "FR", "GB", "NL", "RU", "CN", "BR", "IN", "ID",
    "CA", "JP", "KR", "SG", "HK", "IT", "ES", "PL", "UA", "TH",
    "VN", "TR", "AU", "MX", "AR", "CO", "CL", "ZA", "EG", "SE",
    "NO", "FI", "DK", "CH", "AT", "BE", "CZ", "RO", "BG", "GR",
    "IL", "AE", "SA", "PK", "BD", "PH", "MY", "TW", "IR"
]

# Dedicated 600-worker thread pool for concurrent TLS handshakes
PROBE_EXECUTOR = ThreadPoolExecutor(max_workers=CONCURRENCY)

# ------------------------------------------------------------------------------
# ASN TABLE FOR PROVIDER LOOKUP
# ------------------------------------------------------------------------------
asn_rows, asn_starts = [], []
def load_asn_table():
    global asn_rows, asn_starts
    if asn_starts: return
    if os.path.exists(ASN_PATH):
        rows = []
        with open(ASN_PATH, "r", encoding="utf-8", errors="ignore") as f:
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
# DEDUPLICATION & POOL STORAGE
# ------------------------------------------------------------------------------
def load_seen_and_pool():
    seen = set()
    os.makedirs(CACHE_DIR, exist_ok=True)
    if os.path.exists(SEEN_PATH):
        print(f"[INIT] Loading {SEEN_PATH}...", flush=True)
        with open(SEEN_PATH, "r", encoding="utf-8", errors="ignore") as f:
            for l in f:
                l = l.strip()
                if l and ":" in l:
                    seen.add(l.split()[0].split("\t")[0])
    
    pool_entries = set()
    if os.path.exists(REAL_POOL_PATH):
        print(f"[INIT] Loading {REAL_POOL_PATH}...", flush=True)
        with open(REAL_POOL_PATH, "r", encoding="utf-8", errors="ignore") as f:
            for l in f:
                l = l.strip()
                if l and ":" in l:
                    p = l.split()[0].split("\t")[0]
                    seen.add(p)
                    pool_entries.add(p)

    print(f"[INIT] Memory loaded: {len(seen):,} seen candidates, {len(pool_entries):,} existing real_pool proxies.", flush=True)
    return seen, pool_entries

def append_to_seen_file(candidates):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(SEEN_PATH, "a", encoding="utf-8") as f:
        for p in candidates:
            f.write(f"{p}\n")

def append_to_real_pool(survivors, existing_pool):
    os.makedirs(os.path.dirname(REAL_POOL_PATH), exist_ok=True)
    added = 0
    with open(REAL_POOL_PATH, "a", encoding="utf-8") as f:
        for p, tgt in survivors:
            if p not in existing_pool:
                ip_only = p.split(":")[0]
                prov = lookup_prov(ip_only)
                f.write(f"{p}\t{tgt}\t{prov}\n")
                existing_pool.add(p)
                added += 1
    return added

# ------------------------------------------------------------------------------
# SOURCE FAMILIES (ROTATION ARCHITECTURE)
# ------------------------------------------------------------------------------
class SourceManager:
    def __init__(self):
        self.families = ["country_matrix", "cache_endpoints", "known_repos", "fresh_lists"]
        self.current_idx = 0
        self.endpoint_offset = 3300  # Start at fresh newly discovered section
        self.health = {
            f: {"consecutive_low": 0, "deprioritized": False} for f in self.families
        }

    def get_fresh_lists_urls(self):
        return [
            "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/http_proxies.txt",
            "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/socks4_proxies.txt",
            "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/socks5_proxies.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4_RAW.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-https.txt",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt",
            "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
            "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/http.txt",
            "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks4.txt",
            "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks5.txt",
            "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/http.txt",
            "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/https.txt",
            "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks4.txt",
            "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt",
            "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/http.txt",
            "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/socks4.txt",
            "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/socks5.txt",
            "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt",
            "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/https.txt",
            "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks4.txt",
            "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt",
            "https://raw.githubusercontent.com/prxchk/proxy-list/main/http.txt",
            "https://raw.githubusercontent.com/prxchk/proxy-list/main/socks4.txt",
            "https://raw.githubusercontent.com/prxchk/proxy-list/main/socks5.txt",
            "https://raw.githubusercontent.com/tuanminpay/live-proxy/master/http.txt",
            "https://raw.githubusercontent.com/tuanminpay/live-proxy/master/socks4.txt",
            "https://raw.githubusercontent.com/tuanminpay/live-proxy/master/socks5.txt",
            "https://raw.githubusercontent.com/OfficialPutu/animate-server/master/proxies.txt",
            "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
            "https://raw.githubusercontent.com/hendrikbgr/Free-Proxy-Repo/master/proxy_list.txt",
            "https://spys.me/proxy.txt",
            "https://spys.me/socks.txt"
        ]

    def get_country_matrix_urls(self):
        urls = []
        for c in COUNTRIES:
            urls.append(f"https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country={c}&ssl=all&anonymity=all")
            urls.append(f"https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks4&timeout=10000&country={c}")
            urls.append(f"https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=10000&country={c}")
            urls.append(f"https://proxylist.geonode.com/api/proxy-list?country={c}&limit=500&page=1&sort_by=lastChecked&sort_type=desc")
            urls.append(f"https://proxylist.geonode.com/api/proxy-list?country={c}&limit=500&page=2&sort_by=lastChecked&sort_type=desc")
            urls.append(f"https://spys.one/free-proxy-list/{c}/")
        return urls

    def get_known_repos_urls(self):
        urls = [
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/all.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
            "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/proxies/all.txt",
            "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/proxies/http.txt",
            "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/proxies/socks4.txt",
            "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/proxies/socks5.txt",
            "https://raw.githubusercontent.com/notthinks/proxy-lists/main/http.txt",
            "https://raw.githubusercontent.com/notthinks/proxy-lists/main/socks4.txt",
            "https://raw.githubusercontent.com/notthinks/proxy-lists/main/socks5.txt",
            "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/master/proxies/http.txt",
            "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/master/proxies/socks4.txt",
            "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/master/proxies/socks5.txt",
            "https://raw.githubusercontent.com/shiftytr/proxy-list/master/proxy.txt",
            "https://raw.githubusercontent.com/shiftytr/proxy-list/master/socks4.txt",
            "https://raw.githubusercontent.com/shiftytr/proxy-list/master/socks5.txt",
        ]
        for c in COUNTRIES[:25]:
            urls.append(f"https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_geolocation/{c}/all.txt")
            urls.append(f"https://raw.githubusercontent.com/iplocate/free-proxy-list/main/countries/{c}.txt")
            urls.append(f"https://raw.githubusercontent.com/notthinks/proxy-lists/main/country/{c}/http.txt")
            urls.append(f"https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/master/countries/{c}.txt")
        return urls

    def get_cache_endpoints_slice(self):
        if not os.path.exists(ENDPOINTS_CACHE_PATH):
            return []
        with open(ENDPOINTS_CACHE_PATH, "r", encoding="utf-8", errors="ignore") as f:
            all_eps = [l.strip() for l in f if l.strip()]
        if not all_eps:
            return []
        
        batch_size = 250
        if self.endpoint_offset >= len(all_eps):
            self.endpoint_offset = 0
        batch = all_eps[self.endpoint_offset : self.endpoint_offset + batch_size]
        self.endpoint_offset += len(batch)
        return batch

    def select_next_source_family(self):
        candidates = [f for f in self.families if not self.health[f]["deprioritized"]]
        if not candidates:
            for f in self.families:
                self.health[f]["consecutive_low"] = 0
                self.health[f]["deprioritized"] = False
            candidates = self.families

        chosen = self.families[self.current_idx % len(self.families)]
        self.current_idx += 1
        if chosen not in candidates:
            chosen = candidates[0]

        if chosen == "fresh_lists":
            urls = self.get_fresh_lists_urls()
        elif chosen == "country_matrix":
            urls = self.get_country_matrix_urls()
        elif chosen == "known_repos":
            urls = self.get_known_repos_urls()
        else:
            urls = self.get_cache_endpoints_slice()

        return chosen, urls

    def record_novelty_rate(self, family, novel_ratio):
        if novel_ratio < 0.10:
            self.health[family]["consecutive_low"] += 1
            if self.health[family]["consecutive_low"] >= 3:
                self.health[family]["deprioritized"] = True
                print(f"[DEPRIORITIZE] Source family '{family}' deprioritized (novelty < 10% for 3 cycles).", flush=True)
        else:
            self.health[family]["consecutive_low"] = 0
            self.health[family]["deprioritized"] = False

# ------------------------------------------------------------------------------
# CONCURRENT FETCHING & HOST:PORT REGEX EXTRACTION (ANY PORT)
# ------------------------------------------------------------------------------
def fetch_url(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*"
        }
    )
    found = set()
    try:
        with urllib.request.urlopen(req, timeout=5.5) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
            if "proxylist.geonode.com" in url:
                try:
                    data = json.loads(text)
                    for item in data.get("data", []):
                        ip, port = item.get("ip"), item.get("port")
                        if ip and port: found.add(f"{ip}:{port}")
                except Exception: pass
            
            matches = re.findall(r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?):(?:\d{1,5})\b", text)
            for m in matches:
                try:
                    p = int(m.split(":")[1])
                    if 1 <= p <= 65535:
                        found.add(m)
                except Exception: pass
    except Exception:
        pass
    return found

def fetch_all_urls(urls):
    combined = set()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        results = pool.map(fetch_url, urls)
        for r in results:
            combined.update(r)
    elapsed = time.time() - t0
    return list(combined), elapsed

# ------------------------------------------------------------------------------
# HIGH-PERFORMANCE STRICT TLS CERT-VALIDATING PROBE
# ------------------------------------------------------------------------------
def sync_tls_handshake_single(sock, target, timeout=PROBE_TIMEOUT):
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

        # Strict TLS ClientHello with SNI and System CA validation
        ss = SSL_CTX.wrap_socket(sock, server_hostname=target)
        ss.settimeout(timeout)
        ss.do_handshake()
        cert = ss.getpeercert()
        ss.close()
        return bool(cert)
    except Exception:
        try: sock.close()
        except Exception: pass
        return False

def sync_probe_candidate(ip, port, timeout=PROBE_TIMEOUT):
    # Try primary target (speed.cloudflare.com)
    s = None
    try:
        s = socket.create_connection((ip, port), timeout=CONNECT_TIMEOUT)
        if sync_tls_handshake_single(s, "speed.cloudflare.com", timeout):
            return True, "speed.cloudflare.com"
    except Exception:
        if s:
            try: s.close()
            except Exception: pass
        return False, ""

    # Fallback target (www.google.com)
    s2 = None
    try:
        s2 = socket.create_connection((ip, port), timeout=CONNECT_TIMEOUT)
        if sync_tls_handshake_single(s2, "www.google.com", timeout):
            return True, "www.google.com"
    except Exception:
        if s2:
            try: s2.close()
            except Exception: pass
        return False, ""

    return False, ""

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

        passed, target_hit = await loop.run_in_executor(PROBE_EXECUTOR, sync_probe_candidate, ip, port, PROBE_TIMEOUT)

        tracker["done"] += 1
        if passed:
            tracker["pass"] += 1
            results.append((ip_port, target_hit))

        if tracker["done"] % 2500 == 0:
            print(f"  [{tracker['done']:,}/{tracker['total']:,}] Probed | Passed: {tracker['pass']:,} ({tracker['pass']/max(1, tracker['done'])*100:.2f}%)", flush=True)

        queue.task_done()

async def run_probe_pool(candidates):
    q = asyncio.Queue()
    for c in candidates:
        q.put_nowait(c)
    tracker = {"done": 0, "pass": 0, "total": len(candidates)}
    results = []
    tasks = [asyncio.create_task(worker(q, tracker, results)) for _ in range(CONCURRENCY)]
    await asyncio.gather(*tasks)
    return results

# ------------------------------------------------------------------------------
# GIT SYNCHRONIZATION WITH RETRY & JITTER
# ------------------------------------------------------------------------------
def git_sync_and_push(cycle, survivors_count, pool_total):
    print(f"\n[GIT] Syncing cycle #{cycle} to GitHub (added +{survivors_count}, total pool: {pool_total:,})...", flush=True)
    subprocess.run(["git", "-C", ROOT, "add", "-A"], check=False)
    
    st = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"], capture_output=True, text=True)
    has_changes = any(l.strip() and not l.startswith("??") for l in st.stdout.splitlines())
    if has_changes:
        commit_msg = f"harvest: cycle #{cycle} +{survivors_count} (pool: {pool_total:,})"
        subprocess.run(["git", "-C", ROOT, "commit", "-m", commit_msg], check=False)

    for attempt in range(1, 4):
        pull = subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "origin", "main"], capture_output=True, text=True)
        if pull.returncode != 0:
            subprocess.run(["git", "-C", ROOT, "rebase", "--abort"], capture_output=True)
            subprocess.run(["git", "-C", ROOT, "fetch", "origin", "main"], capture_output=True)
            subprocess.run(["git", "-C", ROOT, "merge", "--no-edit", "-X", "theirs", "origin/main"], capture_output=True)
        
        push = subprocess.run(["git", "-C", ROOT, "push", "origin", "main"], capture_output=True, text=True)
        if push.returncode == 0:
            print(f"  [GIT] Successfully pushed to origin/main on attempt {attempt}.", flush=True)
            return True
        else:
            print(f"  [GIT ERROR] Push failed attempt {attempt}/3 (exit code {push.returncode}): {push.stderr.strip()}", file=sys.stderr, flush=True)
            jitter = random.uniform(1.5, 3.5)
            time.sleep(jitter)
    return False

# ------------------------------------------------------------------------------
# MAIN HARVEST LOOP
# ------------------------------------------------------------------------------
def main():
    print("="*80, flush=True)
    print("NOVELTY HARVEST ENGINE INITIALIZING", flush=True)
    print("="*80, flush=True)
    load_asn_table()

    seen_set, pool_set = load_seen_and_pool()
    source_mgr = SourceManager()

    history_additions = collections.deque()
    cycle = 0

    running = True
    def handle_sig(sig, frame):
        nonlocal running
        print("\n[STOP] Received termination signal. Cleanly finishing current cycle...", flush=True)
        running = False
    
    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    while running:
        cycle += 1
        now = time.time()
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")

        # 1. Select source family
        family_name, urls = source_mgr.select_next_source_family()
        print(f"\n[{now_str}] === CYCLE #{cycle}: SOURCE FAMILY '{family_name}' ({len(urls):,} URLs) ===", flush=True)

        # 2. Concurrently fetch and extract
        raw_candidates, fetch_dur = fetch_all_urls(urls)
        print(f"Fetched {len(urls):,} URLs in {fetch_dur:.1f}s. Extracted {len(raw_candidates):,} host:port candidates.", flush=True)

        # 3. Dedup against seen_set and pool_set
        novel_candidates = [c for c in raw_candidates if c not in seen_set]
        found_cnt = len(raw_candidates)
        novel_cnt = len(novel_candidates)
        novel_ratio = (novel_cnt / max(1, found_cnt))
        print(f"Dedup Results: {novel_cnt:,}/{found_cnt:,} brand-new candidates ({novel_ratio*100:.2f}% novel).", flush=True)

        # Record health for automatic deprioritization
        source_mgr.record_novelty_rate(family_name, novel_ratio)

        # 4. Immediately add novel candidates to persistent seen_set BEFORE probing
        if novel_candidates:
            append_to_seen_file(novel_candidates)
            for c in novel_candidates:
                seen_set.add(c)

        # 5. Strict cert-valid probing across 600 concurrency
        survivors = []
        if novel_candidates:
            print(f"Streaming {len(novel_candidates):,} candidates across {CONCURRENCY} workers (timeout={PROBE_TIMEOUT}s)...", flush=True)
            t_vstart = time.time()
            survivors = asyncio.run(run_probe_pool(novel_candidates))
            probe_dur = time.time() - t_vstart
            print(f"Probe completed in {probe_dur:.1f}s: {len(survivors):,} TLS-valid survivors confirmed.", flush=True)
        else:
            print("No novel candidates to probe in this cycle.", flush=True)

        # 6. Append genuinely new survivors to real_pool.txt
        added_to_pool = append_to_real_pool(survivors, pool_set)
        pool_total = len(pool_set)

        # Record hourly additions
        history_additions.append((now, added_to_pool))
        while history_additions and history_additions[0][0] < now - 86400:
            history_additions.popleft()

        new_this_hour = sum(cnt for ts, cnt in history_additions if ts >= now - 3600)
        new_last_24h = sum(cnt for ts, cnt in history_additions)

        print(f"[PROGRESS] Added: +{added_to_pool} | Total Pool: {pool_total:,} | This Hour: +{new_this_hour:,} | Last 24h: +{new_last_24h:,}", flush=True)

        # 7. Write work/harvest_novel_status.json
        status_payload = {
            "cycle_number": cycle,
            "timestamp": now,
            "time_str": now_str,
            "source_used": family_name,
            "candidates_found": found_cnt,
            "candidates_new_after_dedup": novel_cnt,
            "new_after_dedup_ratio": round(novel_ratio, 4),
            "survivors": added_to_pool,
            "pool_total": pool_total,
            "new_to_pool_this_hour": new_this_hour,
            "new_to_pool_last_24h": new_last_24h,
            "source_health": source_mgr.health
        }

        os.makedirs(os.path.dirname(STATUS_JSON_PATH), exist_ok=True)
        with open(STATUS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(status_payload, f, indent=2)

        # 8. Git Commit and Push every cycle
        git_sync_and_push(cycle, added_to_pool, pool_total)

        if not running:
            break

    print("[SHUTDOWN] Harvest novelty engine stopped cleanly.", flush=True)

if __name__ == "__main__":
    main()
