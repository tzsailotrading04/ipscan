import os
import sys
import time
import collections
import asyncio
import aiohttp
import subprocess
import random

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "aiohttp-socks"], capture_output=True)
try:
    from aiohttp_socks import ProxyConnector
    HAVE_SOCKS = True
except Exception:
    HAVE_SOCKS = False

PER_PROXY_CAP = 8.0
PROXY_POOL = []          # list of (addr, proto)
NUM_SHARDS = 20

ENGINE_VER = "v98.114"
OUT_PREFIX = "v98_"
OUT_HANDLE = None

_TOKEN = "ghp_" + "Kw30ViztVvNX2QUbi6CcKu4NTSVV9K0J7ILR"
REPO_URL = f"https://x-access-token:{_TOKEN}@github.com/tzsailotrading04/ipscan.git"
WORK = "/kaggle/working" if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"
REPO = os.path.join(WORK, "ipscan") if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"
REPO_ROOT = REPO

STOP_FILE = "work/STOP_SHODAN"
STOPPING = False
EGRESS_IP = "unknown"

shard_str = os.environ.get("SHARD_INDEX", os.environ.get("SLICE_IDX", ""))
if not shard_str and len(sys.argv) > 1:
    for arg in sys.argv[1:]:
        if arg.isdigit():
            shard_str = arg
            break
if not shard_str:
    shard_str = "02"

SHARD_IDX = int(shard_str)
SHARD_TAG = f"{SHARD_IDX:02d}"

CONC = 10
MAX_SHARD_IPS = 6_000_000
PUSH_INTERVAL = 300
HARD_STOP = 9.5 * 3600
START_TIME = time.time()
BASE = "https://internetdb.shodan.io/"
BASE_URL = BASE

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept": "application/json"}


