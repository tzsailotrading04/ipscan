"""
tools/harvest_fresh_endpoints_fast.py
High-speed multithreaded discovery of fresh proxy endpoints across:
1. 11 new search queries (English + non-English)
2. Spys.one, ProxyScrape & GeoNode per-country matrices
3. Concurrent git tree extraction
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = r"D:\DEpinFarm"
CACHE_DIR = os.path.join(ROOT, "cache")
ENDPOINTS_FILE = os.path.join(CACHE_DIR, "endpoints.txt")

TOKEN = "ghp_" + "Kw30ViztVvNX2QUbi6CcKu4NTSVV9K0J7ILR"
GH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/vnd.github.v3+json",
    "Authorization": f"token {TOKEN}"
}

FRESH_TERMS = [
    "socks5-proxy-list",
    "http-proxy-list",
    "elite-proxy",
    "anonymous-proxy-list",
    "proxy-scraper",
    "fresh-proxy",
    "proxy-list-daily",
    "proxy-gateway",
    "gratis proxy",
    "proxy kostenlos",
    "proxies gratis"
]

COUNTRIES = [
    "all", "US", "DE", "FR", "GB", "NL", "RU", "CN", "BR", "IN",
    "ID", "CA", "JP", "KR", "SG", "HK", "IT", "ES", "PL", "UA",
    "TH", "VN", "TR", "AU", "MX", "AR", "CO", "CL", "ZA", "EG",
    "SE", "NO", "FI", "DK", "CH", "AT", "BE", "CZ", "RO", "BG",
    "GR", "IL", "AE", "SA", "PK", "BD", "PH", "MY", "TW", "IR"
]
PROTOCOLS = ["http", "socks4", "socks5"]

def fetch_json(url):
    req = urllib.request.Request(url, headers=GH_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception:
        return None

def fetch_repo_tree(item):
    repo, branch = item
    tree_url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    data = fetch_json(tree_url)
    endpoints = []
    if data and "tree" in data:
        for node in data["tree"]:
            if node.get("type") == "blob":
                path = node.get("path", "")
                lp = path.lower()
                if any(ext in lp for ext in [".txt", ".json", ".csv"]):
                    if any(k in lp for k in ["proxy", "proxies", "http", "socks", "ip", "alive", "checked", "speed"]):
                        endpoints.append(f"https://raw.githubusercontent.com/{repo}/{branch}/{path}")
    return endpoints

def main():
    print("=== HIGH-SPEED FRESH ENDPOINT DISCOVERY ===", flush=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    existing_eps = set()
    if os.path.exists(ENDPOINTS_FILE):
        with open(ENDPOINTS_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for l in f:
                l = l.strip()
                if l: existing_eps.add(l)
    print(f"Existing endpoints in cache: {len(existing_eps):,}", flush=True)

    # 1. GitHub Search across new terms
    discovered_repos = {}
    for term in FRESH_TERMS:
        q = urllib.parse.quote(term)
        url = f"https://api.github.com/search/repositories?q={q}&sort=updated&per_page=100"
        data = fetch_json(url)
        if data and "items" in data:
            for item in data["items"]:
                fn = item.get("full_name")
                branch = item.get("default_branch", "main")
                if fn and fn not in discovered_repos:
                    discovered_repos[fn] = branch
            print(f"Query '{term}': {len(data['items'])} repos (total discovered: {len(discovered_repos):,})", flush=True)
        time.sleep(2.0)

    print(f"\nConcurrently extracting git trees for {len(discovered_repos):,} repos (workers=20)...", flush=True)

    new_endpoints = set()
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(fetch_repo_tree, item) for item in discovered_repos.items()]
        done_cnt = 0
        for f in as_completed(futures):
            res = f.result()
            if res:
                for ep in res:
                    new_endpoints.add(ep)
            done_cnt += 1
            if done_cnt % 50 == 0:
                print(f"[{done_cnt:,}/{len(discovered_repos):,}] Repos processed | Discovered raw lists: {len(new_endpoints):,}", flush=True)

    print(f"Total raw GitHub endpoints extracted: {len(new_endpoints):,}", flush=True)

    # 2. Add Sources: Spys.one, ProxyScrape per-country, GeoNode per-country
    new_endpoints.add("https://spys.me/proxy.txt")
    new_endpoints.add("https://spys.me/socks.txt")
    new_endpoints.add("https://spys.one/en/free-proxy-list/")
    new_endpoints.add("https://spys.one/en/socks-proxy-list/")
    new_endpoints.add("https://spys.one/en/anonymous-proxy-list/")
    new_endpoints.add("https://spys.one/en/http-proxy-list/")
    new_endpoints.add("https://spys.one/en/https-ssl-proxy/")
    for c in COUNTRIES:
        if c != "all":
            new_endpoints.add(f"https://spys.one/free-proxy-list/{c}/")

    # ProxyScrape per-country matrix
    for p in PROTOCOLS:
        for c in COUNTRIES:
            new_endpoints.add(f"https://api.proxyscrape.com/v2/?request=displayproxies&protocol={p}&timeout=10000&country={c}&ssl=all&anonymity=all")

    # GeoNode per-country endpoints
    for c in COUNTRIES:
        for page in [1, 2]:
            new_endpoints.add(f"https://proxylist.geonode.com/api/proxy-list?country={c}&limit=500&page={page}&sort_by=lastChecked&sort_type=desc")

    # 3. Filter truly new endpoints
    truly_new = [ep for ep in new_endpoints if ep not in existing_eps]
    print(f"\nFresh unique endpoints gathered: {len(new_endpoints):,}", flush=True)
    print(f"Truly NEW endpoints appended: {len(truly_new):,}", flush=True)

    with open(ENDPOINTS_FILE, "a", encoding="utf-8") as f:
        for ep in truly_new:
            f.write(f"{ep}\n")

    total_now = len(existing_eps) + len(truly_new)
    print(f"Master cache/endpoints.txt now has {total_now:,} endpoints.", flush=True)

if __name__ == "__main__":
    main()
