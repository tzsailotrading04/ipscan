import os
import sys
import time
import asyncio
import aiohttp
import subprocess

ENGINE_VER = "v98.9"
OUT_PREFIX = "v98_"

_TOKEN = "ghp_" + "Kw30ViztVvNX2QUbi6CcKu4NTSVV9K0J7ILR"
REPO_URL = f"https://x-access-token:{_TOKEN}@github.com/tzsailotrading04/ipscan.git"
WORK = "/kaggle/working" if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"
REPO = os.path.join(WORK, "ipscan") if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"

STOP_FILE = "work/STOP_SHODAN"
STOPPING = False

shard_str = os.environ.get("SHARD_INDEX", os.environ.get("SLICE_IDX", ""))
if not shard_str and len(sys.argv) > 1:
    for arg in sys.argv[1:]:
        if arg.isdigit():
            shard_str = arg
            break
if not shard_str:
    shard_str = "09"

SHARD_IDX = int(shard_str)
SHARD_TAG = f"{SHARD_IDX:02d}"

NUM_SHARDS = int(os.environ.get("NUM_SHARDS", "20"))
CONC = 180
MAX_SHARD_IPS = 6_000_000
PUSH_INTERVAL = 300
HARD_STOP = 9.5 * 3600
START_TIME = time.time()
BASE_URL = "https://internetdb.shodan.io/"


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{ENGINE_VER} SHARD {SHARD_TAG}] {msg}", flush=True)


async def run_git(cmd):
    if not os.path.exists("/kaggle/working"):
        return
    full_cmd = [cmd[0], "-C", REPO] + cmd[1:]
    await asyncio.to_thread(subprocess.run, full_cmd, capture_output=True)


async def run_git_rc(cmd):
    if not os.path.exists("/kaggle/working"):
        return 1
    full_cmd = [cmd[0], "-C", REPO] + cmd[1:]
    proc = await asyncio.to_thread(subprocess.run, full_cmd, capture_output=True)
    return proc.returncode


def git_sync():
    if not os.path.exists("/kaggle/working"):
        return
    subprocess.run(["git", "-C", REPO, "pull", "--rebase", "--autostash", "origin", "main"],
                   capture_output=True)


async def stop_monitor():
    global STOPPING
    while not STOPPING:
        await asyncio.sleep(60)
        try:
            await run_git(["git", "fetch", "origin", "main", "--quiet"])
            rc = await run_git_rc(["git", "cat-file", "-e", f"origin/main:{STOP_FILE}"])
            if rc == 0:
                STOPPING = True
                print("[STOP] flag seen on origin/main, draining...", flush=True)
                break
        except Exception:
            pass
        stop_path = os.path.join(REPO, STOP_FILE) if not os.path.isabs(STOP_FILE) else STOP_FILE
        if os.path.exists(stop_path):
            STOPPING = True
            print("[STOP] flag seen, draining...", flush=True)
            break


def atomic_write(filepath, content):
    d = os.path.dirname(filepath)
    os.makedirs(d, exist_ok=True)
    tmp = filepath + f".tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, filepath)


def push_progress(offset, total, cand_count, stats):
    if not os.path.exists("/kaggle/working"):
        return
    prog_rel = f"ip/harvest/shodan_progress_{OUT_PREFIX}{SHARD_TAG}.txt"
    shard_rel = f"ip/harvest/shodan_shard_{OUT_PREFIX}{SHARD_TAG}.txt"
    stats_rel = f"ip/harvest/shodan_stats_{OUT_PREFIX}{SHARD_TAG}.txt"

    stats_content = f"engine={ENGINE_VER}\nshard={SHARD_TAG}\noffset={offset}\ntotal={total}\n"
    for k in sorted(stats):
        stats_content += f"{k}={stats[k]}\n"
    atomic_write(os.path.join(REPO, stats_rel), stats_content)

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
    atomic_write(path, str(val) + "\n")


