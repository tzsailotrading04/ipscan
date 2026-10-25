import os
import sys
import time
import json
import socket
import urllib.request
import urllib.error
import subprocess
from concurrent.futures import ThreadPoolExecutor

_TOKEN = "ghp_" + "Kw30ViztVvNX2QUbi6CcKu4NTSVV9K0J7ILR"
REPO_URL = f"https://x-access-token:{_TOKEN}@github.com/tzsailotrading04/ipscan.git"
WORK = "/kaggle/working" if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"
REPO = os.path.join(WORK, "ipscan") if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"

# Step 2: Read shard index from env var or argv
shard_str = os.environ.get("SHARD_INDEX", os.environ.get("SLICE_IDX", ""))
if not shard_str and len(sys.argv) > 1:
    for arg in sys.argv[1:]:
        if arg.isdigit():
            shard_str = arg
            break
if not shard_str:
    shard_str = "0"

SHARD_IDX = int(shard_str)
SHARD_TAG = f"{SHARD_IDX:02d}"

WORKERS = 16
MAX_REQS_PER_SEC = 90
PUSH_INTERVAL = 900  # 15 minutes
HARD_STOP = 9.5 * 3600  # 9.5 hours for Kaggle session
START_TIME = time.time()

PROXY_PORTS = {80, 443, 8080, 3128, 1080, 8000, 8888, 8081, 8085, 8443, 81, 9050, 10808, 10809}

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [SHARD {SHARD_TAG}] {msg}", flush=True)

def git_sync():
    if not os.path.exists("/kaggle/working"):
        return
    subprocess.run(["git", "-C", REPO, "pull", "--rebase", "origin", "main"], capture_output=True)

def push_progress(offset, total, cand_count):
    if not os.path.exists("/kaggle/working"):
        return
    log(f"Pushing checkpoint to GitHub: offset={offset}/{total} candidates={cand_count}")
    prog_rel = f"ip/harvest/shodan_progress_{SHARD_TAG}.txt"
    shard_rel = f"ip/harvest/shodan_shard_{SHARD_TAG}.txt"
    
    for attempt in range(5):
        subprocess.run(["git", "-C", REPO, "pull", "--rebase", "--autostash", "origin", "main"], capture_output=True)
        subprocess.run(["git", "-C", REPO, "add", prog_rel, shard_rel], check=False)
        msg = f"cl_shodan_{SHARD_TAG}: offset={offset}/{total} cands={cand_count}"
        subprocess.run(["git", "-C", REPO, "commit", "-m", msg], capture_output=True)
        r = subprocess.run(["git", "-C", REPO, "push", "origin", "main"], capture_output=True, text=True)
        if r.returncode == 0:
            log("GIT_PUSH_OK")
            return
        time.sleep(2)
    log("GIT_PUSH_FAILED after 5 attempts")

def query_ip(ip):
    url = f"https://internetdb.shodan.io/{ip}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read()
            obj = json.loads(data)
            return ("ok", obj.get("ports", []))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return ("not_found", [])
        elif e.code == 429:
            return ("rate_limit", [])
        return ("err_http", [])
    except Exception:
        return ("err_other", [])

