import os
import re
import sys
import time
import collections
import asyncio
import aiohttp
import subprocess
import random
import glob
import shutil

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "aiohttp-socks"], capture_output=True)
try:
    from aiohttp_socks import ProxyConnector
    HAVE_SOCKS = True
except Exception:
    HAVE_SOCKS = False

PER_PROXY_CAP = 2.0
SKIP_REVERIFY = True  # skip re-verifying active pool proxies in refill
PROXY_POOL = []          # list of (addr, proto)
PROXY_CLASS = {}
TOTAL_VERIFIED_PARSED = 0
FETCH_TIMEOUTS = {"FAST": 15, "MED": 20, "OK": 25}
BANNED = {}              # addr -> monotonic expiry time
FAILS = {}               # (addr, proto) -> consecutive failure count
FAILS_UNTIL = {}         # addr -> monotonic expiry time
NEXT_OK = {}             # addr -> monotonic time when next request is allowed
STATS_PROXY_OK = 0
STATS_PROXY_FAIL = 0
STATS_DIRECT_USED = 0
STATS_BANNED_TOTAL = 0
POOL_MIN = 999999

async def proxy_gate(addr):
    while True:
        now = time.monotonic()
        nxt = NEXT_OK.get(addr, 0.0)
        if nxt <= now:
            NEXT_OK[addr] = now + (1.0 / PER_PROXY_CAP)
            return
        await asyncio.sleep(nxt - now)
NUM_SHARDS = 20

ENGINE_VER = "v98.154"
OUT_PREFIX = "v98_"

CHUNK_MAX = 100_000
current_chunk = 1
chunk_lines = 0
chunk_handle = None

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
    shard_str = "16"

SHARD_IDX = int(shard_str)
SHARD_TAG = f"{SHARD_IDX:02d}"

CONC = 10
MAX_SHARD_IPS = 200_000_000
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


def check_disk_space():
    target = REPO if os.path.exists(REPO) else ("D:\\" if os.path.exists("D:\\") else "/")
    try:
        total, used, free = shutil.disk_usage(target)
        free_gb = free / (1024 ** 3)
        return free_gb
    except Exception:
        return 999.0


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


