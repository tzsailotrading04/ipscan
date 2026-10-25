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

# ---- v98 tuning ----
NUM_SHARDS = int(os.environ.get("NUM_SHARDS", "20"))
CONC = 180                 # v98: Little's Law -> 88 req/s x 2.0s latency = 176 workers
TARGET_RATE = 88.0         # paced ceiling, safely under the ~95 req/s Cloudflare wall
MAX_SHARD_IPS = 6_000_000  # v98: was 3_350_000 -> fleet 120M IPs
PUSH_INTERVAL = 300
HARD_STOP = 9.5 * 3600
START_TIME = time.time()
BASE_URL = "https://internetdb.shodan.io/"


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [SHARD {SHARD_TAG}] {msg}", flush=True)


def git_sync():
    if not os.path.exists("/kaggle/working"):
        return
    subprocess.run(
        ["git", "-C", REPO, "pull", "--rebase", "--autostash", "origin", "main"],
        capture_output=True,
    )


def push_progress(offset, total, cand_count):
    if not os.path.exists("/kaggle/working"):
        return
    log(f"Pushing checkpoint to GitHub: offset={offset:,}/{total:,} candidates={cand_count:,}")
    prog_rel = f"ip/harvest/shodan_progress_{SHARD_TAG}.txt"
    shard_rel = f"ip/harvest/shodan_shard_{SHARD_TAG}.txt"

    for attempt in range(5):
        subprocess.run(
            ["git", "-C", REPO, "pull", "--rebase", "--autostash", "origin", "main"],
            capture_output=True,
        )
        subprocess.run(["git", "-C", REPO, "add", prog_rel, shard_rel], check=False)
        msg = f"cl_shodan_{SHARD_TAG}: offset={offset}/{total} cands={cand_count}"
        subprocess.run(["git", "-C", REPO, "commit", "-m", msg], capture_output=True)
        r = subprocess.run(
            ["git", "-C", REPO, "push", "origin", "main"], capture_output=True, text=True
        )
        if r.returncode == 0:
            log("GIT_PUSH_OK")
            return
        time.sleep(2)
    log("GIT_PUSH_FAILED after 5 attempts")


def norm_subnet(line):
    """Accept '1.2.3.4', '1.2.3.4/24' or '1.2.3' -> return '1.2.3'."""
    s = line.strip()
    if not s:
        return None
    if "/" in s:
        s = s.split("/")[0]
    parts = s.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3])
    if len(parts) == 3:
        return s
    return None


def load_strided_subnets():
    """Load the FULL master subnet list, dedupe, then take every Nth entry.

    Contiguous slicing gave shard 00 the bottom of the IP space and shard 14 the
    middle, so 13 of 20 shards landed in thin regions and yielded exactly 0.000%.
    Striding gives every shard the same thin/fat mix.
    """
    master = os.path.join(REPO, "work", "shodan_shards.txt")
    if not os.path.exists(master):
        log(f"ERROR: master list missing at {master}")
        return []

    seen = set()
    ordered = []
    with open(master, "r", encoding="utf-8", errors="ignore") as f:
        for l in f:
            parts = l.rstrip("\n").split("\t")
            cand = parts[1] if len(parts) >= 2 else parts[0]
            s = norm_subnet(cand)
            if s and s not in seen:
                seen.add(s)
                ordered.append(s)

    total_unique = len(ordered)
    strided = ordered[SHARD_IDX::NUM_SHARDS]
    log(f"Master subnets: {total_unique:,} unique | strided slice for shard {SHARD_TAG}: {len(strided):,}")
    return strided


def load_pe_ports():
    path = os.path.join(REPO, "ip", "pe_ports.txt")
    ports = set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for l in f:
                l = l.strip()
                if l.isdigit():
                    ports.add(int(l))
    log(f"Loaded {len(ports)} proxy ports for output filtering")
    return ports


class LightPacer:
    """Smooth token-bucket pacer guaranteeing max req/s without burst."""

    def __init__(self, max_per_sec=88.0):
        self.max_per_sec = max_per_sec
        self.win_start = time.perf_counter()
        self.win_count = 0
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = time.perf_counter()
            elapsed = now - self.win_start
            if elapsed < 1.0:
                if self.win_count >= self.max_per_sec:
                    await asyncio.sleep(1.0 - elapsed)
                    self.win_start = time.perf_counter()
                    self.win_count = 0
            else:
                self.win_start = now
                self.win_count = 0
            self.win_count += 1


async def fetch_ip(session, ip):
    try:
        async with session.get(BASE_URL + ip, timeout=aiohttp.ClientTimeout(total=4)) as r:
            if r.status == 200:
                data = await r.json()
                return ("ok", data.get("ports", []))
            elif r.status == 404:
                return ("not_found", [])
            elif r.status == 429:
                return ("rate_limit", None)
            else:
                return (f"http_{r.status}", [])
    except asyncio.TimeoutError:
        return ("timeout", [])
    except Exception:
        return ("error", [])


