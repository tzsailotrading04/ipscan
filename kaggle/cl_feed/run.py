#!/usr/bin/env python3
r"""
DEpin Farm 100-Source Feeder Kernel (v98.180)
- Runs autonomously as a Kaggle batch CPU kernel (remruata/ipscan-cl-feed)
- Universal regex parser (\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}\b)
- Validates octets 0-255, ports 1-65535, drops private/bogon IPs
- Concurrent fetcher: 40 workers, 20s timeout, 3 retries with backoff
- Skips failing source for 30 min after 3 consecutive failures
- 900s cycle loop, one slow source never stalls cycle
- Dedupes against cache/harvest_seen_set.txt, writing new entries to ip/harvest/queue/q_<ts>.txt
- Verbatim git push helper, 3 retries with jitter, clean exit before 12h
"""
import os
import re
import sys
import time
import random
import urllib.request
import urllib.error
import ssl
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

_TOKEN = "ghp_" + "Kw30ViztVvNX2QUbi6CcKu4NTSVV9K0J7ILR"
REPO_URL = f"https://x-access-token:{_TOKEN}@github.com/tzsailotrading04/ipscan.git"
WORK = "/kaggle/working" if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"
REPO = os.path.join(WORK, "ipscan") if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"

SOURCES_FILE = os.path.join(REPO, "tools", "sources.txt")
SEEN_FILE = os.path.join(REPO, "cache", "harvest_seen_set.txt")
QUEUE_DIR = os.path.join(REPO, "ip", "harvest", "queue")

CONCURRENCY = 40
TIMEOUT = 20.0
MAX_RETRIES = 3
CYCLE_INTERVAL = 900
MAX_RUNTIME_SEC = 41400  # Clean exit before 12h limit

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0"
]

IP_PORT_REGEX = re.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})\b')

def log(msg):
    t = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{t}] {msg}", flush=True)

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

    # Validate octets 0-255
    if not (0 <= o1 <= 255 and 0 <= o2 <= 255 and 0 <= o3 <= 255 and 0 <= o4 <= 255):
        return False

    # Drop private/bogon IPs
    if o1 == 0 or o1 == 10 or o1 == 127:
        return False
    if o1 == 192 and o2 == 168:
        return False
    if o1 == 172 and (16 <= o2 <= 31):
        return False
    if o1 == 169 and o2 == 254:
        return False
    if o1 == 100 and (64 <= o2 <= 127):
        return False
    if o1 >= 224:
        return False

    return True

def parse_proxies_from_raw(raw_text):
    results = set()
    if not raw_text:
        return results
    for ip, port_str in IP_PORT_REGEX.findall(raw_text):
        try:
            port = int(port_str)
            if is_valid_public_ipv4(ip, port):
                results.add(f"{ip}:{port}")
        except Exception:
            continue
    return results

# Failure tracker: {url: {"consecutive": int, "cooldown_until": float}}
source_state = {}

def fetch_source(url):
    now = time.time()
    st = source_state.setdefault(url, {"consecutive": 0, "cooldown_until": 0.0})
    if now < st["cooldown_until"]:
        rem = int(st["cooldown_until"] - now)
        return url, False, set(), f"COOLDOWN ({rem}s remaining)", 0

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
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
                raw_text = resp.read().decode("utf-8", errors="ignore")
                proxies = parse_proxies_from_raw(raw_text)
                st["consecutive"] = 0
                st["cooldown_until"] = 0.0
                return url, True, proxies, "", attempt
        except Exception as e:
            last_err = str(e)
            if attempt < MAX_RETRIES:
                backoff = (2 ** (attempt - 1)) + random.uniform(0.5, 1.5)
                time.sleep(backoff)

    st["consecutive"] += 1
    if st["consecutive"] >= 3:
        st["cooldown_until"] = now + 1800  # 30 min cooldown
    return url, False, set(), last_err, MAX_RETRIES

def git_sync_and_push(msg):
    try:
        subprocess.run(["git", "-C", REPO, "add", "-A"], check=False)
        st = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True)
        if not st.stdout.strip():
            return True
        c_res = subprocess.run(["git", "-C", REPO, "commit", "-m", msg], capture_output=True, text=True)
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
                return True
            print(f"[GIT ERROR] push failed attempt {attempt}/16: {p_res.stderr.strip()}", file=sys.stderr, flush=True)
            backoff = min(60, 2 ** attempt) * random.uniform(0.5, 1.5)
            time.sleep(backoff)
        return False
    except Exception as e:
        print(f"[GIT EXCEPTION] {e}", file=sys.stderr, flush=True)
        return False

