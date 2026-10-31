import os
import sys
import time
import re
import urllib.request
import subprocess
from concurrent.futures import ThreadPoolExecutor

REPO_ROOT = r"D:\DEpinFarm"
QUEUE_DIR = os.path.join(REPO_ROOT, "ip", "harvest", "queue")
BULK_ALL = os.path.join(REPO_ROOT, "ip", "harvest", "bulk_all.txt")
REAL_POOL = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
POOL_DEAD = os.path.join(REPO_ROOT, "cache", "pool_dead.txt")
LOG_FILE = os.path.join(REPO_ROOT, "work", "proxy_queue_refresh.log")

HTTP_SOURCES = [
    ('monosans_http', 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt'),
    ('proxifly_http', 'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt'),
    ('proxmint_http', 'https://raw.githubusercontent.com/proxmint/free-proxy-list/main/proxies/http.txt'),
    ('thespeedx_http', 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt'),
    ('r00tee_http', 'https://raw.githubusercontent.com/r00tee/Proxy-List/main/Https.txt'),
    ('dpangestuw_http', 'https://raw.githubusercontent.com/dpangestuw/Free-Proxy/main/http_proxies.txt'),
    ('proxyspace_http', 'https://proxyspace.pro/http.txt'),
    ('proxyspace_https', 'https://proxyspace.pro/https.txt'),
    ('komutan234_http', 'https://raw.githubusercontent.com/komutan234/Proxy-List-Free/main/proxies/http.txt'),
    ('kangproxy_http', 'https://cdn.jsdelivr.net/gh/officialputuid/KangProxy@main/http/http.txt'),
    ('zevtyardt_http', 'https://raw.githubusercontent.com/zevtyardt/proxy-list/main/http.txt'),
    ('murongpig_http', 'https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/http.txt'),
    ('ercindedeoglu_http', 'https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/http.txt'),
    ('anonym0uswork_http', 'https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/master/proxy_files/http_proxies.txt'),
    ('b4rc0de_http', 'https://raw.githubusercontent.com/B4RC0DE-TM/proxy-list/main/HTTP.txt'),
    ('jetkai_http', 'https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt'),
    ('aliilapro_http', 'https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/http.txt'),
    ('sunny9577_http', 'https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/http_proxies.txt'),
    ('vakhov_http', 'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt'),
    ('zloiuser_http', 'https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt'),
    ('roosterkid_https', 'https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt'),
    ('prxchk_http', 'https://raw.githubusercontent.com/prxchk/proxy-list/main/http.txt'),
    ('clarketm_http', 'https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt'),
    ('mmpx12_http', 'https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt'),
]

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{ts}] {msg}"
    print(formatted, flush=True)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as lf:
            lf.write(formatted + "\n")
    except Exception:
        pass

def fetch_feed(item):
    name, url = item
    found = set()
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode('utf-8', errors='ignore')
            cands = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b', body)
            for c in cands:
                m = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{2,5})$', c.strip())
                if m:
                    ip, port = m.groups()
                    p_int = int(port)
                    if 1 <= p_int <= 65535:
                        octets = [int(o) for o in ip.split('.')]
                        if all(0 <= o <= 255 for o in octets) and octets[0] not in (0, 10, 127):
                            found.add(f"{ip}:{port}")
    except Exception as e:
        log(f"Feed error {name}: {e}")
    return name, found

def scrape_spys_me():
    found = set()
    try:
        req = urllib.request.Request('https://spys.me/proxy.txt', headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=12) as r:
            body = r.read().decode('utf-8', errors='ignore')
            for c in re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b', body):
                found.add(c)
    except Exception as e:
        log(f"spys.me error: {e}")
    return found

def run_step(cmd_list, desc):
    log(f"Starting: {desc} ({' '.join(cmd_list)})")
    res = subprocess.run(cmd_list, cwd=REPO_ROOT, capture_output=True, text=True)
    if res.returncode == 0:
        log(f"Completed: {desc}")
    else:
        log(f"Failed ({res.returncode}): {desc} -> {res.stderr.strip() or res.stdout.strip()}")
    return res.returncode == 0

