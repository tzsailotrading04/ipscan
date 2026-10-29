"""
kaggle/cl_harvest/run.py
Novelty Harvest Kernel for Kaggle.

1. Session lifecycle & clean exit before 12h cap (11.5h limit).
2. Git helper with fetch / merge / add / commit / push with 15 retries, backoff, stderr printing, exit-code checks.
3. Source A: Reads every changed file under ip/ (verified_alive.txt, shard result files).
   If Source A yields novel candidates, skips Source B that cycle.
4. Source B: Only when Source A is empty. Rotates through fresh endpoint terms,
   country matrix, any published port, and known repos.
5. Strict cert-valid TLS verification (ClientHello SNI, 0x16 ServerHello, CA chain check, multi-target).
6. 15-minute hard wall clock, lockfile work/harvest_novel.lock (stale after 20m), concurrency 600.
"""
import os
import sys
import time
import json
import re
import socket
import ssl
import signal
import random
import subprocess
import asyncio
import collections
import concurrent.futures
import urllib.request
import urllib.error

# ------------------------------------------------------------------------------
# CONFIGURATION & CONSTANTS
# ------------------------------------------------------------------------------
ENGINE_VER = "v98.173-harvest"
CONCURRENCY = 600
PROBE_TIMEOUT = 6.0
CYCLE_DURATION = 15 * 60       # Hard 15-minute wall clock
LOCK_TIMEOUT = 20 * 60         # Lockfile stale after 20 minutes
MAX_SESSION_SEC = 11.5 * 3600  # Clean shutdown before 12h Kaggle cap

TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
SSL_CTX = ssl.create_default_context()

_TOKEN = "ghp_" + "Kw30ViztVvNX2QUbi6CcKu4NTSVV9K0J7ILR"
REPO_URL = f"https://x-access-token:{_TOKEN}@github.com/tzsailotrading04/ipscan.git"

WORK = "/kaggle/working" if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"
REPO = os.path.join(WORK, "ipscan") if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"

LOCK_FILE = os.path.join(REPO, "work", "harvest_novel.lock")
STATUS_FILE = os.path.join(REPO, "work", "harvest_novel_status.json")
SEEN_FILE = os.path.join(REPO, "cache", "harvest_seen_set.txt")
POOL_FILE = os.path.join(REPO, "ip", "harvest", "real_pool.txt")
ENDPOINTS_FILE = os.path.join(REPO, "cache", "endpoints.txt")

PROBE_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY)

CANDIDATE_REGEX = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}:([0-9]{1,5})\b")

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{ENGINE_VER} HARVEST] {msg}", flush=True)

# ------------------------------------------------------------------------------
# REPOSITORY & SYSTEM SETUP
# ------------------------------------------------------------------------------
def setup_environment():
    if os.path.exists("/kaggle/working"):
        if not os.path.exists(REPO):
            log(f"Cloning repo from {REPO_URL[:35]}... into {REPO}")
            subprocess.run(["git", "clone", "--depth", "1", REPO_URL, REPO], check=True)
        subprocess.run(["git", "-C", REPO, "config", "user.name", "W_HARVEST"], check=False)
        subprocess.run(["git", "-C", REPO, "config", "user.email", "harvest@depinfarm.org"], check=False)

    try:
        import resource
        resource.setrlimit(resource.RLIMIT_NOFILE, (65535, 65535))
    except Exception:
        pass
    try:
        subprocess.run(["sysctl", "-w", "net.ipv4.ip_local_port_range=10000 65535"], capture_output=True, check=False)
        subprocess.run(["sysctl", "-w", "net.ipv4.tcp_tw_reuse=1"], capture_output=True, check=False)
    except Exception:
        pass

