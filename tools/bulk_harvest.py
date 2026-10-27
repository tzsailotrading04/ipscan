import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = r"D:\DEpinFarm"
BULK_DIR = os.path.join(ROOT, "ip", "harvest", "bulk")
OUT_FILE = os.path.join(ROOT, "ip", "harvest", "bulk_all.txt")
os.makedirs(BULK_DIR, exist_ok=True)

source_counts = {}
all_proxies = set()

def normalize_add(cand_str, source_name):
    # Match valid IPv4:port
    m = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{2,5})$', cand_str.strip())
    if m:
        ip, port = m.groups()
        p_int = int(port)
        if 1 <= p_int <= 65535:
            octets = [int(o) for o in ip.split('.')]
            if all(0 <= o <= 255 for o in octets) and octets[0] not in (0, 10, 127):
                entry = f"{ip}:{port}"
                all_proxies.add(entry)
                source_counts[source_name] = source_counts.get(source_name, 0) + 1

# ==========================================
# 1. KAGGLE DATASETS
# ==========================================
print("=== 1. EXTRACTING FROM KAGGLE DATASETS ===", flush=True)

# 1a. charles1995/free-public-proxies-2026
f_charles = os.path.join(BULK_DIR, "charles1995_free-public-proxies-2026", "proxies.csv")
if os.path.exists(f_charles):
    with open(f_charles, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 2 and parts[1].isdigit():
                normalize_add(f"{parts[0]}:{parts[1]}", "kaggle_charles1995")

# 1b. litportnet/free-proxy-observations
f_litport = os.path.join(BULK_DIR, "litportnet_free-proxy-observations", "all.csv")
if os.path.exists(f_litport):
    with open(f_litport, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 3 and parts[2].isdigit():
                normalize_add(f"{parts[1]}:{parts[2]}", "kaggle_litportnet")

# 1c. signalspikes/internet-port-scan-1
f_signals = os.path.join(BULK_DIR, "signalspikes_internet-port-scan-1", "scan-04_27_2021-1619562631-C17RqCX0.json")
if os.path.exists(f_signals):
    print("Parsing signalspikes internet port scan (streaming JSON lines)...", flush=True)
    count = 0
    with open(f_signals, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if '"ip":' in line and '"ports":' in line:
                m_ip = re.search(r'"ip":\s*"([^"]+)"', line)
                m_ports = re.findall(r'"port":\s*(\d+)', line)
                if m_ip and m_ports:
                    ip = m_ip.group(1)
                    for p in m_ports:
                        normalize_add(f"{ip}:{p}", "kaggle_signalspikes_scan")
                        count += 1
                        if count >= 300_000:  # extract top 300k open ports
                            break
            if count >= 300_000:
                break
    print(f"Extracted {count:,} open ports from signalspikes.", flush=True)

# ==========================================
# 2. SPYS.ONE SCRAPING
# ==========================================
print("\n=== 2. SCRAPING SPYS.ONE TABLES ===", flush=True)
spys_pages = ['free-proxy-list', 'socks-proxy-list', 'http-proxy-list', 'anonymous-proxy-list', 'https-ssl-proxy']
for page in spys_pages:
    url = f"https://spys.one/en/{page}/"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=12) as r:
            html = r.read().decode('utf-8', errors='ignore')
        var_dict = {}
        for m in re.finditer(r'([a-z0-9]+)\s*=\s*(\d+);', html):
            var_dict[m.group(1)] = int(m.group(2))
        for _ in range(5):
            for m in re.finditer(r'([a-z0-9]+)\s*=\s*(\d+)\s*\^\s*([a-z0-9]+)', html):
                k, num, ref = m.groups()
                if ref in var_dict:
                    var_dict[k] = int(num) ^ var_dict[ref]
        rows = re.findall(r'(\d+\.\d+\.\d+\.\d+).*?<script type="text/javascript">document\.write\("<font class=spy2>:<\\/font>"\+(.*?)\)</script>', html, re.DOTALL)
        for ip, port_expr in rows:
            tokens = re.findall(r'\(([a-z0-9]+)\^([a-z0-9]+)\)', port_expr)
            digits = ''.join(str(var_dict[a] ^ var_dict[b]) for a, b in tokens if a in var_dict and b in var_dict)
            if digits:
                normalize_add(f"{ip}:{digits}", f"spys_one_{page}")
        print(f"Scraped spys.one/{page}: {len(rows)} rows", flush=True)
    except Exception as e:
        print(f"Failed spys.one/{page}: {e}", flush=True)

# Also spys.me official feeds
for me_url, name in [('https://spys.me/proxy.txt', 'spys_me_http'), ('https://spys.me/socks.txt', 'spys_me_socks')]:
    try:
        req = urllib.request.Request(me_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode('utf-8', errors='ignore')
            for c in re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b', body):
                normalize_add(c, name)
    except Exception as e:
        print(f"Failed {me_url}: {e}", flush=True)

# ==========================================
# 3. PUBLIC LIST REPOS (EXISTING + 15+ NEW)
# ==========================================
print("\n=== 3. FETCHING PUBLIC LIST REPOS ===", flush=True)

public_urls = [
    # Existing repos
    ('monosans_all', 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/all.txt'),
    ('monosans_http', 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt'),
    ('monosans_socks4', 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt'),
    ('monosans_socks5', 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt'),
    ('proxifly_http', 'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt'),
    ('proxifly_socks4', 'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks4/data.txt'),
    ('proxifly_socks5', 'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt'),
    ('proxmint_all', 'https://raw.githubusercontent.com/proxmint/free-proxy-list/main/proxies/all.txt'),
    ('proxmint_http', 'https://raw.githubusercontent.com/proxmint/free-proxy-list/main/proxies/http.txt'),
    ('proxmint_socks5', 'https://raw.githubusercontent.com/proxmint/free-proxy-list/main/proxies/socks5.txt'),
    ('thespeedx_http', 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt'),
    ('thespeedx_socks4', 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt'),
    ('thespeedx_socks5', 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt'),
    ('r00tee_http', 'https://raw.githubusercontent.com/r00tee/Proxy-List/main/Https.txt'),
    ('r00tee_socks4', 'https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks4.txt'),
    ('r00tee_socks5', 'https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks5.txt'),
    ('dpangestuw_all', 'https://raw.githubusercontent.com/dpangestuw/Free-Proxy/main/All_proxies.txt'),
    ('dpangestuw_http', 'https://raw.githubusercontent.com/dpangestuw/Free-Proxy/main/http_proxies.txt'),
    ('dpangestuw_socks4', 'https://raw.githubusercontent.com/dpangestuw/Free-Proxy/main/socks4_proxies.txt'),
    ('dpangestuw_socks5', 'https://raw.githubusercontent.com/dpangestuw/Free-Proxy/main/socks5_proxies.txt'),
    ('proxyspace_http', 'https://proxyspace.pro/http.txt'),
    ('proxyspace_https', 'https://proxyspace.pro/https.txt'),
    ('proxyspace_socks4', 'https://proxyspace.pro/socks4.txt'),
    ('proxyspace_socks5', 'https://proxyspace.pro/socks5.txt'),
    ('komutan234_http', 'https://raw.githubusercontent.com/komutan234/Proxy-List-Free/main/proxies/http.txt'),
    ('komutan234_socks5', 'https://raw.githubusercontent.com/komutan234/Proxy-List-Free/main/proxies/socks5.txt'),
    ('kangproxy_all', 'https://cdn.jsdelivr.net/gh/officialputuid/KangProxy@main/xResults/Proxies.txt'),
    ('kangproxy_http', 'https://cdn.jsdelivr.net/gh/officialputuid/KangProxy@main/http/http.txt'),

    # NEW REPOS (15+ new distinct repos)
    ('hookzof_socks5', 'https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt'),
    ('zevtyardt_http', 'https://raw.githubusercontent.com/zevtyardt/proxy-list/main/http.txt'),
    ('zevtyardt_socks5', 'https://raw.githubusercontent.com/zevtyardt/proxy-list/main/socks5.txt'),
    ('murongpig_http', 'https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/http.txt'),
    ('murongpig_socks5', 'https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks5.txt'),
    ('ercindedeoglu_http', 'https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/http.txt'),
    ('ercindedeoglu_socks5', 'https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks5.txt'),
    ('anonym0uswork_http', 'https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/master/proxy_files/http_proxies.txt'),
    ('anonym0uswork_socks5', 'https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/master/proxy_files/socks5_proxies.txt'),
    ('b4rc0de_http', 'https://raw.githubusercontent.com/B4RC0DE-TM/proxy-list/main/HTTP.txt'),
    ('b4rc0de_socks5', 'https://raw.githubusercontent.com/B4RC0DE-TM/proxy-list/main/SOCKS5.txt'),
    ('jetkai_http', 'https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt'),
    ('jetkai_socks5', 'https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt'),
    ('aliilapro_http', 'https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/http.txt'),
    ('aliilapro_socks5', 'https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/socks5.txt'),
    ('sunny9577_http', 'https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/http_proxies.txt'),
    ('hendrikbgr_all', 'https://raw.githubusercontent.com/hendrikbgr/Free-Proxy-Repo/master/proxy_list.txt'),
    ('vakhov_http', 'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt'),
    ('vakhov_socks5', 'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt'),
    ('zloiuser_http', 'https://raw.githubusercontent.com/zloi-user/hideip.me/master/http.txt'),
    ('zloiuser_socks5', 'https://raw.githubusercontent.com/zloi-user/hideip.me/master/socks5.txt'),
    ('shiftytr_socks5', 'https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt'),
    ('roosterkid_https', 'https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt'),
    ('roosterkid_socks5', 'https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt'),
    ('prxchk_http', 'https://raw.githubusercontent.com/prxchk/proxy-list/main/http.txt'),
    ('prxchk_socks5', 'https://raw.githubusercontent.com/prxchk/proxy-list/main/socks5.txt'),
]

def fetch_feed(item):
    name, url = item
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode('utf-8', errors='ignore')
            cands = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b', body)
            for c in cands:
                normalize_add(c, name)
            print(f"Fetched {name}: {len(cands):,} candidates", flush=True)
    except Exception as e:
        print(f"Failed {name} ({url}): {e}", flush=True)

with ThreadPoolExecutor(max_workers=10) as ex:
    list(ex.map(fetch_feed, public_urls))

# Write output file
print("\n=== WRITING DEDUPED BULK_ALL.TXT ===", flush=True)
with open(OUT_FILE, "w", encoding="utf-8") as f:
    for p in sorted(all_proxies):
        f.write(p + "\n")

print(f"\nWritten {len(all_proxies):,} unique ip:port to {OUT_FILE}")
print("\n=== SOURCE BREAKDOWN ===")
for s, cnt in sorted(source_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"  {s}: {cnt:,}")
print(f"TOTAL UNIQUE PROXIES: {len(all_proxies):,}")