def git_commit_push(epoch, kept_count):
    log("Committing and pushing to git...")
    subprocess.run(["git", "-C", REPO_ROOT, "add", "ip/harvest/bulk_all.txt", "ip/harvest/feeds_raw.txt", "ip/harvest/queue/"], check=False)
    msg = f"queue: refresh HTTP batch q_a0_http_{epoch} ({kept_count:,} cands)"
    c_res = subprocess.run(["git", "-C", REPO_ROOT, "commit", "-m", msg], capture_output=True, text=True)
    if c_res.returncode != 0 and "nothing to commit" in c_res.stdout:
        log("No changes to commit in git.")
        return True

    for attempt in range(1, 4):
        p_res = subprocess.run(["git", "-C", REPO_ROOT, "push", "origin", "main"], capture_output=True, text=True)
        if p_res.returncode == 0:
            log(f"Successfully pushed to origin/main on attempt {attempt}.")
            return True
        log(f"Push attempt {attempt} failed: {p_res.stderr.strip() or p_res.stdout.strip()}. Pulling with rebase...")
        subprocess.run(["git", "-C", REPO_ROOT, "fetch", "origin", "main", "--quiet"], check=False)
        subprocess.run(["git", "-C", REPO_ROOT, "rebase", "origin/main"], check=False)
        time.sleep(2)
    return False

def main():
    log("=== STARTING PROXY QUEUE REFRESH JOB ===")
    
    # 1. Run harvesters
    run_step([sys.executable, os.path.join(REPO_ROOT, "tools", "pull_aggregators.py")], "pull_aggregators.py")
    run_step([sys.executable, os.path.join(REPO_ROOT, "tools", "bulk_harvest.py")], "bulk_harvest.py")

    # 2. Load bulk_all.txt
    if not os.path.exists(BULK_ALL):
        log("ERROR: bulk_all.txt not found. Aborting.")
        return 1

    bulk_all_list = []
    with open(BULK_ALL, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                bulk_all_list.append(line)
    log(f"Loaded {len(bulk_all_list):,} lines from bulk_all.txt")

    # 3. Load exclusions (real_pool and pool_dead)
    real_pool = set()
    if os.path.exists(REAL_POOL):
        with open(REAL_POOL, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                m = re.search(r'\b(\d{1,3}(?:\.\d{1,3}){3}:\d{2,5})\b', line)
                if m:
                    real_pool.add(m.group(1))
    log(f"Loaded {len(real_pool):,} unique endpoints from real_pool.txt")

    pool_dead = set()
    if os.path.exists(POOL_DEAD):
        with open(POOL_DEAD, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                m = re.search(r'\b(\d{1,3}(?:\.\d{1,3}){3}:\d{2,5})\b', line)
                if m:
                    pool_dead.add(m.group(1))
    log(f"Loaded {len(pool_dead):,} unique endpoints from pool_dead.txt")

    # 4. Fetch HTTP/HTTPS candidates
    log(f"Fetching {len(HTTP_SOURCES)} HTTP/HTTPS feeds in parallel...")
    http_candidates = set()
    with ThreadPoolExecutor(max_workers=10) as ex:
        for name, found in ex.map(fetch_feed, HTTP_SOURCES):
            http_candidates.update(found)
    spys_found = scrape_spys_me()
    http_candidates.update(spys_found)
    log(f"Gathered {len(http_candidates):,} unique proxies from HTTP/HTTPS sources.")

    # 5. Filter bulk_all.txt
    kept = []
    dropped_non_http = 0
    dropped_in_pool = 0
    dropped_in_dead = 0

    for p in bulk_all_list:
        if p not in http_candidates:
            dropped_non_http += 1
            continue
        if p in real_pool:
            dropped_in_pool += 1
            continue
        if p in pool_dead:
            dropped_in_dead += 1
            continue
        kept.append(p)

    total_dropped = dropped_non_http + dropped_in_pool + dropped_in_dead
    log(f"Filter Results: Kept={len(kept):,}, Dropped Total={total_dropped:,} (Non-HTTP={dropped_non_http:,}, RealPool={dropped_in_pool:,}, DeadPool={dropped_in_dead:,})")

    # 6. Write queue files
    epoch = int(time.time())
    kept_capped = kept[:200000]
    chunk_size = 40000
    chunks = [kept_capped[i:i + chunk_size] for i in range(0, len(kept_capped), chunk_size)]
    log(f"Writing {len(chunks)} queue files for epoch {epoch} (capped at 200,000)...")

    os.makedirs(QUEUE_DIR, exist_ok=True)
    for idx, chunk in enumerate(chunks, 1):
        filename = f"q_a0_http_{epoch}_{idx:02d}.txt"
        filepath = os.path.join(QUEUE_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            for p in chunk:
                f.write(p + "\n")
        log(f"  Wrote {filename} ({len(chunk):,} lines)")

    # 7. Commit & push
    git_commit_push(epoch, len(kept_capped))
    log("=== PROXY QUEUE REFRESH JOB FINISHED ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())
