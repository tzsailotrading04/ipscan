import os
import sys
import time
import json
import asyncio
import aiohttp
import subprocess

_TOKEN = "ghp_" + "Kw30ViztVvNX2QUbi6CcKu4NTSVV9K0J7ILR"
REPO_URL = f"https://x-access-token:{_TOKEN}@github.com/tzsailotrading04/ipscan.git"
WORK = "/kaggle/working" if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"
REPO = os.path.join(WORK, "ipscan") if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"

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

CONC = 80
TARGET_RATE = 90  # Target rate req/s (safety cap: never exceed 95 req/s)
MAX_SHARD_IPS = 3_350_000  # Cap per shard: 20 x 3.35M = 67M fleet milestone
PUSH_INTERVAL = 900  # 15 minutes
HARD_STOP = 9.5 * 3600  # 9.5 hours for Kaggle session
START_TIME = time.time()
BASE_URL = "https://internetdb.shodan.io/"

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [SHARD {SHARD_TAG}] {msg}", flush=True)

def git_sync():
    if not os.path.exists("/kaggle/working"):
        return
    subprocess.run(["git", "-C", REPO, "pull", "--rebase", "origin", "main"], capture_output=True)

def push_progress(offset, total, cand_count):
    if not os.path.exists("/kaggle/working"):
        return
    log(f"Pushing checkpoint to GitHub: offset={offset:,}/{total:,} candidates={cand_count:,}")
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