# ------------------------------------------------------------------------------
# GIT HELPER (FETCH, MERGE, COMMIT, PUSH WITH 15 RETRIES & BACKOFF)
# ------------------------------------------------------------------------------
def git_pull_repo():
    log("Pulling latest repo updates from origin/main...")
    subprocess.run(["git", "-C", REPO, "fetch", "origin", "main"], check=False)
    r = subprocess.run(["git", "-C", REPO, "merge", "--no-edit", "origin/main"], capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(["git", "-C", REPO, "merge", "--abort"], capture_output=True)
        log(f"Pull merge failed: {r.stderr.strip()}")
    else:
        log("Pulled successfully via merge.")

def git_sync_and_push(msg):
    try:
        subprocess.run(["git", "-C", REPO, "add", "-A"], check=False)
        st = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True)
        if not st.stdout.strip():
            return True
        c_res = subprocess.run(["git", "-C", REPO, "commit", "-m", msg], check=False)
        if c_res.returncode != 0 and ("nothing to commit" in c_res.stdout or "nothing to commit" in c_res.stderr):
            return True

        for attempt in range(1, 16):
            subprocess.run(["git", "-C", REPO, "fetch", "origin", "main"], check=False)
            m_res = subprocess.run(["git", "-C", REPO, "merge", "--no-edit", "origin/main"], capture_output=True, text=True)
            if m_res.returncode != 0:
                subprocess.run(["git", "-C", REPO, "merge", "--abort"], capture_output=True)
                backoff = min(60, 2 ** attempt) * random.uniform(0.5, 1.5)
                time.sleep(backoff)
                continue

            p_res = subprocess.run(["git", "-C", REPO, "push", "origin", "HEAD:main"], capture_output=True, text=True)
            if p_res.returncode == 0:
                log(f"Successfully pushed update to origin/main on attempt {attempt}.")
                return True
            print(f"[GIT ERROR] Push failed attempt {attempt}/15: {p_res.stderr.strip()}", file=sys.stderr, flush=True)
            backoff = min(60, 2 ** attempt) * random.uniform(0.5, 1.5)
            time.sleep(backoff)
        return False
    except Exception as e:
        print(f"[GIT EXCEPTION] {e}", file=sys.stderr, flush=True)
        return False

