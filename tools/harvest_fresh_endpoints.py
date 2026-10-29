"""
tools/harvest_fresh_endpoints.py
Fresh endpoint sweep with new query terms and unindexed sources.
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse

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

def fetch_json(url, headers):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None

def main():
    print("=== STARTING FRESH ENDPOINT DISCOVERY SWEEP ===")
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    existing_eps = set()
    if os.path.exists(ENDPOINTS_FILE):
        with open(ENDPOINTS_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for l in f:
                l = l.strip()
                if l: existing_eps.add(l)
    print(f"Existing endpoints loaded: {len(existing_eps):,}")

    new_endpoints = set()

    # 1. GitHub Search across new terms
    discovered_repos = {}
    for term in FRESH_TERMS:
        q = urllib.parse.quote(term)
        url = f"https://api.github.com/search/repositories?q={q}&sort=updated&per_page=100"
        print(f"Searching GitHub for '{term}'...")
        data = fetch_json(url, GH_HEADERS)
        if data and "items" in data:
            count = len(data["items"])
            print(f"  -> Found {count} repos (total: {data.get('total_count', 0)})")
            for item in data["items"]:
                fn = item.get("full_name")
                branch = item.get("default_branch", "main")
                if fn and fn not in discovered_repos:
                    discovered_repos[fn] = branch
        time.sleep(2.5)  # Stay safely below 30 req/min search limit

    print(f"\nTotal unique fresh GitHub repos to inspect: {len(discovered_repos):,}")

    # Inspect git trees
    repo_idx = 0
    for repo, branch in discovered_repos.items():
        repo_idx += 1
        tree_url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
        data = fetch_json(tree_url, GH_HEADERS)
        if data and "tree" in data:
            for node in data["tree"]:
                path = node.get("path", "")
                # Match txt, json, csv proxy lists
                if node.get("type") == "blob":
                    lower_path = path.lower()
                    if any(ext in lower_path for ext in [".txt", ".json", ".csv"]):
                        if any(k in lower_path for k in ["proxy", "proxies", "http", "socks", "ip", "alive", "checked", "speed"]):
                            raw_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
                            new_endpoints.add(raw_url)
        if repo_idx % 25 == 0:
            print(f"  [{repo_idx}/{len(discovered_repos)}] Processed | Discovered raw files so far: {len(new_endpoints):,}")
            time.sleep(0.5)

    print(f"Total raw GitHub endpoints extracted: {len(new_endpoints):,}")

    # 2. Add Sources: spys.one per-country, ProxyScrape per-country, GeoNode per-country
    # spys.me & spys.one
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
        for page in [1, 2, 3]:
            new_endpoints.add(f"https://proxylist.geonode.com/api/proxy-list?country={c}&limit=500&page={page}&sort_by=lastChecked&sort_type=desc")

    # 3. Deduplicate against existing endpoints
    truly_new = [ep for ep in new_endpoints if ep not in existing_eps]
    print(f"\nFresh endpoints gathered: {len(new_endpoints):,}")
    print(f"Truly NEW endpoints not previously in endpoints.txt: {len(truly_new):,}")

    # Append new endpoints to endpoints.txt
    with open(ENDPOINTS_FILE, "a", encoding="utf-8") as f:
        for ep in truly_new:
            f.write(f"{ep}\n")

    total_now = len(existing_eps) + len(truly_new)
    print(f"Master endpoints.txt updated: now contains {total_now:,} endpoints.")

if __name__ == "__main__":
    main()