async def async_main():
    log("=" * 60)
    log(f"SHODAN ENGINE v98 (STRIDED SHARDS, CONC={CONC}, PACED {TARGET_RATE:.0f}/s) - SHARD {SHARD_TAG}")
    log(f"Shard target: {MAX_SHARD_IPS:,} IPs | {NUM_SHARDS} shards total")
    log("=" * 60)

    if os.path.exists("/kaggle/working"):
        if not os.path.exists(REPO):
            subprocess.run(["git", "clone", "--depth", "1", REPO_URL, REPO], check=True)
        subprocess.run(["git", "-C", REPO, "config", "user.name", f"Shodan Worker {SHARD_TAG}"], check=False)
        subprocess.run(["git", "-C", REPO, "config", "user.email", f"shodan{SHARD_TAG}@depinfarm.org"], check=False)
        git_sync()

    subnets = load_strided_subnets()
    if not subnets:
        log("ERROR: no subnets for this shard. Exiting.")
        sys.exit(1)

    pe_ports = load_pe_ports()

    raw_total_ips = len(subnets) * 256
    total_ips = min(raw_total_ips, MAX_SHARD_IPS)
    log(f"Strided subnets: {len(subnets):,} -> raw {raw_total_ips:,} IPs, capped to {total_ips:,}")

    def get_ip(offset):
        sub_i = offset // 256
        host_i = offset % 256
        return f"{subnets[sub_i]}.{host_i}"

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
    log(f"Resume offset: {resume_offset:,} / {total_ips:,} ({resume_offset / total_ips * 100:.2f}%)")

    out_shard_file = os.path.join(REPO, "ip", "harvest", f"shodan_shard_{SHARD_TAG}.txt")
    os.makedirs(os.path.dirname(out_shard_file), exist_ok=True)

    cands_found = 0
    if os.path.exists(out_shard_file):
        with open(out_shard_file, "r", encoding="utf-8", errors="ignore") as f:
            cands_found = sum(1 for _ in f)
    log(f"Existing candidate lines in shard file: {cands_found:,}")

    pacer = LightPacer(max_per_sec=TARGET_RATE)
    idx_lock = asyncio.Lock()
    write_lock = asyncio.Lock()
    current_idx = resume_offset
    processed_count = resume_offset
    total_429s = 0
    kept_lines = 0
    last_log_time = time.time()
    last_push_time = time.time()
    log_window_count = 0
    log_window_start = time.time()

    out_handle = open(out_shard_file, "a", encoding="utf-8")
    conn = aiohttp.TCPConnector(limit=CONC + 10, ttl_dns_cache=600, enable_cleanup_closed=True)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    async def worker():
        nonlocal current_idx, processed_count, cands_found, total_429s, log_window_count, kept_lines
        while current_idx < total_ips:
            if time.time() - START_TIME >= HARD_STOP:
                break

            async with idx_lock:
                if current_idx >= total_ips:
                    break
                my_offset = current_idx
                current_idx += 1

            ip = get_ip(my_offset)
            await pacer.acquire()

            status, ports = await fetch_ip(session, ip)
            if status == "ok" and ports:
                keep = [p for p in ports if p in pe_ports]
                if keep:
                    lines = [f"{ip}:{p}\n" for p in keep]
                    async with write_lock:
                        out_handle.writelines(lines)
                        out_handle.flush()
                        cands_found += len(lines)
                        kept_lines += len(lines)
            elif status == "rate_limit":
                total_429s += 1
                await asyncio.sleep(2.0)

            async with idx_lock:
                if my_offset + 1 > processed_count:
                    processed_count = my_offset + 1
                log_window_count += 1

    async def monitor():
        nonlocal last_log_time, last_push_time, log_window_count, log_window_start
        while current_idx < total_ips and (time.time() - START_TIME < HARD_STOP):
            await asyncio.sleep(5)
            now = time.time()

            if now - last_log_time >= 60:
                win_elapsed = now - log_window_start
                instant_rate = log_window_count / max(0.1, win_elapsed)
                cum_elapsed = now - START_TIME
                cum_rate = (processed_count - resume_offset) / max(0.1, cum_elapsed)
                pct = processed_count / total_ips * 100
                log(
                    f"Rate: {instant_rate:.1f} req/s (cum: {cum_rate:.1f} req/s) | "
                    f"Progress: {processed_count:,}/{total_ips:,} ({pct:.1f}%) | "
                    f"Cands: {cands_found:,} | 429s: {total_429s}"
                )
                last_log_time = now
                log_window_start = now
                log_window_count = 0

            if now - last_push_time >= PUSH_INTERVAL:
                with open(prog_file, "w") as pf:
                    pf.write(str(processed_count) + "\n")
                push_progress(processed_count, total_ips, cands_found)
                last_push_time = now

    async with aiohttp.ClientSession(connector=conn, headers=headers) as session:
        try:
            worker_tasks = [asyncio.create_task(worker()) for _ in range(CONC)]
            monitor_task = asyncio.create_task(monitor())
            await asyncio.gather(*worker_tasks)
            monitor_task.cancel()
        finally:
            out_handle.close()
            with open(prog_file, "w") as pf:
                pf.write(str(processed_count) + "\n")
            push_progress(processed_count, total_ips, cands_found)

    if processed_count >= total_ips:
        log(f"SHARD {SHARD_TAG} REACHED CAP ({total_ips:,}). DONE.")
    else:
        log(f"SESSION STOPPED AT {processed_count:,}/{total_ips:,}. Cands: {cands_found:,}. 429s: {total_429s}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