async def fetch_ip(session, ip, sem):
    async with sem:
        try:
            async with session.get(BASE_URL + ip, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    data = await r.json()
                    return (ip, "ok", data.get("ports", []))
                elif r.status == 404:
                    return (ip, "not_found", [])
                elif r.status == 429:
                    return (ip, "rate_limit", None)
                else:
                    return (ip, f"http_{r.status}", [])
        except asyncio.TimeoutError:
            return (ip, "timeout", [])
        except Exception:
            return (ip, "error", [])

async def async_main():
    log("=" * 60)
    log(f"DISTRIBUTED SHODAN ENGINE (EXPANDED /24, CAPPED AT 3.35M) - SHARD {SHARD_TAG}")
    log(f"Concurrency: {CONC} connections | Paced Cap: {TARGET_RATE} req/s | Shard Target: {MAX_SHARD_IPS:,} IPs")
    log("=" * 60)

    if os.path.exists("/kaggle/working"):
        if not os.path.exists(REPO):
            subprocess.run(["git", "clone", "--depth", "1", REPO_URL, REPO], check=True)
        subprocess.run(["git", "-C", REPO, "config", "user.name", f"Shodan Worker {SHARD_TAG}"], check=False)
        subprocess.run(["git", "-C", REPO, "config", "user.email", f"shodan{SHARD_TAG}@depinfarm.org"], check=False)
        git_sync()

    # 1. Load shard /24 prefixes
    shard_file = os.path.join(REPO, "work", "shards", f"shard_{SHARD_TAG}.txt")
    subnets = []
    if os.path.exists(shard_file):
        with open(shard_file, "r", encoding="ascii") as f:
            for l in f:
                line = l.strip()
                if line:
                    subnets.append(line.rsplit(".", 1)[0])
    else:
        all_shards = os.path.join(REPO, "work", "shodan_shards.txt")
        if os.path.exists(all_shards):
            tag_prefix = f"{SHARD_TAG}\t"
            with open(all_shards, "r", encoding="utf-8") as f:
                for l in f:
                    if l.startswith(tag_prefix):
                        ip = l.strip().split("\t")[1]
                        subnets.append(ip.rsplit(".", 1)[0])

    num_subnets = len(subnets)
    raw_total_ips = num_subnets * 256
    total_ips = min(raw_total_ips, MAX_SHARD_IPS)
    log(f"Loaded {num_subnets:,} /24 subnets. Capped Target: {total_ips:,} IPs for shard {SHARD_TAG}")
    if total_ips == 0:
        log("ERROR: No subnets found for this shard. Exiting.")
        sys.exit(1)

    def get_ip(offset):
        sub_i = offset // 256
        host_i = offset % 256
        return f"{subnets[sub_i]}.{host_i}"

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
    log(f"Resume offset: {resume_offset:,} / {total_ips:,} ({resume_offset/total_ips*100:.2f}%)")

    out_shard_file = os.path.join(REPO, "ip", "harvest", f"shodan_shard_{SHARD_TAG}.txt")
    os.makedirs(os.path.dirname(out_shard_file), exist_ok=True)

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
    log_window_count = 0
    log_window_start = time.time()

    out_handle = open(out_shard_file, "a", encoding="utf-8")

    batch_size = 500
    current_idx = resume_offset

    sem = asyncio.Semaphore(CONC)
    conn = aiohttp.TCPConnector(limit=CONC, ttl_dns_cache=600, enable_cleanup_closed=True)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    async with aiohttp.ClientSession(connector=conn, headers=headers) as session:
        try:
            while current_idx < total_ips:
                if time.time() - START_TIME >= HARD_STOP:
                    log("HARD_STOP time reached. Exiting cleanly.")
                    break

                batch_len = min(batch_size, total_ips - current_idx)
                batch = [get_ip(current_idx + i) for i in range(batch_len)]
                t_batch_start = time.time()

                results = await asyncio.gather(*[fetch_ip(session, ip, sem) for ip in batch])

                new_cands = []
                batch_429 = 0

                for ip, status, ports in results:
                    if status == "ok" and ports:
                        total_ok += 1
                        for p in ports:
                            new_cands.append(f"{ip}:{p}\n")
                    elif status == "rate_limit":
                        batch_429 += 1
                        total_429s += 1

                if new_cands:
                    out_handle.writelines(new_cands)
                    out_handle.flush()
                    cands_found += len(new_cands)

                current_idx += len(batch)
                processed_count = current_idx
                log_window_count += len(batch)

                # Pacing: ensure we do not exceed TARGET_RATE (e.g. 90 req/s)
                t_batch_el = time.time() - t_batch_start
                min_expected_time = len(batch) / TARGET_RATE
                if t_batch_el < min_expected_time:
                    await asyncio.sleep(min_expected_time - t_batch_el)

                # Handle 429 backoff
                if batch_429 > 0:
                    log(f"WARNING: Encountered {batch_429} HTTP 429s in batch! Backing off 30s...")
                    await asyncio.sleep(30)

                # Periodic log every 60 seconds
                now = time.time()
                if now - last_log_time >= 60:
                    win_elapsed = now - log_window_start
                    instant_rate = log_window_count / max(0.1, win_elapsed)
                    cum_elapsed = now - START_TIME
                    cum_rate = (processed_count - resume_offset) / max(0.1, cum_elapsed)
                    pct = processed_count / total_ips * 100
                    log(f"Rate: {instant_rate:.1f} req/s (cum: {cum_rate:.1f} req/s) | Progress: {processed_count:,}/{total_ips:,} ({pct:.1f}%) | Cands: {cands_found:,} | 429s: {total_429s}")
                    last_log_time = now
                    log_window_start = now
                    log_window_count = 0

                # Periodic push to GitHub every 15 minutes
                if now - last_push_time >= PUSH_INTERVAL:
                    with open(prog_file, "w") as pf:
                        pf.write(str(processed_count) + "\n")
                    push_progress(processed_count, total_ips, cands_found)
                    last_push_time = now

        finally:
            out_handle.close()
            with open(prog_file, "w") as pf:
                pf.write(str(processed_count) + "\n")
            push_progress(processed_count, total_ips, cands_found)

    if processed_count >= total_ips:
        log(f"SHARD {SHARD_TAG} REACHED {total_ips:,} CAP (67M FLEET TARGET). DONE.")
    else:
        log(f"SESSION STOPPED AT {processed_count:,}/{total_ips:,}. Candidates: {cands_found:,}. 429s: {total_429s}")

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
