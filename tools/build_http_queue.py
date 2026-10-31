import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = r"D:\DEpinFarm"
QUEUE_DIR = os.path.join(ROOT, "ip", "harvest", "queue")
BULK_ALL = os.path.join(ROOT, "ip", "harvest", "bulk_all.txt")
REAL_POOL = os.path.join(ROOT, "ip", "harvest", "real_pool.txt")

http_sources = [
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
    ('zloiuser_http', 'https://raw.githubusercontent.com/zloi-user/hideip.me/master/http.txt'),
    ('roosterkid_https', 'https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt'),
    ('prxchk_http', 'https://raw.githubusercontent.com/prxchk/proxy-list/main/http.txt'),
]

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
        print(f"Fetch failed for {name}: {e}")
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
        print(f"spys.me fetch error: {e}")
    return found

def main():
    print("1. Loading bulk_all.txt and real_pool.txt...")
    bulk_all_list = []
    with open(BULK_ALL, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                bulk_all_list.append(line)
    bulk_all_set = set(bulk_all_list)
    print(f"Total lines in bulk_all.txt: {len(bulk_all_list):,}")

    real_pool = set()
    if os.path.exists(REAL_POOL):
        with open(REAL_POOL, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    real_pool.add(line)
    print(f"Total lines in real_pool.txt: {len(real_pool):,}")

    print("2. Fetching HTTP and HTTPS sources...")
    http_candidates = set()
    with ThreadPoolExecutor(max_workers=10) as ex:
        for name, found in ex.map(fetch_feed, http_sources):
            print(f"  {name}: {len(found):,} proxies")
            http_candidates.update(found)

    spys_found = scrape_spys_me()
    print(f"  spys_me_http: {len(spys_found):,} proxies")
    http_candidates.update(spys_found)
    print(f"Total unique proxies from HTTP/HTTPS sources: {len(http_candidates):,}")

    print("3. Filtering bulk_all.txt against HTTP/HTTPS sources and real_pool.txt...")
    kept = []
    dropped_non_http = 0
    dropped_in_pool = 0

    for p in bulk_all_list:
        if p not in http_candidates:
            dropped_non_http += 1
            continue
        if p in real_pool:
            dropped_in_pool += 1
            continue
        kept.append(p)

    total_dropped = dropped_non_http + dropped_in_pool
    print("\n=== FILTER RESULTS ===")
    print(f"Total bulk_all lines examined: {len(bulk_all_list):,}")
    print(f"Kept (from HTTP/HTTPS sources, not in real_pool): {len(kept):,}")
    print(f"Dropped total: {total_dropped:,}")
    print(f"  - Dropped (not in HTTP/HTTPS sources): {dropped_non_http:,}")
    print(f"  - Dropped (already in real_pool.txt): {dropped_in_pool:,}")

    # Cap at 200,000
    kept_capped = kept[:200000]
    chunk_size = 40000

    chunks = [kept_capped[i:i + chunk_size] for i in range(0, len(kept_capped), chunk_size)]
    print(f"\nWriting {len(chunks)} queue files (up to 40,000 lines each):")

    os.makedirs(QUEUE_DIR, exist_ok=True)
    for idx, chunk in enumerate(chunks, 1):
        filename = f"q_a0_http_1793445000_{idx:02d}.txt"
        filepath = os.path.join(QUEUE_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            for p in chunk:
                f.write(p + "\n")
        print(f"  Wrote {filepath} ({len(chunk):,} lines)")

if __name__ == "__main__":
    main()