def read_progress(path):
    if not os.path.exists(path):
        return 0, 1
    offset = 0
    chunk = 1
    try:
        with open(path, "r", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith("chunk="):
                    try:
                        chunk = int(line.split("=")[1])
                    except Exception:
                        pass
                elif line.isdigit():
                    offset = max(offset, int(line))
    except Exception:
        pass
    return offset, max(1, chunk)


def write_progress(path, offset, chunk_num):
    atomic_write(path, f"{offset}\nchunk={chunk_num}\n")


def read_offset(path):
    offset, _ = read_progress(path)
    return offset


def write_offset(path, val):
    global current_chunk
    write_progress(path, val, current_chunk)


def push_progress(offset, total, cand_count, stats):
    if not os.path.exists("/kaggle/working"):
        return
    prog_rel = f"ip/harvest/shodan_progress_{OUT_PREFIX}{SHARD_TAG}.txt"
    chunk_rel = f"ip/harvest/shodan_shard_{OUT_PREFIX}{SHARD_TAG}_c{current_chunk:03d}.txt"
    stats_rel = f"ip/harvest/shodan_stats_{OUT_PREFIX}{SHARD_TAG}.txt"

    stats_content = f"engine={ENGINE_VER}\nshard={SHARD_TAG}\negress_ip={EGRESS_IP}\noffset={offset}\ntotal={total}\nchunk={current_chunk}\n"
    for k in sorted(stats):
        stats_content += f"{k}={stats[k]}\n"
    atomic_write(os.path.join(REPO, stats_rel), stats_content)

    msg = f"{ENGINE_VER} shard_{SHARD_TAG}: offset={offset}/{total} cands={cand_count} chunk={current_chunk}"

    global chunk_handle
    if chunk_handle:
        chunk_handle.flush()
        chunk_handle.close()
        chunk_handle = None

    subprocess.run(["git", "-C", REPO, "add", prog_rel, stats_rel, chunk_rel], check=False)
    subprocess.run(["git", "-C", REPO, "commit", "-m", msg], capture_output=True)

    for attempt in range(3):
        subprocess.run(["git", "-C", REPO, "fetch", "origin", "main"], capture_output=True)
        r = subprocess.run(["git", "-C", REPO, "push", "origin", "main"], capture_output=True, text=True)
        if r.returncode == 0:
            break
        subprocess.run(["git", "-C", REPO, "merge", "origin/main", "-X", "ours", "--no-edit"], capture_output=True)

    chunk_handle = open(os.path.join(REPO, chunk_rel), "a", encoding="utf-8")


def load_strided_subnets():
    log(f"Generating full IPv4 public subnets for shard {SHARD_TAG}...")
    t0 = time.time()
    subnets = []
    count = 0
    for a in range(1, 224):
        if a == 10 or a == 127:
            continue
        for b in range(256):
            if a == 169 and b == 254:
                continue
            if a == 172 and 16 <= b <= 31:
                continue
            if a == 192 and b == 168:
                continue
            if a == 100 and 64 <= b <= 127:
                continue
            if a == 198 and (b == 18 or b == 19):
                continue

            if a == 192 and b == 0:
                c_iter = (c for c in range(256) if c not in (0, 2))
            elif a == 192 and b == 88:
                c_iter = (c for c in range(256) if c != 99)
            elif a == 198 and b == 51:
                c_iter = (c for c in range(256) if c != 100)
            elif a == 203 and b == 0:
                c_iter = (c for c in range(256) if c != 113)
            else:
                c_iter = range(256)

            prefix = f"{a}.{b}."
            for c in c_iter:
                if count % NUM_SHARDS == SHARD_IDX:
                    subnets.append(f"{prefix}{c}")
                count += 1
    t1 = time.time()
    log(f"Generated {len(subnets):,} subnets ({len(subnets)*256:,} IPs) for shard {SHARD_TAG} in {t1-t0:.2f}s (global public subnets: {count:,})")
    log(f"STRIDE_CHECK first={subnets[0] if subnets else 'NONE'} last={subnets[-1] if subnets else 'NONE'}")
    return subnets


PROXY_PORTS = {80, 1080, 1081, 3127, 3128, 3129, 8000, 8001, 8080, 8081,
               8118, 8888, 9000, 4145, 10808}
KEEP_PORTS = PROXY_PORTS | {443, 8443}

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
        self.c429_shodan = 0
        self.c429_proxy = 0

    async def acquire(self):
        async with self.lock:
            now = time.monotonic()
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
            if retry_after:
                self.c429_shodan += 1
                self.rate = max(self.lo, self.rate * 0.9)
            else:
                self.c429_proxy += 1
        elif (200 <= status < 400) or status == 404:  # 200,204,404 = SUCCESS
            self.rate = min(self.hi, self.rate + 0.1)
        # 5xx and exceptions: neutral
        self.interval = 1.0 / self.rate

    def rolling_429(self):
        if not self.recent:
            return 0.0
        return 100.0 * (1 - sum(self.recent) / len(self.recent))


def load_candidates():
    """Newest-first verified entries, cycle-filtered and latency-filtered:
    1. Read cycle field (last column).
    2. Discard entries more than 20 cycles behind the highest seen (relaxed cutoff).
    3. Sort candidates descending by cycle (newest first).
    4. Apply FAST (<1000ms), MED (<3000ms), OK (<8000ms) latency filter.
    5. Log pool_pass_rate as kept/parsed.
    """
    def parse_verified(path):
        res = []
        if not os.path.exists(path):
            return res
        is_list = "lists_all" in os.path.basename(path)
        is_legacy = "part_" not in os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    p = line.split("\t")
                    addr = p[0].strip()
                    if ":" not in addr:
                        continue
                    if is_list:
                        res.append((addr, "http", 2000, "OK", 1))
                    else:
                        proto = p[1].strip().lower() if len(p) >= 2 else "http"
                        if proto not in ("http", "socks5"):
                            proto = "http"
                        ms = 99999
                        cls = "SLOW"
                        if len(p) >= 6:
                            try:
                                ms = int(p[5].strip())
                            except Exception:
                                ms = 99999
                        if len(p) >= 7:
                            cls = p[6].strip().upper()
                        raw_cycle = 1
                        if len(p) >= 8:
                            try:
                                raw_cycle = int(p[7].strip())
                            except Exception:
                                raw_cycle = 1
                        cycle = 1 if is_legacy else raw_cycle
                        res.append((addr, proto, ms, cls, cycle))
        except Exception:
            pass
        return res

    v_files = sorted(glob.glob(os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive_part_*.txt")))
    v_files += [os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive.txt")]
    v_files += [os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive.bak.txt")]
    v_files += [os.path.join(REPO_ROOT, "ip", "harvest", "lists_all.txt")]

    all_parsed = []
    total_parsed = 0
    max_cycle = 0

    for vf in v_files:
        if not os.path.exists(vf):
            continue
        is_legacy = "part_" not in os.path.basename(vf)
        entries = parse_verified(vf)
        total_parsed += len(entries)
        for addr, proto, ms, cls, raw_cycle in entries:
            # Legacy files (verified_alive.txt / .bak) were pre-partition, default to cycle 1
            cycle = 1 if is_legacy else raw_cycle
            if cycle > max_cycle:
                max_cycle = cycle
            all_parsed.append((addr, proto, ms, cls, cycle))

    # Cutoff: discard entries whose cycle is more than 20 cycles behind highest seen
    cutoff = max(0, max_cycle - 20)
    log(f"[cycle_filter] max_cycle={max_cycle} cutoff={cutoff}")

    # Deduplicate by addr, keeping highest cycle
    best_by_addr = {}
    for addr, proto, ms, cls, cycle in all_parsed:
        if cycle < cutoff:
            continue
        if addr not in best_by_addr or cycle > best_by_addr[addr][4]:
            best_by_addr[addr] = (addr, proto, ms, cls, cycle)

    # Sort candidates by cycle descending (newest verified come first)
    candidates = list(best_by_addr.values())
    candidates.sort(key=lambda x: x[4], reverse=True)

    # Filter FAST (<1000ms), MED (<3000ms), OK (<8000ms)
    fast_entries = []
    med_entries = []
    ok_entries = []
    slow_entries = []
    for addr, proto, ms, cls, cycle in candidates:
        if cls == "FAST" or ms < 1000:
            fast_entries.append((addr, proto, ms, "FAST", cycle))
        elif cls == "MED" or ms < 3000:
            med_entries.append((addr, proto, ms, "MED", cycle))
        elif cls == "OK" or ms < 8000:
            ok_entries.append((addr, proto, ms, "OK", cycle))
        else:
            slow_entries.append((addr, proto, ms, "SLOW", cycle))

    pool_cands = fast_entries + med_entries + ok_entries
    slow_used = 0
    if len(pool_cands) < 200 and slow_entries:
        slow_entries.sort(key=lambda x: x[2])
        needed = 200 - len(pool_cands)
        fill_slow = slow_entries[:needed]
        pool_cands += fill_slow
        slow_used = len(fill_slow)

    global PROXY_CLASS, TOTAL_VERIFIED_PARSED
    PROXY_CLASS = {x[0]: x[3] for x in pool_cands}
    TOTAL_VERIFIED_PARSED = total_parsed

    # STEP 4: Log pool_pass_rate as kept/parsed
    pass_rate_str = f"{len(pool_cands)}/{total_parsed} ({100.0 * len(pool_cands) / max(1, total_parsed):.1f}%)"
    log(f"pool_pass_rate={pass_rate_str} | FAST={len(fast_entries)} MED={len(med_entries)} OK={len(ok_entries)} SLOW={slow_used}")

    out = [(x[0], x[1]) for x in pool_cands]
    return out

async def build_pool(items):
    high_pri_pool = []  # 200, 404
    low_pri_pool = []   # 429, 403, other
    fail_counts = {"connect_error": 0, "timeout": 0, "bad_status": 0, "other": 0}
    status_counts = {"200": 0, "404": 0, "429": 0, "403": 0, "407": 0, "other": 0}
    lat_hist = {"<1s": 0, "1-3s": 0, "3-8s": 0, "8-15s": 0, "15-25s": 0, ">25s": 0}
    after_8s_count = 0
    other_types = {}
    sem = asyncio.Semaphore(600)

    def record_other(proto_tag, e):
        name = type(e).__name__
        count = other_types.get(name, 0)
        other_types[name] = count + 1
        if count < 10:
            print(f"[build_pool_other] {proto_tag} {name}: {e}", flush=True)

    def record_latency(dur):
        nonlocal after_8s_count
        if dur < 1.0:
            lat_hist["<1s"] += 1
        elif dur < 3.0:
            lat_hist["1-3s"] += 1
        elif dur < 8.0:
            lat_hist["3-8s"] += 1
        elif dur < 15.0:
            lat_hist["8-15s"] += 1
        elif dur < 25.0:
            lat_hist["15-25s"] += 1
        else:
            lat_hist[">25s"] += 1
        if dur >= 8.0:
            after_8s_count += 1

    async with aiohttp.ClientSession(headers=HEADERS) as shared:
        async def try_http(addr):
            t0 = time.monotonic()
            try:
                async with shared.get(BASE + rand_ip(), proxy=f"http://{addr}", timeout=15) as r:
                    dur = time.monotonic() - t0
                    st_k = str(r.status)
                    status_counts[st_k if st_k in status_counts else "other"] += 1
                    if r.status < 500 and r.status != 407:
                        record_latency(dur)
                        return r.status
                    return "bad_status"
            except asyncio.TimeoutError:
                return "timeout"
            except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError,
                    aiohttp.ClientProxyConnectionError, ConnectionError, OSError):
                return "connect_error"
            except Exception as e:
                record_other("http", e)
                return "other"

        async def try_socks5(addr):
            if not HAVE_SOCKS:
                record_other("socks5", RuntimeError("aiohttp_socks not available"))
                return "other"
            t0 = time.monotonic()
            try:
                conn = ProxyConnector.from_url(f"socks5://{addr}")
                async with aiohttp.ClientSession(headers=HEADERS, connector=conn) as s:
                    async with s.get(BASE + rand_ip(), timeout=15) as r:
                        dur = time.monotonic() - t0
                        st_k = str(r.status)
                        status_counts[st_k if st_k in status_counts else "other"] += 1
                        if r.status < 500 and r.status != 407:
                            record_latency(dur)
                            return r.status
                        return "bad_status"
            except asyncio.TimeoutError:
                return "timeout"
            except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError,
                    aiohttp.ClientProxyConnectionError, ConnectionError, OSError):
                return "connect_error"
            except Exception as e:
                record_other("socks5", e)
                return "other"

        async def v(item):
            addr, proto = item
            last_err = None
            async with sem:
                if proto == "socks5":
                    # STEP 1: Try socks5, if it fails retry once as http before rejecting
                    res = await try_socks5(addr)
                    if isinstance(res, int):
                        if res in (200, 404):
                            high_pri_pool.append((addr, "socks5"))
                        else:
                            low_pri_pool.append((addr, "socks5"))
                        return
                    last_err = res
                    # Retry once as http
                    res_http = await try_http(addr)
                    if isinstance(res_http, int):
                        if res_http in (200, 404):
                            high_pri_pool.append((addr, "http"))
                        else:
                            low_pri_pool.append((addr, "http"))
                        return
                    last_err = res_http
                else:
                    # proto == "http": Try http, if it fails retry once as socks5 before rejecting
                    res = await try_http(addr)
                    if isinstance(res, int):
                        if res in (200, 404):
                            high_pri_pool.append((addr, "http"))
                        else:
                            low_pri_pool.append((addr, "http"))
                        return
                    last_err = res
                    # Retry once as socks5
                    if HAVE_SOCKS:
                        res_s5 = await try_socks5(addr)
                        if isinstance(res_s5, int):
                            if res_s5 in (200, 404):
                                high_pri_pool.append((addr, "socks5"))
                            else:
                                low_pri_pool.append((addr, "socks5"))
                            return
                        last_err = res_s5

            if last_err and last_err in fail_counts:
                fail_counts[last_err] += 1

        await asyncio.gather(*[v(i) for i in items], return_exceptions=True)

    # STEP 3: Prioritise real responses: 200/404 at front, 429/403 at back
    pool = high_pri_pool + low_pri_pool
    log(f"[build_pool_fails] tested={len(items)} passed={len(pool)} connect_error={fail_counts['connect_error']} timeout={fail_counts['timeout']} bad_status={fail_counts['bad_status']} other={fail_counts['other']}")
    print(f"[build_pool_fails] tested={len(items)} passed={len(pool)} connect_error={fail_counts['connect_error']} timeout={fail_counts['timeout']} bad_status={fail_counts['bad_status']} other={fail_counts['other']}", flush=True)
    log(f"[build_pool_status] 200={status_counts['200']} 404={status_counts['404']} 429={status_counts['429']} 403={status_counts['403']} 407={status_counts['407']} other={status_counts['other']}")
    print(f"[build_pool_status] 200={status_counts['200']} 404={status_counts['404']} 429={status_counts['429']} 403={status_counts['403']} 407={status_counts['407']} other={status_counts['other']}", flush=True)
    log(f"[build_pool_latency] <1s={lat_hist['<1s']} 1-3s={lat_hist['1-3s']} 3-8s={lat_hist['3-8s']} 8-15s={lat_hist['8-15s']} 15-25s={lat_hist['15-25s']} >25s={lat_hist['>25s']} after_8s={after_8s_count}")
    print(f"[build_pool_latency] <1s={lat_hist['<1s']} 1-3s={lat_hist['1-3s']} 3-8s={lat_hist['3-8s']} 8-15s={lat_hist['8-15s']} 15-25s={lat_hist['15-25s']} >25s={lat_hist['>25s']} after_8s={after_8s_count}", flush=True)
    if other_types:
        log(f"[build_pool_other_types] {other_types}")
        print(f"[build_pool_other_types] {other_types}", flush=True)
    else:
        log(f"[build_pool_other_types] none (other=0)")
        print(f"[build_pool_other_types] none (other=0)", flush=True)
    return pool

class HttpStatus(int):
    def __new__(cls, val, ports=None):
        obj = super().__new__(cls, val)
        obj.ports = ports or []
        return obj


async def fetch_ip(session, ip, pacer):
    global STATS_PROXY_OK, STATS_PROXY_FAIL, STATS_DIRECT_USED, STATS_BANNED_TOTAL
    for attempt in range(2):
        if PROXY_POOL:
            now = time.monotonic()
            usable = [p for p in PROXY_POOL if BANNED.get(p[0], 0.0) <= now and FAILS_UNTIL.get(p[0], 0.0) <= now]
            if usable:
                addr, proto = random.choice(usable)
            else:
                addr, proto = min(PROXY_POOL, key=lambda p: max(BANNED.get(p[0], 0.0), FAILS_UNTIL.get(p[0], 0.0)))
            use_proxy = f"socks5://{addr}" if proto == "socks5" else f"http://{addr}"
            to = FETCH_TIMEOUTS.get(PROXY_CLASS.get(addr, "MED"), 25)
            await proxy_gate(addr)
        else:
            use_proxy = None
            to = 10
        try:
            async with session.get(BASE + ip, proxy=use_proxy, timeout=to) as r:
                if use_proxy:
                    FAILS[(addr, proto)] = 0
                    FAILS_UNTIL.pop(addr, None)
                    STATS_PROXY_OK += 1
                else:
                    STATS_DIRECT_USED += 1
                ra = r.headers.get("Retry-After")
                if r.status == 429:
                    if ra:
                        try:
                            ra_val = float(ra)
                        except (ValueError, TypeError):
                            ra_val = 60.0
                        if use_proxy:
                            BANNED[addr] = time.monotonic() + min(ra_val, 180.0)
                            STATS_BANNED_TOTAL += 1
                pacer.on_result(r.status, ra)
                ports = []
                if r.status == 200:
                    try:
                        data = await r.json()
                        ports = data.get("ports", [])
                    except Exception:
                        pass
                return HttpStatus(r.status, ports)
        except (asyncio.TimeoutError, aiohttp.ClientError, ConnectionError):
            if use_proxy:
                STATS_PROXY_FAIL += 1
                key = (addr, proto)
                FAILS[key] = FAILS.get(key, 0) + 1
                if FAILS[key] >= 2:
                    FAILS_UNTIL[addr] = time.monotonic() + min(20.0, 5.0 * FAILS[key])
            continue
        except Exception:
            continue
    pacer.on_result(0)
    return None


async def async_main():
    global PROXY_POOL, CONC, POOL_MIN, current_chunk, chunk_lines, chunk_handle

    log("=" * 66)
    log(f"{ENGINE_VER} START | AdaptivePacer (proxy-driven) | full IPv4")
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

    total_ips = len(subnets) * 256
    log(f"total_ips={total_ips:,}")

    def get_ip(offset):
        return f"{subnets[offset // 256]}.{offset % 256}"

    prog_file = os.path.join(REPO, "ip", "harvest", f"shodan_progress_{OUT_PREFIX}{SHARD_TAG}.txt")
    resume_offset, saved_chunk = read_progress(prog_file)
    current_chunk = saved_chunk

    chunk_pattern = os.path.join(REPO, "ip", "harvest", f"shodan_shard_{OUT_PREFIX}{SHARD_TAG}_c*.txt")
    existing_chunks = sorted(glob.glob(chunk_pattern))
    if existing_chunks:
        last_file = existing_chunks[-1]
        m = re.search(r"_c(\d+)\.txt$", last_file)
        if m:
            c_num = int(m.group(1))
            if c_num >= current_chunk:
                current_chunk = c_num

    chunk_file = os.path.join(REPO, "ip", "harvest", f"shodan_shard_{OUT_PREFIX}{SHARD_TAG}_c{current_chunk:03d}.txt")
    chunk_lines = 0
    if os.path.exists(chunk_file):
        with open(chunk_file, "r", encoding="utf-8", errors="ignore") as f:
            chunk_lines = sum(1 for _ in f)
        if chunk_lines >= CHUNK_MAX:
            current_chunk += 1
            chunk_file = os.path.join(REPO, "ip", "harvest", f"shodan_shard_{OUT_PREFIX}{SHARD_TAG}_c{current_chunk:03d}.txt")
            chunk_lines = 0

    write_progress(prog_file, resume_offset, current_chunk)
    log(f"resume_offset={resume_offset:,}/{total_ips:,} chunk={current_chunk} chunk_lines={chunk_lines}")

    os.makedirs(os.path.dirname(chunk_file), exist_ok=True)
    cands_found = chunk_lines

    stats = {"ok": 0, "not_found": 0, "rate_limit": 0, "timeout": 0,
             "other": 0, "ok_with_ports": 0, "ok_no_keep": 0, "kept_lines": 0,
             "429_shodan": 0, "429_proxy": 0, "pool_size": len(PROXY_POOL),
             "proxy_ok": 0, "proxy_fail": 0, "direct_used": 0, "req_s": "0.0"}

    # Startup — build pool BEFORE creating the main semaphore / worker tasks
    allc = []
    try:
        allc = load_candidates()
        mine = allc[SHARD_IDX::NUM_SHARDS]          # DISJOINT slice
        mine = mine[:20000]
        pass_rate_str = f"{len(allc)}/{max(1, TOTAL_VERIFIED_PARSED)} ({100.0 * len(allc) / max(1, TOTAL_VERIFIED_PARSED):.1f}%)"
        log(f"[ceiling] total_candidates={len(allc)} slice_size={len(mine)} pool_pass_rate={pass_rate_str}")
        print(f"[ceiling] total_candidates={len(allc)} slice_size={len(mine)} pool_pass_rate={pass_rate_str}", flush=True)
        async with aiohttp.ClientSession(headers=HEADERS) as tmp:
            PROXY_POOL = await build_pool(mine)
    except Exception as e:
        log(f"build_pool error: {e}")
        PROXY_POOL = []
    parsed_cnt = len(mine) if 'mine' in locals() else 0
    dropped_cnt = parsed_cnt - len(PROXY_POOL)
    log(f"[pool] shard={SHARD_IDX} parsed={parsed_cnt} dropped={dropped_cnt} pool_size={len(PROXY_POOL)}")
    print(f"[pool] shard={SHARD_IDX} parsed={parsed_cnt} dropped={dropped_cnt} pool_size={len(PROXY_POOL)}", flush=True)
    global POOL_MIN
    POOL_MIN = len(PROXY_POOL)

    CONC = min(4000, max(120, int(1.5 * len(PROXY_POOL))))
    PACER_HI = min(30000.0, max(3000.0, 15.0 * len(PROXY_POOL)))
    lo = max(200.0, PACER_HI * 0.1)
    start = min(PACER_HI, 500.0)
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

    chunk_handle = open(chunk_file, "a", encoding="utf-8")
    conn = aiohttp.TCPConnector(limit=CONC + 10, ttl_dns_cache=600, enable_cleanup_closed=True)

    now_m = time.monotonic()
    stats["usable_now"] = sum(1 for p in PROXY_POOL if BANNED.get(p[0], 0.0) <= now_m and FAILS_UNTIL.get(p[0], 0.0) <= now_m)
    stats["cooling_now"] = sum(1 for exp in FAILS_UNTIL.values() if exp > time.monotonic())
    stats["pool_size"] = len(PROXY_POOL)
    stats["pool_min"] = POOL_MIN
    push_progress(processed_count, total_ips, cands_found, stats)

    async def worker():
        nonlocal current_idx, processed_count, cands_found, log_window_count
        global current_chunk, chunk_lines, chunk_handle
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
                        first_match = next((p for p in ports if int(p) in PROXY_PORTS), None)
                        if first_match is None:
                            first_match = next((p for p in ports if int(p) in {443, 8443}), None)
                        if first_match is not None:
                            lines = [f"{ip}:{first_match}\n"]
                            if chunk_lines >= CHUNK_MAX:
                                if chunk_handle:
                                    chunk_handle.flush()
                                    chunk_handle.close()
                                current_chunk += 1
                                next_chunk_file = os.path.join(REPO, "ip", "harvest", f"shodan_shard_{OUT_PREFIX}{SHARD_TAG}_c{current_chunk:03d}.txt")
                                chunk_handle = open(next_chunk_file, "a", encoding="utf-8")
                                chunk_lines = 0
                            chunk_handle.writelines(lines)
                            chunk_handle.flush()
                            chunk_lines += len(lines)
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
        global POOL_MIN, STOPPING
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
                now_m = time.monotonic()
                usable_now = sum(1 for p in PROXY_POOL if BANNED.get(p[0], 0.0) <= now_m and FAILS_UNTIL.get(p[0], 0.0) <= now_m)
                log(f"Rate {ir:.1f}/s (pacer: {pacer.rate:.1f}/s) | {processed_count:,}/{total_ips:,} ({pct:.2f}%) | usable={usable_now} pool={len(PROXY_POOL)} | "
                    f"cands={cands_found:,} chunk={current_chunk} | ok={stats['ok']} 404={stats['not_found']} "
                    f"429={stats['rate_limit']} to={stats['timeout']} "
                    f"ok_ports={stats['ok_with_ports']} no_keep={stats['ok_no_keep']}")
                last_log_time = now
                log_window_start = now
                log_window_count = 0
            if now - last_push_time >= PUSH_INTERVAL:
                free_gb = check_disk_space()
                if free_gb < 8.0:
                    log(f"[DISK_GUARD] CRITICAL: free disk space is {free_gb:.2f} GB (< 8 GB). Stopping cleanly.")
                    STOPPING = True
                elif free_gb < 15.0:
                    log(f"[DISK_GUARD] WARNING: low disk space: {free_gb:.2f} GB free (< 15 GB).")

                write_progress(prog_file, processed_count, current_chunk)
                stats["rolling_429"] = f"{pacer.rolling_429():.2f}"
                stats["pacer_rate"] = f"{pacer.rate:.1f}"
                stats["429_shodan"] = pacer.c429_shodan
                stats["429_proxy"] = pacer.c429_proxy
                stats["banned_now"] = sum(1 for exp in BANNED.values() if exp > time.monotonic())
                now_m = time.monotonic()
                b_under30 = sum(1 for exp in BANNED.values() if 0 < (exp - now_m) < 30)
                b_30_120 = sum(1 for exp in BANNED.values() if 30 <= (exp - now_m) < 120)
                b_120_600 = sum(1 for exp in BANNED.values() if 120 <= (exp - now_m) <= 600)
                log(f"[ban_histogram] <30s={b_under30} 30-120s={b_30_120} 120-600s={b_120_600}")
                stats["banned_total"] = STATS_BANNED_TOTAL
                now_m = time.monotonic()
                stats["usable_now"] = sum(1 for p in PROXY_POOL if BANNED.get(p[0], 0.0) <= now_m and FAILS_UNTIL.get(p[0], 0.0) <= now_m)
                stats["cooling_now"] = sum(1 for exp in FAILS_UNTIL.values() if exp > time.monotonic())
                POOL_MIN = min(POOL_MIN, len(PROXY_POOL))
                stats["pool_size"] = len(PROXY_POOL)
                stats["pool_min"] = POOL_MIN
                stats["proxy_ok"] = STATS_PROXY_OK
                stats["proxy_fail"] = STATS_PROXY_FAIL
                stats["direct_used"] = STATS_DIRECT_USED
                total_resp = stats["ok"] + stats["not_found"] + stats["rate_limit"] + stats["timeout"] + stats["other"]
                stats["req_s"] = f"{total_resp / max(0.1, time.time() - START_TIME):.1f}"
                push_progress(processed_count, total_ips, cands_found, stats)
                last_push_time = now

    async def pool_refill():
        nonlocal pacer
        global PROXY_POOL, POOL_MIN, current_chunk, chunk_handle
        while not STOPPING and (time.time() - START_TIME < HARD_STOP):
            await asyncio.sleep(300)
            if STOPPING:
                break
            try:
                # Sync latest verified files from remote
                try:
                    await asyncio.to_thread(subprocess.run, ["git", "-C", REPO, "pull", "--quiet", "origin", "main"], capture_output=True)
                except Exception:
                    pass

                # Step 1: Re-read pool files fresh each cycle & sample 400
                fresh_cands = load_candidates()
                mine_fresh = fresh_cands[SHARD_IDX::NUM_SHARDS][:20000]
                sample_batch = random.sample(mine_fresh, min(400, len(mine_fresh))) if mine_fresh else []

                shard_cands = []
                cur_chunk_file = os.path.join(REPO, "ip", "harvest", f"shodan_shard_{OUT_PREFIX}{SHARD_TAG}_c{current_chunk:03d}.txt")
                if os.path.exists(cur_chunk_file):
                    try:
                        if chunk_handle:
                            chunk_handle.flush()
                        with open(cur_chunk_file, "r", encoding="utf-8", errors="ignore") as sf:
                            lines = sf.readlines()
                            for l in lines[-500:]:
                                l = l.strip()
                                if l and ":" in l and not l.startswith(("<", "=", ">")):
                                    addr = l.split()[0].split("	")[0]
                                    shard_cands.append((addr, "http"))
                    except Exception:
                        pass

                combined = sample_batch + [item for item in shard_cands if item not in sample_batch]
                if not combined:
                    continue
                if SKIP_REVERIFY:
                    combined = [p for p in combined if p not in PROXY_POOL]
                if not combined:
                    continue

                fresh = await build_pool(combined)
                curr_set = set(PROXY_POOL)
                added = 0
                for item in fresh:
                    # Step 3: Re-add recovered proxies & reset fails/cooldowns
                    FAILS[item] = 0
                    FAILS_UNTIL.pop(item[0], None)
                    BANNED.pop(item[0], None)
                    if item not in curr_set:
                        PROXY_POOL.append(item)
                        curr_set.add(item)
                        added += 1

                if PROXY_POOL:
                    PACER_HI = min(30000.0, max(3000.0, 15.0 * len(PROXY_POOL)))
                    pacer.hi = PACER_HI
                    pacer.lo = max(200.0, PACER_HI * 0.1)
                    pacer.rate = max(pacer.lo, min(pacer.hi, pacer.rate))
                log(f"[refill] tested={len(combined)} (fresh_pool={len(sample_batch)} shard={len(shard_cands)}) live={len(fresh)} added={added} pool={len(PROXY_POOL)} pacer.hi={pacer.hi:.1f}")
            except Exception as e:
                log(f"[refill] error: {e}")

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
            rev_task = asyncio.create_task(pool_refill())
            await asyncio.gather(*tasks)
            mon.cancel()
            stop_task.cancel()
            rev_task.cancel()
        finally:
            if chunk_handle:
                chunk_handle.flush()
                chunk_handle.close()
                chunk_handle = None
            write_progress(prog_file, processed_count, current_chunk)
            stats["rolling_429"] = f"{pacer.rolling_429():.2f}"
            stats["pacer_rate"] = f"{pacer.rate:.1f}"
            stats["429_shodan"] = pacer.c429_shodan
            stats["429_proxy"] = pacer.c429_proxy
            stats["banned_now"] = sum(1 for exp in BANNED.values() if exp > time.monotonic())
            now_m = time.monotonic()
            b_under30 = sum(1 for exp in BANNED.values() if 0 < (exp - now_m) < 30)
            b_30_120 = sum(1 for exp in BANNED.values() if 30 <= (exp - now_m) < 120)
            b_120_600 = sum(1 for exp in BANNED.values() if 120 <= (exp - now_m) <= 600)
            log(f"[ban_histogram] <30s={b_under30} 30-120s={b_30_120} 120-600s={b_120_600}")
            stats["banned_total"] = STATS_BANNED_TOTAL
            now_m = time.monotonic()
            stats["usable_now"] = sum(1 for p in PROXY_POOL if BANNED.get(p[0], 0.0) <= now_m and FAILS_UNTIL.get(p[0], 0.0) <= now_m)
            stats["cooling_now"] = sum(1 for exp in FAILS_UNTIL.values() if exp > time.monotonic())
            POOL_MIN = min(POOL_MIN, len(PROXY_POOL))
            stats["pool_size"] = len(PROXY_POOL)
            stats["pool_min"] = POOL_MIN
            stats["proxy_ok"] = STATS_PROXY_OK
            stats["proxy_fail"] = STATS_PROXY_FAIL
            stats["direct_used"] = STATS_DIRECT_USED
            total_resp = stats["ok"] + stats["not_found"] + stats["rate_limit"] + stats["timeout"] + stats["other"]
            stats["req_s"] = f"{total_resp / max(0.1, time.time() - START_TIME):.1f}"
            push_progress(processed_count, total_ips, cands_found, stats)

    log(f"STOPPED {processed_count:,}/{total_ips:,} cands={cands_found:,} stats={stats}")
    if STOPPING:
        log("[STOP] Clean exit after drain.")
        return


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