class AdaptivePacer:
    def __init__(self, start=50.0, lo=6.0, hi=90.0):
        self.rate = float(start)
        self.lo = float(lo)
        self.hi = float(hi)
        self.interval = 1.0 / self.rate
        self.next_slot = time.monotonic()
        self.lock = asyncio.Lock()
        self.paused_until = 0.0

    async def acquire(self):
        async with self.lock:
            now = time.monotonic()
            if now < self.paused_until:
                wait = self.paused_until - now
            else:
                if self.next_slot < now:
                    self.next_slot = now
                wait = self.next_slot - now
                self.next_slot += self.interval
        if wait > 0:
            await asyncio.sleep(wait)

    def on_ok(self):
        self.rate = min(self.hi, self.rate + 0.5)
        self.interval = 1.0 / self.rate

    def on_429(self, retry_after=None):
        self.rate = max(self.lo, self.rate * 0.5)
        self.interval = 1.0 / self.rate
        if retry_after:
            try:
                self.paused_until = time.monotonic() + min(float(retry_after), 300.0)
            except (ValueError, TypeError):
                pass


async def fetch_ip(session, ip):
    try:
        async with session.get(BASE_URL + ip, timeout=aiohttp.ClientTimeout(total=4)) as r:
            if r.status == 200:
                data = await r.json()
                return ("ok", data.get("ports", []), None)
            elif r.status == 404:
                return ("not_found", [], None)
            elif r.status == 429:
                ra = r.headers.get("Retry-After")
                return ("rate_limit", None, ra)
            else:
                return (f"http_{r.status}", [], None)
    except asyncio.TimeoutError:
        return ("timeout", [], None)
    except Exception:
        return ("error", [], None)


async def async_main():
    log("=" * 66)
    log(f"{ENGINE_VER} START | CONC={CONC} | AdaptivePacer (50->6..90) | cap {MAX_SHARD_IPS:,}")
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

    pacer = AdaptivePacer(start=50.0, lo=6.0, hi=90.0)
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
            if STOPPING:
                break
            if time.time() - START_TIME >= HARD_STOP:
                break
            async with idx_lock:
                if current_idx >= total_ips:
                    break
                my_offset = current_idx
                current_idx += 1

            ip = get_ip(my_offset)
            await pacer.acquire()
            status, ports, retry_after = await fetch_ip(session, ip)

            if status == "ok":
                pacer.on_ok()
            elif status == "rate_limit":
                pacer.on_429(retry_after)

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

            async with idx_lock:
                if my_offset + 1 > processed_count:
                    processed_count = my_offset + 1
                log_window_count += 1

    async def monitor():
        nonlocal last_log_time, last_push_time, log_window_count, log_window_start
        while current_idx < total_ips and not STOPPING and (time.time() - START_TIME < HARD_STOP):
            await asyncio.sleep(5)
            now = time.time()
            if now - last_log_time >= 60:
                el = now - log_window_start
                ir = log_window_count / max(0.1, el)
                pct = processed_count / total_ips * 100
                log(f"Rate {ir:.1f}/s (pacer: {pacer.rate:.1f}/s) | {processed_count:,}/{total_ips:,} ({pct:.2f}%) | "
                    f"cands={cands_found:,} | ok={stats['ok']} 404={stats['not_found']} "
                    f"429={stats['rate_limit']} to={stats['timeout']} "
                    f"ok_ports={stats['ok_with_ports']} no_keep={stats['ok_no_keep']}")
                last_log_time = now
                log_window_start = now
                log_window_count = 0
            if now - last_push_time >= PUSH_INTERVAL:
                write_offset(prog_file, processed_count)
                push_progress(processed_count, total_ips, cands_found, stats)
                last_push_time = now

    async with aiohttp.ClientSession(connector=conn, headers=headers) as session:
        try:
            tasks = [asyncio.create_task(worker()) for _ in range(CONC)]
            mon = asyncio.create_task(monitor())
            stop_task = asyncio.create_task(stop_monitor())
            await asyncio.gather(*tasks)
            mon.cancel()
            stop_task.cancel()
        finally:
            out_handle.close()
            write_offset(prog_file, processed_count)
            push_progress(processed_count, total_ips, cands_found, stats)

    log(f"STOPPED {processed_count:,}/{total_ips:,} cands={cands_found:,} stats={stats}")
    if STOPPING:
        log("[STOP] Clean exit after drain.")
        sys.exit(0)


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
