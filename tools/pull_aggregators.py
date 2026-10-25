import urllib.request
import json
import re
import os
import csv
from concurrent.futures import ThreadPoolExecutor

OUT_FEEDS = "D:/DEpinFarm/ip/harvest/feeds_raw.txt"

# 1. Direct URLs
aggregator_urls = [
    # Proxifly
    'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.txt',
    'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt',
    'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks4/data.txt',
    'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt',
    # Jetkai
    'https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies.txt',
    'https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt',
    'https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-https.txt',
    'https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt',
    'https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt',
    # ProxyScrape API
    'https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all',
    'https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks4&timeout=10000&country=all',
    'https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=10000&country=all',
    # ClarkeTM
    'https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt',
    # Spys.me
    'https://spys.me/proxy.txt',
    'https://spys.me/socks.txt',
    # TheSpeedX
    'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
    'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt',
    'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt',
    # Monosans
    'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/all.txt'
]

# 2. GeoNode Paginated API
def fetch_geonode():
    results = set()
    print("Fetching GeoNode API pages...", flush=True)
    for page in range(1, 11): # top 10 pages x 500 = up to 5,000 proxies
        url = f"https://proxylist.geonode.com/api/proxy-list?limit=500&page={page}&sort_by=lastChecked&sort_type=desc"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode('utf-8'))
                items = data.get('data', [])
                for item in items:
                    ip = item.get('ip')
                    port = item.get('port')
                    if ip and port:
                        results.add(f"{ip}:{port}")
        except Exception as e:
            print(f"GeoNode page {page} err: {e}")
            break
    print(f"GeoNode retrieved: {len(results):,} proxies", flush=True)
    return results

def fetch_url(u):
    try:
        req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode('utf-8', errors='ignore')
            matches = re.findall(r'(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})', txt)
            return set(f"{ip}:{port}" for ip, port in matches)
    except Exception as e:
        return set()

def load_kaggle_downloaded():
    results = set()
    # 1. charles1995/free-public-proxies-2026
    p1 = "D:/DEpinFarm/ip/harvest/kaggle_proxies/proxies.csv"
    if os.path.exists(p1):
        with open(p1, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ip, port = row.get('ip'), row.get('port')
                if ip and port:
                    results.add(f"{ip}:{port}")
    # 2. litportnet/free-proxy-observations
    p2 = "D:/DEpinFarm/ip/harvest/kaggle_litport/all.csv"
    if os.path.exists(p2):
        with open(p2, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ip, port = row.get('ip'), row.get('port')
                if ip and port:
                    results.add(f"{ip}:{port}")
    print(f"Kaggle datasets parsed: {len(results):,} proxies", flush=True)
    return results

def main():
    existing = set()
    if os.path.exists(OUT_FEEDS):
        with open(OUT_FEEDS, 'r', encoding='ascii', errors='ignore') as f:
            for l in f:
                l = l.strip()
                if l: existing.add(l)
    print(f"Initial feeds_raw.txt rows: {len(existing):,}")

    new_proxies = set()

    # 1. URL feeds in parallel
    print(f"Fetching {len(aggregator_urls)} aggregator URLs in parallel...", flush=True)
    with ThreadPoolExecutor(max_workers=10) as ex:
        for res in ex.map(fetch_url, aggregator_urls):
            new_proxies.update(res)

    # 2. GeoNode
    new_proxies.update(fetch_geonode())

    # 3. Kaggle Datasets
    new_proxies.update(load_kaggle_downloaded())

    added = new_proxies - existing
    print(f"Total new unique proxies harvested from aggregators & Kaggle: {len(added):,}")
    existing.update(added)

    # Write out updated feeds_raw.txt atomically
    tmp = OUT_FEEDS + ".tmp"
    with open(tmp, 'w', encoding='ascii') as f:
        for p in sorted(existing):
            f.write(p + "\n")
    os.replace(tmp, OUT_FEEDS)

    print(f"Final updated feeds_raw.txt count: {len(existing):,}")

if __name__ == "__main__":
    main()