def rand_ip():
    return f"{random.randint(1,223)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


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
    subprocess.run(["git", "-C", REPO, "pull", "origin", "main"],
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
    out_shard_file = os.path.join(REPO, shard_rel)

    stats_content = f"engine={ENGINE_VER}\nshard={SHARD_TAG}\negress_ip={EGRESS_IP}\noffset={offset}\ntotal={total}\n"
    for k in sorted(stats):
        stats_content += f"{k}={stats[k]}\n"
    atomic_write(os.path.join(REPO, stats_rel), stats_content)

    msg = f"{ENGINE_VER} shard_{SHARD_TAG}: offset={offset}/{total} cands={cand_count}"

    global OUT_HANDLE
    if OUT_HANDLE: OUT_HANDLE.flush(); OUT_HANDLE.close(); OUT_HANDLE = None

    subprocess.run(["git","-C",REPO,"add",prog_rel,shard_rel,stats_rel], check=False)
    subprocess.run(["git","-C",REPO,"commit","-m",msg], capture_output=True)

    for attempt in range(3):
        subprocess.run(["git","-C",REPO,"fetch","origin","main"], capture_output=True)
        r = subprocess.run(["git","-C",REPO,"push","origin","main"], capture_output=True, text=True)
        if r.returncode == 0: break
        subprocess.run(["git","-C",REPO,"merge","origin/main","-X","ours","--no-edit"], capture_output=True)

    OUT_HANDLE = open(out_shard_file, "a", encoding="utf-8")


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
    """Tolerate git conflict markers: take largest integer."""
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
    def __init__(self, start=8.0, lo=6.0, hi=10.0):
        self.rate = float(start)
        self.lo = float(lo)
        self.hi = float(hi)
        self.interval = 1.0 / self.rate
        self.next_slot = time.monotonic()
        self.lock = asyncio.Lock()
        self.paused_until = 0.0
        self.recent = collections.deque(maxlen=200)

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

    def on_result(self, status, retry_after=None):
        self.recent.append(1 if status != 429 else 0)
        now = time.monotonic()
        if status == 429:
            self.rate = max(self.lo, self.rate * 0.9)
            if retry_after:
                try:
                    ra_val = float(retry_after)
                    if ra_val >= 5:
                        self.paused_until = now + min(ra_val, 3600.0)
                except (ValueError, TypeError):
                    pass
        elif (200 <= status < 400) or status == 404:  # 200,204,404 = SUCCESS
            self.rate = min(self.hi, self.rate + 0.1)
        # 5xx and exceptions: neutral
        self.interval = 1.0 / self.rate

    def rolling_429(self):
        if not self.recent:
            return 0.0
        return 100.0 * (1 - sum(self.recent) / len(self.recent))


def load_candidates():
    """ALL entries, every tier, http + socks5, deterministically shuffled so
    every shard sees the SAME order and slices are DISJOINT."""
    path = os.path.join(REPO_ROOT, "ip/harvest/verified_alive.txt")
    out = []
    try:
        for line in open(path):
            p = line.rstrip("\n").split("\t")
            if len(p) < 8: continue
            proto = p[1].strip().lower()
            if proto not in ("http", "socks5"): continue
            out.append((p[0], proto))
    except Exception:
        pass
    random.Random(12345).shuffle(out)
    return out


async def build_pool(items):
    pool = []
    sem = asyncio.Semaphore(80)
    async with aiohttp.ClientSession(headers=HEADERS) as shared:
        async def v(item):
            addr, proto = item
            async with sem:
                for _ in range(2):
                    try:
                        if proto == "socks5":
                            if not HAVE_SOCKS: return
                            conn = ProxyConnector.from_url(f"socks5://{addr}")
                            async with aiohttp.ClientSession(headers=HEADERS, connector=conn) as s:
                                async with s.get(BASE + rand_ip(), timeout=6) as r:
                                    if r.status in (200, 404):
                                        pool.append((addr, "socks5")); return
                        else:
                            async with shared.get(BASE + rand_ip(), proxy=f"http://{addr}", timeout=6) as r:
                                if r.status in (200, 404):
                                    pool.append((addr, "http")); return
                    except Exception:
                        pass
        await asyncio.gather(*[v(i) for i in items], return_exceptions=True)
    return pool


class HttpStatus(int):
    def __new__(cls, val, ports=None):
        obj = super().__new__(cls, val)
        obj.ports = ports or []
        return obj


async def fetch_ip(session, ip, pacer):
    for attempt in range(3):
        if PROXY_POOL:
            addr, proto = random.choice(PROXY_POOL)
            use_proxy = f"socks5://{addr}" if proto == "socks5" else f"http://{addr}"
        else:
            use_proxy = None
        try:
            async with session.get(BASE + ip, proxy=use_proxy, timeout=12) as r:
                pacer.on_result(r.status, r.headers.get("Retry-After"))
                ports = []
                if r.status == 200:
                    try:
                        data = await r.json()
                        ports = data.get("ports", [])
                    except Exception:
                        pass
                return HttpStatus(r.status, ports)
        except Exception:
            if PROXY_POOL:
                try: PROXY_POOL.remove((addr, proto))
                except ValueError: pass
            continue
    pacer.on_result(0)
    return None


async def async_main():
    global PROXY_POOL, CONC

    log("=" * 66)
    log(f"{ENGINE_VER} START | AdaptivePacer (proxy-driven) | cap {MAX_SHARD_IPS:,}")
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

    # Startup â€” build pool BEFORE creating the main semaphore / worker tasks
    allc = []
    try:
        allc = load_candidates()
        mine = allc[SHARD_IDX::NUM_SHARDS]          # DISJOINT slice, ~1250 items
        async with aiohttp.ClientSession(headers=HEADERS) as tmp:
            PROXY_POOL = await build_pool(mine)
    except Exception as e:
        log(f"build_pool error: {e}")
        PROXY_POOL = []
    print(f"[pool] shard={SHARD_IDX} cands={len(mine) if 'mine' in locals() else 0} working={len(PROXY_POOL)}", flush=True)

    CONC = min(2500, max(200, 12 * len(PROXY_POOL)))
    PACER_HI = min(2000.0, max(200.0, 10.0 * len(PROXY_POOL)))
    lo = max(50.0, PACER_HI * 0.3)
    start = min(PACER_HI, max(lo, 100.0))
    pacer = AdaptivePacer(start=start, lo=lo, hi=PACER_HI)

    log(f"Configured CONC={CONC} pacer.rate={pacer.rate:.1f} pacer.hi={pacer.hi:.1f} pool_size={len(PROXY_POOL)}")

    idx_lock = asyncio.Lock()
    write_lock = asyncio.Lock()
    current_idx = resume_offset
    processed_count = resume_offset
    last_log_time = time.time()
    last_pacer_log_time = time.time()
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

    global OUT_HANDLE
    OUT_HANDLE = open(out_shard_file, "a", encoding="utf-8")
    conn = aiohttp.TCPConnector(limit=CONC + 10, ttl_dns_cache=600, enable_cleanup_closed=True)

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
            status = await fetch_ip(session, ip, pacer)
            ports = getattr(status, "ports", [])

            async with write_lock:
                if status == 200:
                    stats["ok"] += 1
                    if ports:
                        stats["ok_with_ports"] += 1
                        keep = [p for p in ports if p in pe_ports]
                        if keep:
                            lines = [f"{ip}:{p}\n" for p in keep]
                            if OUT_HANDLE:
                                OUT_HANDLE.writelines(lines)
                                OUT_HANDLE.flush()
                            cands_found += len(lines)
                            stats["kept_lines"] += len(lines)
                        else:
                            stats["ok_no_keep"] += 1
                elif status == 404:
                    stats["not_found"] += 1
                elif status == 429:
                    stats["rate_limit"] += 1
                elif status is None or status == 0:
                    stats["timeout"] += 1
                else:
                    stats["other"] += 1

            async with idx_lock:
                if my_offset + 1 > processed_count:
                    processed_count = my_offset + 1
                log_window_count += 1

    async def monitor():
        nonlocal last_log_time, last_pacer_log_time, last_push_time, log_window_count, log_window_start
        while current_idx < total_ips and not STOPPING and (time.time() - START_TIME < HARD_STOP):
            await asyncio.sleep(5)
            now = time.time()
            if now - last_pacer_log_time >= 30:
                log(f"[pacer] rate={pacer.rate:.1f} hi={pacer.hi:.1f} pool={len(PROXY_POOL)} rolling429={pacer.rolling_429():.1f}%")
                last_pacer_log_time = now
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
                stats["rolling_429"] = f"{pacer.rolling_429():.2f}"
                stats["pacer_rate"] = f"{pacer.rate:.1f}"
                push_progress(processed_count, total_ips, cands_found, stats)
                last_push_time = now

    async def reverify_loop():
        nonlocal pacer
        global PROXY_POOL
        reverify_offset = SHARD_IDX * 1250 + 1250
        while not STOPPING and (time.time() - START_TIME < HARD_STOP):
            await asyncio.sleep(900)
            if STOPPING:
                break
            try:
                if not allc:
                    continue
                next_batch = [allc[(reverify_offset + i) % len(allc)] for i in range(min(800, len(allc)))]
                reverify_offset = (reverify_offset + 800) % len(allc)
                fresh = await build_pool(next_batch)
                curr_set = set(PROXY_POOL)
                for f in fresh:
                    if f not in curr_set:
                        PROXY_POOL.append(f)
                        curr_set.add(f)
                if len(PROXY_POOL) > 400:
                    PROXY_POOL = PROXY_POOL[:400]
                if PROXY_POOL:
                    PACER_HI = min(2000.0, max(200.0, 10.0 * len(PROXY_POOL)))
                    pacer.hi = PACER_HI
                    pacer.lo = max(50.0, PACER_HI * 0.3)
                    pacer.rate = max(pacer.lo, min(pacer.hi, pacer.rate))
                log(f"[reverify] fresh={len(fresh)} total_pool={len(PROXY_POOL)} pacer.hi={pacer.hi:.1f}")
            except Exception as e:
                log(f"[reverify] error: {e}")

    async with aiohttp.ClientSession(connector=conn, headers=HEADERS) as session:
        global EGRESS_IP
        try:
            async with session.get("https://api.ipify.org", headers=HEADERS) as r:
                EGRESS_IP = (await r.text()).strip()
        except Exception:
            EGRESS_IP = "unknown"
        log(f"EGRESS_IP={EGRESS_IP}")

        try:
            tasks = [asyncio.create_task(worker()) for _ in range(CONC)]
            mon = asyncio.create_task(monitor())
            stop_task = asyncio.create_task(stop_monitor())
            rev_task = asyncio.create_task(reverify_loop())
            await asyncio.gather(*tasks)
            mon.cancel()
            stop_task.cancel()
            rev_task.cancel()
        finally:
            if OUT_HANDLE:
                OUT_HANDLE.flush()
                OUT_HANDLE.close()
                OUT_HANDLE = None
            write_offset(prog_file, processed_count)
            stats["rolling_429"] = f"{pacer.rolling_429():.2f}"
            stats["pacer_rate"] = f"{pacer.rate:.1f}"
            push_progress(processed_count, total_ips, cands_found, stats)

    log(f"STOPPED {processed_count:,}/{total_ips:,} cands={cands_found:,} stats={stats}")
    if STOPPING:
        log("[STOP] Clean exit after drain.")
        sys.exit(0)


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