def main():
    log("=" * 80)
    log("  DEpin Farm 100-Source Feeder Kernel (cl_feed) Initializing")
    log(f"  Concurrency: {CONCURRENCY} | Timeout: {TIMEOUT}s | Cycle: {CYCLE_INTERVAL}s")
    log("=" * 80)

    start_kernel_t = time.time()

    if os.path.exists("/kaggle/working"):
        if not os.path.exists(REPO):
            subprocess.run(["git", "clone", "--depth", "1", REPO_URL, REPO], check=True)
        subprocess.run(["git", "-C", REPO, "config", "user.name", "CL-FEED"], check=False)
        subprocess.run(["git", "-C", REPO, "config", "user.email", "cl_feed@depinfarm.org"], check=False)

    os.makedirs(QUEUE_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)

    # Load seen set
    seen_set = set()
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    entry = line.strip().split()[0] if line.strip() else ""
                    if entry:
                        seen_set.add(entry)
            log(f"Loaded existing seen set: {len(seen_set):,} entries")
        except Exception as e:
            log(f"Warning reading seen set: {e}")

    cycle = 0
    while True:
        cycle += 1
        cycle_start_t = time.time()

        # Clean exit before 12h
        if cycle_start_t - start_kernel_t >= MAX_RUNTIME_SEC:
            log(f"Kernel reached maximum runtime ({cycle_start_t - start_kernel_t:.0f}s). Clean exit.")
            sys.exit(0)

        # Pull latest changes from git
        subprocess.run(["git", "-C", REPO, "pull", "--rebase", "origin", "main"], capture_output=True, check=False)

        # Load sources
        if not os.path.exists(SOURCES_FILE):
            log(f"ERROR: {SOURCES_FILE} not found!")
            time.sleep(30)
            continue

        with open(SOURCES_FILE, "r", encoding="utf-8") as f:
            sources = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

        log(f"--- STARTING CYCLE {cycle} ({len(sources)} sources) ---")

        src_ok = 0
        src_err = 0
        cycle_candidates = set()

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
            future_to_url = {executor.submit(fetch_source, u): u for u in sources}
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    src_url, ok, proxies, err, att = future.result()
                    if ok:
                        src_ok += 1
                        cycle_candidates.update(proxies)
                        print(f"  [source] OK ({len(proxies):>5} proxies, att {att}) {src_url[:70]}", flush=True)
                    else:
                        src_err += 1
                        print(f"  [source] FAIL ({err[:35]}) {src_url[:70]}", flush=True)
                except Exception as exc:
                    src_err += 1
                    print(f"  [source] EXC {exc} {url[:70]}", flush=True)

        # Dedupe against seen set
        novel_entries = []
        dup_count = 0
        for cand in cycle_candidates:
            if cand in seen_set:
                dup_count += 1
            else:
                novel_entries.append(cand)
                seen_set.add(cand)

        # Count current queue files
        queue_files = [f for f in os.listdir(QUEUE_DIR) if f.startswith("q_") and f.endswith(".txt")]
        files_count = len(queue_files)

        if novel_entries:
            ts = int(time.time())
            q_file = os.path.join(QUEUE_DIR, f"q_{ts}.txt")
            with open(q_file, "w", encoding="utf-8") as qf:
                for entry in sorted(novel_entries):
                    qf.write(f"{entry}\n")
            files_count += 1

            # Append to seen set immediately
            with open(SEEN_FILE, "a", encoding="utf-8") as sf:
                for entry in sorted(novel_entries):
                    sf.write(f"{entry}\n")

            commit_msg = f"[feed] cycle={cycle} new={len(novel_entries)} total_seen={len(seen_set)}"
            git_sync_and_push(commit_msg)
        else:
            print("FEEDER_DRY", flush=True)

        print(f"[feed] cycle={cycle} src_ok={src_ok} src_err={src_err} new={len(novel_entries)} dup={dup_count} files={files_count}", flush=True)

        elapsed = time.time() - cycle_start_t
        sleep_time = max(10, CYCLE_INTERVAL - elapsed)
        log(f"Cycle {cycle} complete in {elapsed:.1f}s. Sleeping {sleep_time:.1f}s...")
        time.sleep(sleep_time)

if __name__ == "__main__":
    main()
