#!/usr/bin/env python3
"""
DEpin Farm 100-Source Feeder (v98.178)
- Loads 100 sources from tools/sources.txt
- Universal regex parser (\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}\b) for text, JSON, HTML
- Strict validation: octets 0-255, ports 1-65535, drops private IPs (10.x, 127.x, 192.168.x, 172.16-31.x)
- Concurrent fetcher: 40 workers, 20s timeout, 3 retries with backoff
- Per-source failure counter and detailed report
- Outputs unique valid candidates to ip/harvest/feeds_raw.txt and cache/candidate_queue.txt
"""
import os
import re
import sys
import time
import random
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT = r"D:\DEpinFarm"
SOURCES_FILE = os.path.join(REPO_ROOT, "tools", "sources.txt")
FEEDS_RAW_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "feeds_raw.txt")
QUEUE_FILE = os.path.join(REPO_ROOT, "cache", "candidate_queue.txt")

CONCURRENCY = 40
TIMEOUT = 20.0
MAX_RETRIES = 3

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0"
]

IP_PORT_REGEX = re.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})\b')

def is_valid_public_ipv4(ip_str, port_int):
    if not (1 <= port_int <= 65535):
        return False
    parts = ip_str.split('.')
    if len(parts) != 4:
        return False
    try:
        o1, o2, o3, o4 = (int(p) for p in parts)
    except ValueError:
        return False

    # All four octets 0-255
    if not (0 <= o1 <= 255 and 0 <= o2 <= 255 and 0 <= o3 <= 255 and 0 <= o4 <= 255):
        return False

    # Drop 0.x, 10.x, 127.x (loopback), 192.168.x, 172.16-31.x, 169.254.x, multicast/reserved >= 224
    if o1 == 0 or o1 == 10 or o1 == 127:
        return False
    if o1 == 192 and o2 == 168:
        return False
    if o1 == 172 and (16 <= o2 <= 31):
        return False
    if o1 == 169 and o2 == 254:
        return False
    if o1 >= 224:
        return False

    return True

def parse_proxies_from_raw(raw_text):
    """
    Universal parser: regex matches \b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}\b
    Works on plain text, JSON, and HTML. Validates public IPv4 + port.
    """
    results = set()
    if not raw_text:
        return results

    matches = IP_PORT_REGEX.findall(raw_text)
    for ip, port_str in matches:
        try:
            port = int(port_str)
            if is_valid_public_ipv4(ip, port):
                results.add(f"{ip}:{port}")
        except Exception:
            continue
    return results

def fetch_source(url):
    """
    Fetches a single source URL with up to MAX_RETRIES attempts and backoff.
    Returns: (url, success_bool, proxies_set, error_str, attempts_count)
    """
    last_err = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            ua = random.choice(USER_AGENTS)
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml,text/plain,application/json;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Connection": "close"
                }
            )
            # Create SSL context that does not fail on minor legacy cert issues for third-party scrapers
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
                raw_bytes = resp.read()
                raw_text = raw_bytes.decode("utf-8", errors="ignore")
                proxies = parse_proxies_from_raw(raw_text)
                return url, True, proxies, "", attempt
        except Exception as e:
            last_err = str(e)
            if attempt < MAX_RETRIES:
                backoff = (2 ** (attempt - 1)) + random.uniform(0.5, 1.5)
                time.sleep(backoff)

    return url, False, set(), last_err, MAX_RETRIES

def run_feeder():
    if not os.path.exists(SOURCES_FILE):
        print(f"Error: {SOURCES_FILE} not found!")
        return

    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        sources = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    total_sources = len(sources)
    print("=" * 80)
    print(f"  100-SOURCE FEEDER v98.178 - {total_sources} SOURCES, CONCURRENCY {CONCURRENCY}, TIMEOUT {TIMEOUT}s")
    print("=" * 80)

    start_time = time.time()
    successful_sources = 0
    failed_sources = 0
    failure_counter = {}
    source_yields = {}
    all_proxies = set()

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        future_map = {executor.submit(fetch_source, u): u for u in sources}
        for future in as_completed(future_map):
            url = future_map[future]
            try:
                src_url, ok, proxies, err, attempts = future.result()
                if ok:
                    successful_sources += 1
                    source_yields[src_url] = len(proxies)
                    all_proxies.update(proxies)
                    print(f"  [OK] ({len(proxies):>5} proxies, att {attempts}) {src_url[:75]}")
                else:
                    failed_sources += 1
                    failure_counter[src_url] = failure_counter.get(src_url, 0) + 1
                    print(f"  [FAIL] (att {attempts}, err: {err[:35]}) {src_url[:65]}")
            except Exception as exc:
                failed_sources += 1
                failure_counter[url] = failure_counter.get(url, 0) + 1
                print(f"  [EXC] {url[:65]}: {exc}")

    elapsed = time.time() - start_time
    total_yield = len(all_proxies)

    # Load existing seen set / feeds if present to calculate novelty
    existing_feeds = set()
    if os.path.exists(FEEDS_RAW_FILE):
        try:
            with open(FEEDS_RAW_FILE, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    endpoint = line.strip().split()[0]
                    if endpoint:
                        existing_feeds.add(endpoint)
        except Exception:
            pass

    novel_proxies = all_proxies - existing_feeds

    # Append all novel proxies to candidate queue
    os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)
    with open(QUEUE_FILE, "a", encoding="utf-8") as qf:
        for p in sorted(novel_proxies):
            qf.write(f"{p}\tFEED_100\n")

    # Update feeds_raw.txt atomically
    all_combined = existing_feeds | all_proxies
    os.makedirs(os.path.dirname(FEEDS_RAW_FILE), exist_ok=True)
    temp_feeds = FEEDS_RAW_FILE + ".tmp"
    with open(temp_feeds, "w", encoding="utf-8") as tf:
        for p in sorted(all_combined):
            tf.write(f"{p}\n")
    os.replace(temp_feeds, FEEDS_RAW_FILE)

    print("\n" + "=" * 80)
    print("  FEEDER RUN SUMMARY")
    print("=" * 80)
    print(f"  Total Sources:          {total_sources}")
    print(f"  Successful Sources:     {successful_sources} ({successful_sources/total_sources*100:.1f}%)")
    print(f"  Failed Sources:         {failed_sources} ({failed_sources/total_sources*100:.1f}%)")
    print(f"  Total Unique Proxies:   {total_yield:,}")
    print(f"  Brand New Novel Proxies: {len(novel_proxies):,}")
    print(f"  Total feeds_raw.txt:    {len(all_combined):,}")
    print(f"  Elapsed Time:           {elapsed:.2f}s ({total_sources/elapsed:.1f} sources/sec)")

    if failure_counter:
        print("\n--- PER-SOURCE FAILURE COUNTER ---")
        for f_url, fails in sorted(failure_counter.items(), key=lambda x: x[1], reverse=True)[:15]:
            print(f"  Failures: {fails} | {f_url}")

if __name__ == "__main__":
    run_feeder()