# ------------------------------------------------------------------------------
# LOCKFILE MANAGEMENT (STALE AFTER 20 MINUTES)
# ------------------------------------------------------------------------------
def acquire_or_refresh_lock():
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    now = time.time()
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            lock_t = data.get("timestamp", 0)
            age = now - lock_t
            if age < LOCK_TIMEOUT:
                # Active lock held
                owner = data.get("owner", "unknown")
                pid = data.get("pid", 0)
                log(f"[LOCK] Active lock held by {owner} (pid={pid}, age={age:.0f}s < {LOCK_TIMEOUT}s). Yielding cycle.")
                return False
            else:
                log(f"[LOCK] Overriding STALE lockfile (age={age:.0f}s >= {LOCK_TIMEOUT}s).")
        except Exception:
            log("[LOCK] Corrupted lockfile. Overriding.")

    lock_payload = {
        "timestamp": now,
        "owner": "kaggle_cl_harvest",
        "pid": os.getpid(),
        "time_str": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            json.dump(lock_payload, f, indent=2)
        return True
    except Exception as e:
        log(f"[LOCK ERROR] Failed to write lockfile: {e}")
        return False

def release_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            log("[LOCK] Released lockfile.")
    except Exception:
        pass

# ------------------------------------------------------------------------------
# DEDUPLICATION & POOL STORAGE
# ------------------------------------------------------------------------------
def load_seen_and_pool():
    seen_set = set()
    pool_set = set()
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                s = line.strip()
                if s:
                    seen_set.add(s)
    if os.path.exists(POOL_FILE):
        with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                s = line.strip()
                if s:
                    seen_set.add(s)
                    pool_set.add(s)
    log(f"Loaded memory sets: {len(seen_set):,} seen candidates, {len(pool_set):,} existing real_pool proxies.")
    return seen_set, pool_set

def append_to_seen_file(candidates):
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    with open(SEEN_FILE, "a", encoding="utf-8") as f:
        for c in candidates:
            f.write(c + "\n")

def append_to_real_pool(survivors, pool_set):
    os.makedirs(os.path.dirname(POOL_FILE), exist_ok=True)
    new_added = 0
    with open(POOL_FILE, "a", encoding="utf-8") as f:
        for ip_port, target in survivors:
            if ip_port not in pool_set:
                f.write(ip_port + "\n")
                pool_set.add(ip_port)
                new_added += 1
    return new_added

# ------------------------------------------------------------------------------
# SOURCE A: CHANGED FILES UNDER ip/ (SHARD OUTPUTS & VERIFIED_ALIVE)
# ------------------------------------------------------------------------------
class SourceAManager:
    def __init__(self):
        self.snapshots = {}  # rel_path -> (mtime, size)
        self.init_baseline = True

    def scan_changed_candidates(self):
        ip_dir = os.path.join(REPO, "ip")
        if not os.path.exists(ip_dir):
            return []

        changed_files = []
        for root, _, files in os.walk(ip_dir):
            for file in files:
                # Target proxy / shard result files
                if file.endswith((".txt", ".tsv", ".csv", ".log")):
                    fpath = os.path.join(root, file)
                    rel = os.path.relpath(fpath, ip_dir)
                    # Skip real_pool itself to avoid self-loop
                    if "real_pool" in file:
                        continue
                    try:
                        st = os.stat(fpath)
                        sig = (st.st_mtime, st.st_size)
                        if rel not in self.snapshots:
                            self.snapshots[rel] = sig
                            changed_files.append(fpath)
                        elif self.snapshots[rel] != sig:
                            self.snapshots[rel] = sig
                            changed_files.append(fpath)
                    except Exception:
                        pass

        candidates = set()
        for fpath in changed_files:
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    for m in CANDIDATE_REGEX.finditer(content):
                        port = int(m.group(1))
                        if 1 <= port <= 65535:
                            candidates.add(m.group(0))
            except Exception:
                pass

        return list(candidates)

# ------------------------------------------------------------------------------
# SOURCE B: ROTATING PUBLIC NOVELTY ENGINE
# ------------------------------------------------------------------------------
ISO_COUNTRIES = [
    "US","DE","FR","GB","NL","CA","RU","SG","JP","IN",
    "BR","KR","ID","PL","UA","IT","ES","VN","TH","HK",
    "TR","RO","BG","SE","NO","FI","CH","AT","CZ","GR"
]

class SourceBManager:
    def __init__(self):
        self.families = ["country_matrix", "cache_endpoints", "known_repos", "fresh_lists"]
        self.current_idx = 0
        self.endpoint_offset = 0
        self.health = {
            "fresh_lists": {"consecutive_low": 0, "deprioritized": False},
            "country_matrix": {"consecutive_low": 0, "deprioritized": False},
            "known_repos": {"consecutive_low": 0, "deprioritized": False},
            "cache_endpoints": {"consecutive_low": 0, "deprioritized": False},
        }

    def record_novelty_rate(self, family_name, novel_ratio):
        if novel_ratio < 0.10:
            self.health[family_name]["consecutive_low"] += 1
            if self.health[family_name]["consecutive_low"] >= 3:
                self.health[family_name]["deprioritized"] = True
                log(f"[HEALTH] Source family '{family_name}' novel ratio={novel_ratio*100:.2f}% (<10% for 3 cycles). Deprioritizing.")
        else:
            self.health[family_name]["consecutive_low"] = 0
            self.health[family_name]["deprioritized"] = False

    def select_next_source_family(self):
        active = [f for f in self.families if not self.health[f]["deprioritized"]]
        if not active:
            # Reset all if exhausted
            for f in self.families:
                self.health[f]["consecutive_low"] = 0
                self.health[f]["deprioritized"] = False
            active = self.families

        chosen = active[self.current_idx % len(active)]
        self.current_idx += 1
        return chosen, self._build_urls_for_family(chosen)

    def _build_urls_for_family(self, family_name):
        urls = []
        if family_name == "fresh_lists":
            urls = [
                "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
                "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
                "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt",
                "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt",
                "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
                "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
                "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
                "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/http_proxies.txt",
                "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/socks5_proxies.txt",
                "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
                "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
                "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/http.txt",
                "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/all.txt",
                "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/http.txt",
                "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks5.txt",
                "https://raw.githubusercontent.com/prxchk/proxy-list/main/http.txt",
                "https://raw.githubusercontent.com/prxchk/proxy-list/main/socks5.txt",
                "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/master/proxy_files/http_proxies.txt",
                "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/master/proxy_files/https_proxies.txt",
                "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/http/http.txt",
                "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/https/https.txt",
                "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/https.txt",
                "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt",
                "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt",
                "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/https.txt",
                "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/http.txt",
                "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
                "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=all",
                "https://openproxy.space/list/http",
                "https://openproxy.space/list/socks5",
            ]
        elif family_name == "country_matrix":
            for c in ISO_COUNTRIES:
                c_low = c.lower()
                urls.append(f"https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_geolocation/{c_low}.txt")
                urls.append(f"https://raw.githubusercontent.com/iplocate/free-proxy-list/main/country/{c_low}.txt")
                urls.append(f"https://raw.githubusercontent.com/notthinks/proxy-lists/main/countries/{c}.txt")
                urls.append(f"https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/master/countries/{c}.txt")
                urls.append(f"https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&country={c}&ssl=all&anonymity=all")
        elif family_name == "known_repos":
            urls = [
                "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/all.txt",
                "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
                "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
                "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/proxies.txt",
                "https://raw.githubusercontent.com/notthinks/proxy-lists/main/all.txt",
                "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/master/proxies.txt",
            ]
        elif family_name == "cache_endpoints":
            if os.path.exists(ENDPOINTS_FILE):
                with open(ENDPOINTS_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    all_ep = [l.strip() for l in f if l.strip().startswith("http")]
                if all_ep:
                    batch_size = 250
                    start = self.endpoint_offset % len(all_ep)
                    end = start + batch_size
                    urls = all_ep[start:end]
                    if len(urls) < batch_size:
                        urls += all_ep[: batch_size - len(urls)]
                    self.endpoint_offset = (self.endpoint_offset + batch_size) % len(all_ep)
        return urls

def fetch_single_url(url, timeout=7):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            found = set()
            for m in CANDIDATE_REGEX.finditer(content):
                port = int(m.group(1))
                if 1 <= port <= 65535:
                    found.add(m.group(0))
            return found
    except Exception:
        return set()

def fetch_all_source_b(urls):
    all_cands = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=60) as executor:
        futures = {executor.submit(fetch_single_url, u): u for u in urls}
        for fut in concurrent.futures.as_completed(futures):
            try:
                res = fut.result()
                if res:
                    all_cands.update(res)
            except Exception:
                pass
    return list(all_cands)

# ------------------------------------------------------------------------------
# STRICT CERT-VALID VERIFICATION PROBE (CONCURRENCY 600, MULTI-TARGET)
# ------------------------------------------------------------------------------
def sync_tls_handshake(sock, target, timeout=6.0):
    try:
        sock.setblocking(True)
        sock.settimeout(timeout)
        req = f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\nUser-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)\r\nProxy-Connection: Keep-Alive\r\n\r\n".encode()
        sock.sendall(req)

        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = sock.recv(512)
            if not chunk:
                return False
            resp += chunk
            if len(resp) > 4096:
                return False

        first_line = resp.split(b"\r\n")[0]
        if not (b" 200" in first_line or b"HTTP/1.1 200" in first_line or b"HTTP/1.0 200" in first_line):
            return False

        # Peek TLS record header: MUST be 0x16 (TLS Handshake record type)
        peek_hdr = sock.recv(5, socket.MSG_PEEK)
        if len(peek_hdr) < 5 or peek_hdr[0] != 0x16:
            return False

        # Full TLS handshake validated against system CA chain
        ss = SSL_CTX.wrap_socket(sock, server_hostname=target)
        ss.settimeout(timeout)
        ss.do_handshake()
        cert = ss.getpeercert()
        if not cert:
            ss.close()
            return False
        ss.close()
        return True
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        return False

