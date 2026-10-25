import os
import sys
import time
import asyncio
import aiohttp
import subprocess

ENGINE_VER = "v98.2"
OUT_PREFIX = "v98_"

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

NUM_SHARDS = int(os.environ.get("NUM_SHARDS", "20"))
CONC = 180
TARGET_RATE = 88.0
MAX_SHARD_IPS = 6_000_000
PUSH_INTERVAL = 300
HARD_STOP = 9.5 * 3600
START_TIME = time.time()
BASE_URL = "https://internetdb.shodan.io/"


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{ENGINE_VER} SHARD {SHARD_TAG}] {msg}", flush=True)


def git_sync():
    if not os.path.exists("/kaggle/working"):
        return
    subprocess.run(["git", "-C", REPO, "pull", "--rebase", "--autostash", "origin", "main"],
                   capture_output=True)


def push_progress(offset, total, cand_count, stats):
    if not os.path.exists("/kaggle/working"):
        return
    prog_rel = f"ip/harvest/shodan_progress_{OUT_PREFIX}{SHARD_TAG}.txt"
    shard_rel = f"ip/harvest/shodan_shard_{OUT_PREFIX}{SHARD_TAG}.txt"
    stats_rel = f"ip/harvest/shodan_stats_{OUT_PREFIX}{SHARD_TAG}.txt"

    with open(os.path.join(REPO, stats_rel), "w") as sf:
        sf.write(f"engine={ENGINE_VER}\nshard={SHARD_TAG}\noffset={offset}\ntotal={total}\n")
        for k in sorted(stats):
            sf.write(f"{k}={stats[k]}\n")

    for attempt in range(5):
        subprocess.run(["git", "-C", REPO, "pull", "--rebase", "--autostash", "origin", "main"],
                       capture_output=True)
        subprocess.run(["git", "-C", REPO, "add", prog_rel, shard_rel, stats_rel], check=False)
        msg = f"{ENGINE_VER} shard_{SHARD_TAG}: offset={offset}/{total} cands={cand_count}"
        subprocess.run(["git", "-C", REPO, "commit", "-m", msg], capture_output=True)
        r = subprocess.run(["git", "-C", REPO, "push", "origin", "main"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            log("GIT_PUSH_OK")
            return
        time.sleep(2)
    log("GIT_PUSH_FAILED after 5 attempts")


def norm_subnet(line):
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
    strided = ordered[SHARD_IDX::NUM_SHARDS]
    log(f"Master subnets: {len(ordered):,} unique | strided slice: {len(strided):,}")
    log(f"STRIDE_CHECK first={strided[0] if strided else 'NONE'} last={strided[-1] if strided else 'NONE'}")
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
    log(f"Loaded {len(ports)} proxy ports")
    return ports


def read_offset(path):
    """Tolerate git conflict markers from autostash pop: take largest integer."""
    if not os.path.exists(path):
        return 0
    vals = []
    try:
        with open(path, "r", errors="ignore") as f:
            for line in f:
                t = line.strip()
                if t.isdigit():
                    vals.append(int(t))
    except Exception:
        return 0
    return max(vals) if vals else 0


def write_offset(path, val):
    with open(path, "w") as f:
        f.write(str(val) + "\n")

class LightPacer:
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
    log("=" * 66)
    log(f"{ENGINE_VER} START | CONC={CONC} | paced {TARGET_RATE:.0f}/s | cap {MAX_SHARD_IPS:,}")
    log("=" * 66)

    if os.path.exists("/kaggle/working"):
        if not os.path.exists(REPO):
            subprocess.run(["git", "clone", "--depth", "1", REPO_URL, REPO], check=True)
        subprocess.run(["git", "-C", REPO, "config", "user.name", f"W{SHARD_TAG}"], check=False)
        subprocess.run(["git", "-C", REPO, "config", "user.email", f"w{SHARD_TAG}@depinfarm.org"], check=False)
        git_sync()

    subnets = load_strided_subnets()
    if not subnets:
        log("ERROR: no subnets. Exiting.")
        sys.exit(1)

    pe_ports = load_pe_ports()

    total_ips = min(len(subnets) * 256, MAX_SHARD_IPS)
    log(f"total_ips={total_ips:,}")

    def get_ip(offset):
        return f"{subnets[offset // 256]}.{offset % 256}"

    prog_file = os.path.join(REPO, "ip", "harvest", f"shodan_progress_{OUT_PREFIX}{SHARD_TAG}.txt")
    resume_offset = read_offset(prog_file)
    write_offset(prog_file, resume_offset)
    log(f"resume_offset={resume_offset:,}/{total_ips:,}")

    out_shard_file = os.path.join(REPO, "ip", "harvest", f"shodan_shard_{OUT_PREFIX}{SHARD_TAG}.txt")
    os.makedirs(os.path.dirname(out_shard_file), exist_ok=True)
    cands_found = 0
    if os.path.exists(out_shard_file):
        with open(out_shard_file, "r", encoding="utf-8", errors="ignore") as f:
            cands_found = sum(1 for _ in f)

    stats = {"ok": 0, "not_found": 0, "rate_limit": 0, "timeout": 0,
             "other": 0, "ok_with_ports": 0, "ok_no_keep": 0, "kept_lines": 0}

    pacer = LightPacer(max_per_sec=TARGET_RATE)
    idx_lock = asyncio.Lock()
    write_lock = asyncio.Lock()
    current_idx = resume_offset
    processed_count = resume_offset
    last_log_time = time.time()
    last_push_time = time.time()
    log_window_count = 0
    log_window_start = time.time()

    try:
        with open(out_shard_file, "r", encoding="utf-8", errors="ignore") as _f:
            _good = [l for l in _f if l.strip() and not l.startswith(("<<<", "===", ">>>"))]
        with open(out_shard_file, "w", encoding="utf-8") as _f:
            _f.writelines(_good)
        log(f"shard file purged to {len(_good):,} clean lines")
    except Exception as _e:
        log(f"purge skipped: {_e}")

    out_handle = open(out_shard_file, "a", encoding="utf-8")
    conn = aiohttp.TCPConnector(limit=CONC + 10, ttl_dns_cache=600, enable_cleanup_closed=True)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    async def worker():
        nonlocal current_idx, processed_count, cands_found, log_window_count
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

            async with write_lock:
                if status in stats:
                    stats[status] += 1
                else:
                    stats["other"] += 1
                if status == "ok":
                    if ports:
                        stats["ok_with_ports"] += 1
                        keep = [p for p in ports if p in pe_ports]
                        if keep:
                            lines = [f"{ip}:{p}\n" for p in keep]
                            out_handle.writelines(lines)
                            out_handle.flush()
                            cands_found += len(lines)
                            stats["kept_lines"] += len(lines)
                        else:
                            stats["ok_no_keep"] += 1

            if status == "rate_limit":
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
                el = now - log_window_start
                ir = log_window_count / max(0.1, el)
                pct = processed_count / total_ips * 100
                log(f"Rate {ir:.1f}/s | {processed_count:,}/{total_ips:,} ({pct:.2f}%) | "
                    f"cands={cands_found:,} | ok={stats['ok']} 404={stats['not_found']} "
                    f"429={stats['rate_limit']} to={stats['timeout']} "
                    f"ok_ports={stats['ok_with_ports']} no_keep={stats['ok_no_keep']}")
                last_log_time = now
                log_window_start = now
                log_window_count = 0
            if now - last_push_time >= PUSH_INTERVAL:
                with open(prog_file, "w") as pf:
                    pf.write(str(processed_count) + "\n")
                push_progress(processed_count, total_ips, cands_found, stats)
                last_push_time = now

    async with aiohttp.ClientSession(connector=conn, headers=headers) as session:
        try:
            tasks = [asyncio.create_task(worker()) for _ in range(CONC)]
            mon = asyncio.create_task(monitor())
            await asyncio.gather(*tasks)
            mon.cancel()
        finally:
            out_handle.close()
            with open(prog_file, "w") as pf:
                pf.write(str(processed_count) + "\n")
            push_progress(processed_count, total_ips, cands_found, stats)

    log(f"STOPPED {processed_count:,}/{total_ips:,} cands={cands_found:,} stats={stats}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

