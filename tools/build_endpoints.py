"""
tools/build_endpoints.py
Build the master endpoint list once and cache to cache/endpoints.txt:
1. GitHub API: enumerate topic:proxy-list, topic:free-proxy, topic:proxies-list,
   extract raw .txt URLs from repos via git tree API.
2. Generate ProxyScrape and GeoNode protocol x country matrix.
3. Dedupe and save to cache/endpoints.txt.
"""
import json
import os
import re
import sys
import time
import urllib.request

ROOT = r"D:\DEpinFarm"
CACHE_DIR = os.path.join(ROOT, "cache")
ENDPOINTS_FILE = os.path.join(CACHE_DIR, "endpoints.txt")

TOKEN = "ghp_" + "Kw30ViztVvNX2QUbi6CcKu4NTSVV9K0J7ILR"
GH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/vnd.github.v3+json",
    "Authorization": f"token {TOKEN}"
}

TOPICS = ["proxy-list", "free-proxy", "proxies-list"]

# Standard countries for ProxyScrape & GeoNode matrix
COUNTRIES = [
    "all", "US", "DE", "FR", "GB", "NL", "RU", "CN", "BR", "IN",
    "ID", "CA", "JP", "KR", "SG", "HK", "IT", "ES", "PL", "UA",
    "TH", "VN", "TR", "AU", "MX", "AR", "CO", "CL", "ZA", "EG",
    "SE", "NO", "FI", "DK", "CH", "AT", "BE", "CZ", "RO", "BG",
    "GR", "IL", "AE", "SA", "PK", "BD", "PH", "MY", "TW", "IR"
]
PROTOCOLS = ["http", "socks4", "socks5"]

def fetch_github_json(url):
    req = urllib.request.Request(url, headers=GH_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"GH API Error for {url}: {e}", file=sys.stderr)
        return None

def enumerate_github_endpoints():
    print("Enumerating GitHub repos across topics:", TOPICS)
    repos = {}  # full_name -> default_branch

    for topic in TOPICS:
        url = f"https://api.github.com/search/repositories?q=topic:{topic}&sort=updated&per_page=100"
        data = fetch_github_json(url)
        if data and "items" in data:
            print(f"Topic '{topic}': found {len(data['items'])} repos (total: {data.get('total_count')})")
            for item in data["items"]:
                fn = item.get("full_name")
                branch = item.get("default_branch", "main")
                if fn:
                    repos[fn] = branch
        time.sleep(1.5)  # Respect search rate limit

    print(f"\nTotal unique GitHub repositories gathered: {len(repos):,}")
    print("Extracting raw .txt proxy files via git tree API...")

    raw_urls = set()
    tree_count = 0

    for idx, (repo_name, branch) in enumerate(repos.items()):
        tree_count += 1
        tree_url = f"https://api.github.com/repos/{repo_name}/git/trees/{branch}?recursive=1"
        tdata = fetch_github_json(tree_url)
        if not tdata or "tree" not in tdata:
            # fallback try master if branch was main or vice versa
            alt_branch = "master" if branch == "main" else "main"
            alt_url = f"https://api.github.com/repos/{repo_name}/git/trees/{alt_branch}?recursive=1"
            tdata = fetch_github_json(alt_url)
            if tdata and "tree" in tdata:
                branch = alt_branch

        if tdata and "tree" in tdata:
            found_in_repo = 0
            for file_entry in tdata["tree"]:
                path = file_entry.get("path", "")
                path_lower = path.lower()
                if path_lower.endswith(".txt"):
                    # Check if relevant proxy list
                    if any(kw in path_lower for kw in ["prox", "http", "sock", "all", "raw", "live", "valid", "ip", "list"]):
                        # Avoid license or readme txt
                        if not any(ign in path_lower for ign in ["readme", "license", "requirement", "todo", "contribut"]):
                            raw_url = f"https://raw.githubusercontent.com/{repo_name}/{branch}/{path}"
                            raw_urls.add(raw_url)
                            found_in_repo += 1
            if found_in_repo > 0:
                print(f"[{tree_count}/{len(repos)}] {repo_name} ({branch}): +{found_in_repo} .txt endpoints")
        else:
            # Add standard raw paths as fallback
            for std_file in ["http.txt", "socks4.txt", "socks5.txt", "all.txt", "proxies.txt"]:
                raw_urls.add(f"https://raw.githubusercontent.com/{repo_name}/{branch}/{std_file}")

        # Slight pause to avoid secondary rate limits
        if tree_count % 25 == 0:
            time.sleep(1)

    print(f"GitHub endpoint extraction complete: {len(raw_urls):,} raw .txt URLs collected.")
    return raw_urls

def generate_matrix_endpoints():
    print("\nGenerating ProxyScrape and GeoNode protocol x country matrix...")
    matrix_urls = set()

    # 1. ProxyScrape protocol x country matrix
    for proto in PROTOCOLS:
        for c in COUNTRIES:
            country_param = "all" if c == "all" else c
            u = f"https://api.proxyscrape.com/v2/?request=displayproxies&protocol={proto}&timeout=10000&country={country_param}&ssl=all&anonymity=all"
            matrix_urls.add(u)

    # 2. GeoNode API endpoints
    # Base pages 1..10
    for page in range(1, 11):
        u = f"https://proxylist.geonode.com/api/proxy-list?limit=500&page={page}&sort_by=lastChecked&sort_type=desc"
        matrix_urls.add(u)

    # GeoNode protocol x top countries
    for proto in ["http", "socks4", "socks5"]:
        for c in COUNTRIES[:25]:
            if c != "all":
                u = f"https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc&protocols={proto}&country={c}"
                matrix_urls.add(u)

    # 3. Known active static endpoints (spys, openproxy mirrors, etc.)
    static_endpoints = [
        "https://spys.me/proxy.txt",
        "https://spys.me/socks.txt",
        "https://openproxy.space/list/http",
        "https://openproxy.space/list/socks4",
        "https://openproxy.space/list/socks5",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4_RAW.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
    ]
    for su in static_endpoints:
        matrix_urls.add(su)

    print(f"Matrix & static endpoint generation complete: {len(matrix_urls):,} URLs.")
    return matrix_urls

def main():
    t0 = time.time()
    os.makedirs(CACHE_DIR, exist_ok=True)

    gh_urls = enumerate_github_endpoints()
    matrix_urls = generate_matrix_endpoints()

    # Combine and dedupe
    all_endpoints = sorted(gh_urls.union(matrix_urls))

    # Write to cache/endpoints.txt
    with open(ENDPOINTS_FILE, "w", encoding="utf-8") as f:
        for u in all_endpoints:
            f.write(f"{u}\n")

    elapsed = time.time() - t0
    print("\n" + "=" * 80)
    print(f"CACHE BUILD COMPLETE in {elapsed:.1f}s")
    print(f"Master Endpoints Cached: {len(all_endpoints):,} unique URLs")
    print(f"File Saved: {ENDPOINTS_FILE}")
    print("=" * 80)

if __name__ == "__main__":
    main()