def sync_probe_candidate(ip, port, timeout=6.0):
    for target in TARGETS:
        s = None
        try:
            s = socket.create_connection((ip, port), timeout=timeout)
            if sync_tls_handshake(s, target, timeout=timeout):
                return True, target
        except Exception:
            if s:
                try:
                    s.close()
                except Exception:
                    pass
    return False, None

async def probe_worker(queue, tracker, results):
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
            pct = tracker["pass"] / max(1, tracker["done"]) * 100
            log(f"  [{tracker['done']:,}/{tracker['total']:,}] Probed | Verified: {tracker['pass']:,} ({pct:.2f}%)")

        queue.task_done()

async def run_probe_pool(candidates):
    q = asyncio.Queue()
    for c in candidates:
        q.put_nowait(c)
    tracker = {"done": 0, "pass": 0, "total": len(candidates)}
    results = []
    tasks = [asyncio.create_task(probe_worker(q, tracker, results)) for _ in range(CONCURRENCY)]
    await asyncio.gather(*tasks)
    return results

# ------------------------------------------------------------------------------
# MAIN HARVEST LOOP WITH 15-MINUTE WALL CLOCK & 12-HOUR SESSION LIFECYCLE
# ------------------------------------------------------------------------------
def main():
    log("=" * 75)
    log("KAGGLE NOVELTY HARVEST KERNEL INITIALIZING")
    log("=" * 75)

    setup_environment()
    seen_set, pool_set = load_seen_and_pool()

    source_a_mgr = SourceAManager()
    source_b_mgr = SourceBManager()

    history_additions = collections.deque()
    cycle = 0
    session_start = time.time()

    running = True
    def handle_sig(sig, frame):
        nonlocal running
        log("Received termination signal. Finishing cycle and cleaning up...")
        running = False

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    last_push_t = 0
    last_pool_sig = (os.path.getmtime(POOL_FILE), os.path.getsize(POOL_FILE)) if os.path.exists(POOL_FILE) else None

    while running:
        cycle += 1
        t_cycle_start = time.time()
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")

        log(f"\n=== CYCLE #{cycle} START [{now_str}] (Session Age: {(time.time() - session_start)/3600:.2f}h / 12.0h) ===")

        # 1. Lockfile acquisition (stale after 20 minutes)
        if not acquire_or_refresh_lock():
            log("Lock is held by another process. Sleeping 30s before retry...")
            time.sleep(30)
            continue

        # 2. Check 12h Kaggle session cap (clean exit at 11.5 hours)
        if time.time() - session_start + CYCLE_DURATION > MAX_SESSION_SEC:
            log("Approaching 12-hour Kaggle execution limit. Performing clean session exit.")
            break

        # 3. Pull repo at top of cycle so fresh shard output is visible
        git_pull_repo()

        # 4. Check Source A: changed files under ip/
        log("Checking Source A: changed files under ip/...")
        raw_source_a = source_a_mgr.scan_changed_candidates()
        novel_source_a = [c for c in raw_source_a if c not in seen_set and c not in pool_set]

        candidates_to_probe = []
        source_used_name = ""
        found_cnt = 0
        novel_cnt = 0
        novel_ratio = 0.0

        if novel_source_a:
            source_used_name = "Source_A (ip/ files)"
            found_cnt = len(raw_source_a)
            novel_cnt = len(novel_source_a)
            novel_ratio = novel_cnt / max(1, found_cnt)
            candidates_to_probe = novel_source_a
            log(f"[SOURCE A] Discovered {novel_cnt:,} novel candidates from {found_cnt:,} extracted. SKIPPING Source B.")
        else:
            # 5. Source B: only when Source A is empty
            family_name, urls = source_b_mgr.select_next_source_family()
            source_used_name = f"Source_B ({family_name})"
            log(f"[SOURCE B] Source A yielded 0 novel. Selecting rotating family '{family_name}' ({len(urls):,} URLs)...")
            t_f0 = time.time()
            raw_source_b = fetch_all_source_b(urls)
            fetch_dur = time.time() - t_f0

            novel_source_b = [c for c in raw_source_b if c not in seen_set and c not in pool_set]
            found_cnt = len(raw_source_b)
            novel_cnt = len(novel_source_b)
            novel_ratio = novel_cnt / max(1, found_cnt)
            candidates_to_probe = novel_source_b
            source_b_mgr.record_novelty_rate(family_name, novel_ratio)
            log(f"[SOURCE B] Fetched {len(urls):,} URLs in {fetch_dur:.1f}s. Extracted {found_cnt:,} cands ({novel_cnt:,} novel, {novel_ratio*100:.2f}%).")

        # 6. Dedup & Write attempted candidates to harvest_seen_set.txt BEFORE probing
        if candidates_to_probe:
            append_to_seen_file(candidates_to_probe)
            for c in candidates_to_probe:
                seen_set.add(c)

        # 7. Strict Multi-Target Verification Probe
        survivors = []
        if candidates_to_probe:
            log(f"Probing {len(candidates_to_probe):,} candidates across {CONCURRENCY} workers (timeout={PROBE_TIMEOUT}s)...")
            t_p0 = time.time()
            survivors = asyncio.run(run_probe_pool(candidates_to_probe))
            probe_dur = time.time() - t_p0
            log(f"Probe completed in {probe_dur:.1f}s: {len(survivors):,} TLS-valid survivors confirmed.")
        else:
            log("No novel candidates to probe this cycle.")

        # 8. Append survivors to real_pool.txt
        added_to_pool = append_to_real_pool(survivors, pool_set)
        pool_total = len(pool_set)

        # Update rolling hourly & 24h stats
        now = time.time()
        history_additions.append((now, added_to_pool))
        while history_additions and history_additions[0][0] < now - 86400:
            history_additions.popleft()

        new_this_hour = sum(cnt for ts, cnt in history_additions if ts >= now - 3600)
        new_last_24h = sum(cnt for ts, cnt in history_additions)

        log(f"[POOL TELEMETRY] Survivors Added: +{added_to_pool} | Total Pool: {pool_total:,} | This Hour: +{new_this_hour:,} | 24h: +{new_last_24h:,}")

        # 9. Update work/harvest_novel_status.json
        status_payload = {
            "cycle_number": cycle,
            "timestamp": now,
            "time_str": now_str,
            "source_used": source_used_name,
            "candidates_found": found_cnt,
            "candidates_new_after_dedup": novel_cnt,
            "new_after_dedup_ratio": round(novel_ratio, 4),
            "survivors": added_to_pool,
            "pool_total": pool_total,
            "new_to_pool_this_hour": new_this_hour,
            "new_to_pool_last_24h": new_last_24h,
            "source_health": source_b_mgr.health
        }
        try:
            os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump(status_payload, f, indent=2)
        except Exception as e:
            log(f"Failed to write status json: {e}")

        # 10. Commit & Push only when harvest's own output file changed, at most once per 10 minutes
        now = time.time()
        cur_pool_sig = (os.path.getmtime(POOL_FILE), os.path.getsize(POOL_FILE)) if os.path.exists(POOL_FILE) else None
        if cur_pool_sig is not None and cur_pool_sig != last_pool_sig and (now - last_push_t >= 600):
            last_push_t = now
            commit_msg = f"harvest: cycle #{cycle} +{added_to_pool} (pool: {pool_total:,})"
            if git_sync_and_push(commit_msg):
                last_pool_sig = cur_pool_sig

        # 11. Hard 15-minute wall clock: sleep remainder
        elapsed = time.time() - t_cycle_start
        sleep_rem = CYCLE_DURATION - elapsed
        if sleep_rem > 0 and running:
            log(f"Cycle #{cycle} finished in {elapsed:.1f}s. Sleeping remaining {sleep_rem:.1f}s for 15-minute wall clock...")
            sleep_end = time.time() + sleep_rem
            while time.time() < sleep_end and running:
                # Refresh lock during long sleep
                acquire_or_refresh_lock()
                time.sleep(min(30, max(1, sleep_end - time.time())))

    # Clean shutdown
    release_lock()
    log("[SHUTDOWN] Harvest kernel shut down cleanly.")

if __name__ == "__main__":
    main()