def main():
    log("=" * 60)
    log(f"DISTRIBUTED SHODAN ENGINE - SHARD {SHARD_TAG}")
    log(f"Concurrency: {WORKERS} workers | Rate Cap: {MAX_REQS_PER_SEC} req/s")
    log("=" * 60)

    if os.path.exists("/kaggle/working"):
        if not os.path.exists(REPO):
            subprocess.run(["git", "clone", "--depth", "1", REPO_URL, REPO], check=True)
        subprocess.run(["git", "-C", REPO, "config", "user.name", f"Shodan Worker {SHARD_TAG}"], check=False)
        subprocess.run(["git", "-C", REPO, "config", "user.email", f"shodan{SHARD_TAG}@depinfarm.org"], check=False)
        git_sync()

    # 1. Load shard target IPs
    shard_file = os.path.join(REPO, "work", "shards", f"shard_{SHARD_TAG}.txt")
    ips = []
    if os.path.exists(shard_file):
        with open(shard_file, "r", encoding="ascii") as f:
            ips = [l.strip() for l in f if l.strip()]
    else:
        # Fallback to reading work/shodan_shards.txt
        all_shards = os.path.join(REPO, "work", "shodan_shards.txt")
        if os.path.exists(all_shards):
            tag_prefix = f"{SHARD_TAG}\t"
            with open(all_shards, "r", encoding="utf-8") as f:
                ips = [l.strip().split("\t")[1] for l in f if l.startswith(tag_prefix)]

    total_ips = len(ips)
    log(f"Loaded {total_ips:,} target IPs for shard {SHARD_TAG}")
    if total_ips == 0:
        log("ERROR: No IPs found for this shard. Exiting.")
        sys.exit(1)

    # 2. Read resume offset
    prog_file = os.path.join(REPO, "ip", "harvest", f"shodan_progress_{SHARD_TAG}.txt")
    resume_offset = 0
    if os.path.exists(prog_file):
        try:
            with open(prog_file, "r") as f:
                val = f.read().strip()
                if val.isdigit():
                    resume_offset = int(val)
        except Exception:
            pass
    log(f"Resume offset: {resume_offset:,} / {total_ips:,}")

    out_shard_file = os.path.join(REPO, "ip", "harvest", f"shodan_shard_{SHARD_TAG}.txt")
    os.makedirs(os.path.dirname(out_shard_file), exist_ok=True)

    # Count existing candidates
    cands_found = 0
    if os.path.exists(out_shard_file):
        with open(out_shard_file, "r", encoding="utf-8", errors="ignore") as f:
            cands_found = sum(1 for _ in f)
    log(f"Existing candidates in shard file: {cands_found:,}")

    # 3. Main processing loop
    last_push_time = time.time()
    last_log_time = time.time()
    processed_count = resume_offset
    total_429s = 0
    total_ok = 0

    out_handle = open(out_shard_file, "a", encoding="utf-8")

    batch_size = 500
    current_idx = resume_offset

    pool = ThreadPoolExecutor(max_workers=WORKERS)

    try:
        while current_idx < total_ips:
            if time.time() - START_TIME >= HARD_STOP:
                log("HARD_STOP time reached. Exiting cleanly.")
                break

            batch = ips[current_idx : current_idx + batch_size]
            t_batch_start = time.time()

            results = list(pool.map(query_ip, batch))

            new_cands = []
            batch_429 = 0
            for ip, (status, ports) in zip(batch, results):
                if status == "ok":
                    total_ok += 1
                    for p in ports:
                        new_cands.append(f"{ip}:{p}\n")
                elif status == "rate_limit":
                    batch_429 += 1
                    total_429s += 1

            # Append candidates
            if new_cands:
                out_handle.writelines(new_cands)
                out_handle.flush()
                cands_found += len(new_cands)

            current_idx += len(batch)
            processed_count = current_idx

            # Pacing: ensure we do not exceed MAX_REQS_PER_SEC
            t_batch_el = time.time() - t_batch_start
            min_expected_time = len(batch) / MAX_REQS_PER_SEC
            if t_batch_el < min_expected_time:
                time.sleep(min_expected_time - t_batch_el)

            # Handle 429 backoff if encountered
            if batch_429 > 0:
                log(f"WARNING: Encountered {batch_429} HTTP 429s in batch! Cooling down 60 seconds...")
                time.sleep(60)

            # Periodic log (every 30s)
            now = time.time()
            if now - last_log_time >= 30:
                elapsed = now - START_TIME
                speed = (processed_count - resume_offset) / max(1.0, elapsed)
                log(f"Progress: {processed_count:,}/{total_ips:,} ({processed_count/total_ips*100:.1f}%) | Speed: {speed:.1f} req/s | Cands: {cands_found:,} | 429s: {total_429s}")
                last_log_time = now

            # Periodic push to GitHub (every 15 min)
            if now - last_push_time >= PUSH_INTERVAL:
                with open(prog_file, "w") as pf:
                    pf.write(str(processed_count) + "\n")
                push_progress(processed_count, total_ips, cands_found)
                last_push_time = now

    finally:
        pool.shutdown(wait=False)
        out_handle.close()
        # Final save of progress
        with open(prog_file, "w") as pf:
            pf.write(str(processed_count) + "\n")
        push_progress(processed_count, total_ips, cands_found)

    log(f"FINISHED SHARD {SHARD_TAG}. Total processed: {processed_count:,}/{total_ips:,}. Candidates: {cands_found:,}. 429s: {total_429s}")

if __name__ == "__main__":
    main()
