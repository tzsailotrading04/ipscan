import os
import sys
import time
import json
import sqlite3
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

DB_PATH = "D:/DEpinFarm/cache/shodan_internetdb.sqlite3"
OUT_PATH = "D:/DEpinFarm/ip/harvest/shodan_expanded.txt"
LOG_PATH = "D:/DEpinFarm/work/shodan_expand.log"
FEEDS_RAW = "D:/DEpinFarm/ip/harvest/feeds_raw.txt"
MASTER_POOL = "D:/DEpinFarm/master_pool.txt"

# Candidate proxy ports to harvest
PROXY_PORTS = {
    80, 81, 443, 999, 1080, 1081, 1082, 1083, 3128, 3129,
    8000, 8001, 8080, 8081, 8082, 8085, 8088, 8090, 8118, 8123,
    8888, 8889, 9050, 9051, 9999, 10808, 10809
}

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ip_cache (
                ip TEXT PRIMARY KEY,
                status INTEGER,
                ports TEXT,
                timestamp REAL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON ip_cache(status)")
    return conn

def get_cached_ips():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    c = conn.cursor()
    c.execute("SELECT ip, status, ports FROM ip_cache")
    cached = {row[0]: (row[1], json.loads(row[2]) if row[2] else []) for row in c.fetchall()}
    conn.close()
    return cached

def fetch_ip(ip):
    url = f"https://internetdb.shodan.io/{ip}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            ports = data.get('ports', [])
            return ip, 200, ports
    except urllib.error.HTTPError as e:
        return ip, e.code, []
    except Exception as e:
        return ip, -1, []

def save_candidates(cached, known_pairs):
    new_candidates = set()
    for ip, (status, ports) in cached.items():
        if status == 200 and ports:
            for p in ports:
                if p in PROXY_PORTS:
                    cand = f"{ip}:{p}"
                    if cand not in known_pairs:
                        new_candidates.add(cand)
    with open(OUT_PATH, 'w', encoding='ascii') as f:
        for c in sorted(new_candidates):
            f.write(c + "\n")
    return len(new_candidates)

def run_expansion(limit=None):
    init_db()
    
    # 1. Gather all known ip:port pairs and unique IPs
    known_pairs = set()
    all_ips = set()

    for p in [MASTER_POOL, FEEDS_RAW]:
        if os.path.exists(p):
            with open(p, 'r', encoding='ascii', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if ':' in line:
                        known_pairs.add(line)
                        all_ips.add(line.split(':')[0])

    print(f"Total source unique IPs: {len(all_ips):,}", flush=True)
    print(f"Total known ip:port pairs: {len(known_pairs):,}", flush=True)

    # 2. Check cache
    cached = get_cached_ips()
    print(f"Currently cached IPs in SQLite: {len(cached):,}", flush=True)

    uncached_ips = [ip for ip in all_ips if ip not in cached]
    print(f"Uncached IPs to query: {len(uncached_ips):,}", flush=True)

    if limit and limit < len(uncached_ips):
        to_query = uncached_ips[:limit]
    else:
        to_query = uncached_ips

    # Save initial candidates from current cache
    cands_count = save_candidates(cached, known_pairs)
    print(f"Initial candidates written to disk: {cands_count:,}", flush=True)

    # 3. Query Shodan in parallel and save to cache in batches
    batch_size = 500
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    
    t0 = time.time()

    if to_query:
        print(f"Starting queries for {len(to_query):,} IPs with 16 workers...", flush=True)
        with ThreadPoolExecutor(max_workers=16) as executor:
            batch = []
            for idx, res in enumerate(executor.map(fetch_ip, to_query), 1):
                ip, status, ports = res
                batch.append((ip, status, json.dumps(ports), time.time()))
                cached[ip] = (status, ports)

                if len(batch) >= batch_size:
                    with conn:
                        conn.executemany("INSERT OR REPLACE INTO ip_cache VALUES (?, ?, ?, ?)", batch)
                    batch = []
                    rate = idx / (time.time() - t0)
                    print(f"Progress: {idx:,}/{len(to_query):,} ({idx/len(to_query)*100:.1f}%) - {rate:.1f} req/s", flush=True)
                    
                    # Periodic checkpoint save every 2,500 queries
                    if idx % 2500 == 0:
                        c_count = save_candidates(cached, known_pairs)
                        print(f"  [Checkpoint] Updated candidates in {OUT_PATH}: {c_count:,}", flush=True)

            if batch:
                with conn:
                    conn.executemany("INSERT OR REPLACE INTO ip_cache VALUES (?, ?, ?, ?)", batch)
    
    conn.close()

    # Final candidate generation
    final_count = save_candidates(cached, known_pairs)
    print(f"\nFinal brand new candidate ip:port pairs: {final_count:,}", flush=True)
    print(f"Total cached IPs: {len(cached):,}", flush=True)
    print(f"Saved candidates to {OUT_PATH}", flush=True)

    # Write log
    with open(LOG_PATH, 'a', encoding='utf-8') as lf:
        lf.write(f"RUN {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        lf.write(f"Source IPs: {len(all_ips):,}, Cached IPs: {len(cached):,}, New Candidates: {final_count:,}\n")

if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_expansion(lim)
