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
import subprocess
import shutil
import socket
import ssl
import struct
import bisect

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "aiohttp-socks"], capture_output=True)
try:
    from aiohttp_socks import ProxyConnector
    HAVE_SOCKS = True
except Exception:
    HAVE_SOCKS = False

NUM_SHARDS = 34
DEFAULT_WORKERS = 1
BACKOFF_WORKERS = 20
PROBE_CONCURRENCY = 20

ENGINE_VER = "v98.188"
OUT_PREFIX = "v98_"

SCAN_MODE = "direct"
DIRECT_PORTS = [443, 3128, 8080, 8888, 1080, 8118, 80, 4145]

TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
SSL_CTX = ssl.create_default_context()

_TOKEN = "ghp_" + "Kw30ViztVvNX2QUbi6CcKu4NTSVV9K0J7ILR"
REPO_URL = f"https://x-access-token:{_TOKEN}@github.com/tzsailotrading04/ipscan.git"
WORK = "/kaggle/working" if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"
REPO = os.path.join(WORK, "ipscan") if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"

SHARD_IDX = 16
SHARD_TAG = f"{SHARD_IDX:02d}"
OUT_BRANCH = f"out/sh{SHARD_TAG}"

# ASN Lookup for provider logging
ASN_FILE = os.path.join(REPO, "data", "ip2asn-v4-u32.tsv")
asn_rows, asn_starts = [], []

def load_asn_table():
    global asn_rows, asn_starts
    fpath = ASN_FILE if os.path.exists(ASN_FILE) else os.path.join(os.path.dirname(__file__), "..", "..", "data", "ip2asn-v4-u32.tsv")
    if os.path.exists(fpath):
        rows = []
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) >= 5:
                    try: rows.append((int(p[0]), int(p[1]), p[2], p[4]))
                    except ValueError: pass
        rows.sort()
        asn_starts = [r[0] for r in rows]
        asn_rows = rows

def lookup_prov(ip_str):
    if not asn_starts:
        return "UNKNOWN"
    try:
        u = struct.unpack("!I", socket.inet_aton(ip_str))[0]
        i = bisect.bisect_right(asn_starts, u) - 1
        if i >= 0 and asn_rows[i][0] <= u <= asn_rows[i][1]:
            org = asn_rows[i][3].upper()
            return org.split()[0].strip(",.-")
    except Exception:
        pass
    return "UNKNOWN"

# ==============================================================================
# CANDIDATE PIPELINE (v98.180 QUEUE-FIRST STRIDED ORDER)
# 1) ip/harvest/queue/ (oldest first, delete file once all shards consumed it)
# 2) data/res_subnets.txt
# 3) data/mob_subnets.txt
# 4) data/dc_subnets.txt
# 5) random IPv4 as fallback
# ==============================================================================
def load_subnet_list(filename):
    paths = [
        os.path.join(REPO, "data", filename),
        os.path.join(os.path.dirname(__file__), "..", "..", "data", filename),
        os.path.join("/kaggle/working/ipscan/data", filename)
    ]
    for p in paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                return [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return []

# Routable Random IPv4 Generator (filters private, loopback, link-local, multicast, reserved)
def rand_ipv4():
    while True:
        b0 = random.randint(1, 223)
        if b0 in (10, 127): continue
        b1 = random.randint(0, 255)
        if b0 == 100 and 64 <= b1 <= 127: continue
        if b0 == 169 and b1 == 254: continue
        if b0 == 172 and 16 <= b1 <= 31: continue
        if b0 == 192 and b1 == 168: continue
        if b0 == 198 and (b1 == 18 or b1 == 19): continue
        b2 = random.randint(0, 255)
        b3 = random.randint(1, 254)
        return f"{b0}.{b1}.{b2}.{b3}"

# ==============================================================================
# WORKER PROCESS
# ==============================================================================
async def run_worker(shard_idx, worker_id, total_workers):
    w_tag = f"{shard_idx:02d}_w{worker_id}"
    log_pfx = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{ENGINE_VER} W{w_tag}]"
    print(f"{log_pfx} Initializing Worker {worker_id}/{total_workers} (Random IPv4 Looping)", flush=True)

    load_asn_table()

    sem = asyncio.Semaphore(PROBE_CONCURRENCY)  # Strictly bounds concurrency to 20 parallel probes
    loop = asyncio.get_running_loop()

    STAT_ERRNO99 = 0
    STAT_TIMEOUT = 0
    STAT_REFUSED = 0
    STAT_OTHER = 0

    def sync_tls_handshake(sock, target, timeout=8.0):
        try:
            sock.setblocking(True)
            sock.settimeout(timeout)
            req = f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n".encode()
            sock.sendall(req)
            resp = b""
            while b"\r\n\r\n" not in resp:
                chunk = sock.recv(512)
                if not chunk: return False
                resp += chunk
                if len(resp) > 2048: return False
            first_line = resp.split(b"\r\n")[0]
            if not (b" 200" in first_line or b"HTTP/1.1 200" in first_line or b"HTTP/1.0 200" in first_line):
                return False
            parts = resp.split(b"\r\n\r\n", 1)
            trailing = parts[1] if len(parts) > 1 else b""
            if trailing and trailing[:1] != b"\x16":
                return False
            ss = SSL_CTX.wrap_socket(sock, server_hostname=target)
            ss.settimeout(timeout)
            ss.do_handshake()
            cert = ss.getpeercert()
            if not cert:
                ss.close()
                return False
            ss.close()
            return True
        except Exception:
            try: sock.close()
            except Exception: pass
            return False

    def sync_probe_target(ip, port, target, timeout=8.0):
        s = None
        try:
            s = socket.create_connection((ip, port), timeout=timeout)
            return sync_tls_handshake(s, target, timeout=timeout)
        except Exception:
            if s:
                try: s.close()
                except Exception: pass
            return False

    async def check_port(ip, port):
        nonlocal STAT_ERRNO99, STAT_TIMEOUT, STAT_REFUSED, STAT_OTHER
        async with sem:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setblocking(False)
            try:
                await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=8.0)
            except asyncio.TimeoutError:
                STAT_TIMEOUT += 1
                try: s.close()
                except Exception: pass
                return None
            except ConnectionRefusedError:
                STAT_REFUSED += 1
                try: s.close()
                except Exception: pass
                return None
            except OSError as e:
                if getattr(e, "errno", None) == 99 or "cannot assign" in str(e).lower():
                    STAT_ERRNO99 += 1
                else:
                    STAT_OTHER += 1
                try: s.close()
                except Exception: pass
                return None
            except Exception:
                STAT_OTHER += 1
                try: s.close()
                except Exception: pass
                return None

            # Primary target probe with connected socket
            if await loop.run_in_executor(None, sync_tls_handshake, s, "speed.cloudflare.com", 8.0):
                return port, "speed.cloudflare.com"

            for t in ["www.google.com", "one.one.one.one"]:
                if await loop.run_in_executor(None, sync_probe_target, ip, port, t, 8.0):
                    return port, t
            return None

    BATCH_SIZE = 500

    prog_file = os.path.join(REPO, "ip", "harvest", f"shodan_progress_v98_{w_tag}.txt")
    stats_file = os.path.join(REPO, "ip", "harvest", f"shodan_stats_v98_{w_tag}.txt")
    part_file = os.path.join(REPO, "ip", "harvest", f"verified_alive_part_{w_tag}.txt")

    offset = 0
    if os.path.exists(prog_file):
        try:
            line = open(prog_file).readline().strip()
            if line.isdigit(): offset = int(line)
        except Exception: pass

    cands_found = 0
    if os.path.exists(part_file):
        cands_found = sum(1 for _ in open(part_file, errors="ignore"))

    recent_logs = collections.deque(maxlen=10)

    def shard_log(msg, *args, **kwargs):
        ts_str = time.strftime('%Y-%m-%d %H:%M:%S')
        formatted = f"[{ts_str}] [SHARD {SHARD_TAG} W{worker_id}] {msg}"
        recent_logs.append(formatted)
        print(formatted, flush=True)

    def write_stage_file(stage, cur_offset):
        if worker_id != 0:
            return
        stage_file = os.path.join(REPO, "ip", "harvest", f"stage_{SHARD_TAG}.txt")
        now_ts = int(time.time())
        last_5 = list(recent_logs)[-5:]
        lines = [
            f"stage={stage}",
            f"ts={now_ts}",
            f"offset={cur_offset}",
            "--- LAST 5 LOG LINES ---"
        ]
        for l in last_5:
            lines.append(l)
        content = "\n".join(lines) + "\n"
        try:
            with open(stage_file + ".tmp", "w", encoding="utf-8") as sf:
                sf.write(content)
            os.replace(stage_file + ".tmp", stage_file)
        except Exception:
            pass

    shard_log(f"Random IPv4 Looping: Resume offset={offset:,} cands={cands_found:,}")
    write_stage_file("init", offset)
    write_stage_file("init:open_part_fp", offset)
    part_fp = open(part_file, "a", encoding="utf-8")

    start_t = time.time()
    last_stats_t = time.time()

    write_stage_file("init:load_subnets", offset)
    res_subnets_all = load_subnet_list("res_subnets.txt")
    mob_subnets_all = load_subnet_list("mob_subnets.txt")
    dc_subnets_all = load_subnet_list("dc_subnets.txt")

    write_stage_file("init:stride_subnets", offset)
    # Stride across shards and workers
    res_subnets = [s for idx, s in enumerate(res_subnets_all) if idx % NUM_SHARDS == shard_idx][worker_id::total_workers]
    mob_subnets = [s for idx, s in enumerate(mob_subnets_all) if idx % NUM_SHARDS == shard_idx][worker_id::total_workers]
    dc_subnets = [s for idx, s in enumerate(dc_subnets_all) if idx % NUM_SHARDS == shard_idx][worker_id::total_workers]

    write_stage_file("init:setup_dirs", offset)
    queue_dir = os.path.join(REPO, "ip", "harvest", "queue")
    acks_dir = os.path.join(REPO, "ip", "harvest", "acks")
    os.makedirs(queue_dir, exist_ok=True)
    os.makedirs(acks_dir, exist_ok=True)

    cur_res_idx = 0
    cur_mob_idx = 0
    cur_dc_idx = 0

    write_stage_file("init:pipeline_loaded", offset)
    print(f"{log_pfx} Candidate Pipeline Loaded: res={len(res_subnets):,} mob={len(mob_subnets):,} dc={len(dc_subnets):,} subnets for Shard {SHARD_TAG} W{worker_id}", flush=True)

    def get_candidate_batch():
        nonlocal cur_res_idx, cur_mob_idx, cur_dc_idx
        # Tier 1: Check queue files (oldest first)
        if os.path.exists(queue_dir):
            q_files = sorted([f for f in os.listdir(queue_dir) if f.startswith("q_") and f.endswith(".txt")])
            for qf_name in q_files:
                qf_path = os.path.join(queue_dir, qf_name)
                ack_marker = os.path.join(acks_dir, f"{qf_name}.ack_{shard_idx}")
                if not os.path.exists(ack_marker):
                    # Read lines and stride
                    lines = []
                    try:
                        with open(qf_path, "r", encoding="utf-8", errors="ignore") as qf:
                            lines = [l.strip() for l in qf if l.strip()]
                    except Exception:
                        pass
                    shard_lines = [l for idx, l in enumerate(lines) if idx % NUM_SHARDS == shard_idx]
                    # Mark acknowledged by this shard
                    try:
                        with open(ack_marker, "w", encoding="utf-8") as af:
                            af.write("1\n")
                    except Exception:
                        pass
                    # Check if all shards consumed it
                    all_acks = [f for f in os.listdir(acks_dir) if f.startswith(qf_name + ".ack_")]
                    if len(all_acks) >= NUM_SHARDS:
                        try:
                            os.remove(qf_path)
                            for a in all_acks:
                                os.remove(os.path.join(acks_dir, a))
                        except Exception:
                            pass
                    if shard_lines:
                        batch = []
                        for item in shard_lines:
                            parts = item.split()[0].split(":")
                            if len(parts) == 2 and parts[1].isdigit():
                                batch.append((parts[0], int(parts[1]), "QUEUE"))
                        if batch:
                            return batch, "QUEUE"

        # Tier 2: Consumer Residential Subnets
        if cur_res_idx < len(res_subnets):
            sub = res_subnets[cur_res_idx]
            cur_res_idx += 1
            batch = [(f"{sub}.{h}", p, "RES") for h in range(1, 255) for p in DIRECT_PORTS]
            return batch, "RES"

        # Tier 3: Mobile Carrier Subnets
        if cur_mob_idx < len(mob_subnets):
            sub = mob_subnets[cur_mob_idx]
            cur_mob_idx += 1
            batch = [(f"{sub}.{h}", p, "MOB") for h in range(1, 255) for p in DIRECT_PORTS]
            return batch, "MOB"

        # Tier 4: Datacenter Subnets
        if cur_dc_idx < len(dc_subnets):
            sub = dc_subnets[cur_dc_idx]
            cur_dc_idx += 1
            batch = [(f"{sub}.{h}", p, "DC") for h in range(1, 255) for p in DIRECT_PORTS]
            return batch, "DC"

        # Tier 5: Random IPv4 Fallback
        batch_ips = [rand_ipv4() for _ in range(BATCH_SIZE)]
        batch = [(ip, p, "RANDOM") for ip in batch_ips for p in DIRECT_PORTS]
        return batch, "RANDOM"


    # ==============================================================================
    # STAGE 0: QUEUE CONSUMING STAGE (RUNS BEFORE IP SCANNING)
    # ==============================================================================
    async def consume_queue_stage():
        nonlocal cands_found, offset
        write_stage_file("queue:check_dir", offset)
        if not os.path.exists(queue_dir):
            write_stage_file("queue:no_dir_skip", offset)
            return 0
        write_stage_file("queue:list_files", offset)
        q_files = sorted([f for f in os.listdir(queue_dir) if f.startswith("q_") and f.endswith(".txt")])
        if not q_files:
            write_stage_file("queue:no_files_skip", offset)
            return 0
        write_stage_file(f"queue:found_{len(q_files)}_files", offset)
        shard_log(f"[QUEUE STAGE] Found {len(q_files)} queue files to consume before IP scanning", flush=True)

        write_stage_file("queue_consuming", offset)
        queue_start_t = time.time()
        QUEUE_WALLCLOCK_LIMIT = 120.0  # Wall-clock limit of 120 seconds per cycle

        for qf_name in q_files:
            qf_path = os.path.join(queue_dir, qf_name)
            ack_file = os.path.join(acks_dir, f"{qf_name}.ack_{shard_idx}")
            qcur_dir = os.path.join(REPO, "cache", "qcursor")
            os.makedirs(qcur_dir, exist_ok=True)
            qcur_file = os.path.join(qcur_dir, f"{qf_name}.cur_{shard_idx}")
            _qc = "0"
            try:
                if os.path.exists(qcur_file):
                    with open(qcur_file, "r", encoding="utf-8") as _qcf:
                        _qc = _qcf.read().strip() or "0"
            except Exception:
                _qc = "0"
            if _qc == "DONE":
                continue

            lines = []
            try:
                with open(qf_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [l.strip() for l in f if l.strip()]
            except Exception:
                continue

            # Each shard takes its stride slice across NUM_SHARDS (34)
            shard_slice = [l for idx, l in enumerate(lines) if idx % NUM_SHARDS == shard_idx]
            worker_slice = shard_slice[worker_id::total_workers]
            try:
                _start = int(_qc)
            except Exception:
                _start = 0
            if _start >= len(worker_slice):
                try:
                    with open(qcur_file, "w", encoding="utf-8") as _qcw:
                        _qcw.write("DONE\n")
                except Exception:
                    pass
                continue
            shard_log(f"[QUEUE STAGE] Consuming {qf_name}: total={len(lines)} shard_slice={len(shard_slice)} worker_slice={len(worker_slice)} resume={_start}", flush=True)
            timed_out = False
            write_stage_file(f"queue_file_{qf_name}", offset)
            for i in range(_start, len(worker_slice), 500):
                write_stage_file(f"queue_slice_{qf_name}_{i}", offset)
                # Wall-clock limit check
                if (time.time() - queue_start_t) >= QUEUE_WALLCLOCK_LIMIT:
                    shard_log(f"[QUEUE TIMEOUT] Wall-clock limit ({QUEUE_WALLCLOCK_LIMIT}s) expired ({time.time() - queue_start_t:.1f}s). Abandoning remainder of queue slice, writing ack, and falling through to scanning.", flush=True)
                    timed_out = True
                    break

                chunk = worker_slice[i:i + 500]
                tasks = []
                for item in chunk:
                    parts = item.split()[0].split(":")
                    if len(parts) == 2 and parts[1].isdigit():
                        ip = parts[0]
                        port = int(parts[1])
                        tasks.append((ip, port, check_port(ip, port)))

                if tasks:
                    results = await asyncio.gather(*[t[2] for t in tasks], return_exceptions=True)
                    for (ip, port, _), res in zip(tasks, results):
                        if isinstance(res, tuple) and res[0] is not None:
                            passed_port, target = res
                            prov = lookup_prov(ip)
                            part_fp.write(f"{ip}:{passed_port}\t{target}\tQUEUE\t0\t{prov}\n")
                            part_fp.flush()
                            cands_found += 1
                            shard_log(f"[FOUND QUEUE] {ip}:{passed_port} ({prov}) via {target} | cands={cands_found}", flush=True)
                    offset += len(tasks)
                try:
                    with open(qcur_file, "w", encoding="utf-8") as _qcw2:
                        _qcw2.write(f"{min(i + 500, len(worker_slice))}\n")
                except Exception:
                    pass

                # Check limit after batch completion
                if (time.time() - queue_start_t) >= QUEUE_WALLCLOCK_LIMIT:
                    shard_log(f"[QUEUE TIMEOUT] Wall-clock limit ({QUEUE_WALLCLOCK_LIMIT}s) expired ({time.time() - queue_start_t:.1f}s). Abandoning remainder of queue slice, writing ack, and falling through to scanning.", flush=True)
                    timed_out = True
                    break

            # Mark acknowledged only when this shard's whole slice is finished
            try:
                if (not timed_out) and ((i + 500) >= len(worker_slice)):
                    with open(qcur_file, "w", encoding="utf-8") as _qcw3:
                        _qcw3.write("DONE\n")
                    with open(ack_file, "w", encoding="utf-8") as af:
                        af.write("1\n")
            except Exception:
                pass

            # Check if all 34 shards have passed it, then delete
            acks = [f for f in os.listdir(acks_dir) if f.startswith(f"{qf_name}.ack_") and not f.endswith(".tmp")]
            if len(acks) >= NUM_SHARDS:
                try:
                    os.remove(qf_path)
                    for a in acks:
                        os.remove(os.path.join(acks_dir, a))
                    print(f"{log_pfx} [QUEUE STAGE] {qf_name} consumed by all {NUM_SHARDS} shards and removed.", flush=True)
                except Exception:
                    pass

            # If timed out, break out of queue files loop and fall through to scanning
            if timed_out:
                break
        _rem = 0
        for _f in q_files:
            _p = os.path.join(REPO, "cache", "qcursor", f"{_f}.cur_{shard_idx}")
            try:
                if not (os.path.exists(_p) and open(_p, "r", encoding="utf-8").read().strip() == "DONE"):
                    _rem += 1
            except Exception:
                _rem += 1
        return _rem

    write_stage_file("init:enter_consume_queue_stage", offset)
    _empty = 0
    for _pass in range(600):
        try:
            subprocess.run(["git", "fetch", "--depth", "1", "origin", "main"], cwd=REPO, capture_output=True, timeout=90)
            subprocess.run(["git", "checkout", "FETCH_HEAD", "--", "ip/harvest/queue"], cwd=REPO, capture_output=True, timeout=90)
        except Exception:
            pass
        _left = await consume_queue_stage()
        if _left:
            _empty = 0
            await asyncio.sleep(1)
            continue
        _empty += 1
        if _empty >= 20:
            break
        await asyncio.sleep(30)
    write_stage_file("queue_done", offset)

    # MAIN WORKER EXECUTION LOOP
    write_stage_file("scanning_start", offset)
    while True:
        task_items, current_tier = get_candidate_batch()
        write_stage_file(f"{current_tier.lower()}_loop", offset)
        tasks = []
        for ip, p, tier in task_items:
            tasks.append((ip, p, tier, check_port(ip, p)))

        results = await asyncio.gather(*[t[3] for t in tasks], return_exceptions=True)

        for (ip, port, tier, _), res in zip(tasks, results):
            if isinstance(res, tuple) and res[0] is not None:
                passed_port, target = res
                prov = lookup_prov(ip)
                part_fp.write(f"{ip}:{passed_port}\t{target}\t{tier}\t0\t{prov}\n")
                part_fp.flush()
                cands_found += 1
                shard_log(f"[FOUND {tier}] {ip}:{passed_port} ({prov}) via {target} | cands={cands_found}", flush=True)

        offset += len(task_items)
        write_stage_file(f"{current_tier.lower()}_loop", offset)
        now = time.time()
        if now - last_stats_t >= 15:
            last_stats_t = now
            dt = max(0.1, now - start_t)
            req_s = (offset) / dt
            with open(prog_file + ".tmp", "w") as f:
                f.write(f"{offset}\nchunk=1\n")
            os.replace(prog_file + ".tmp", prog_file)
            with open(stats_file + ".tmp", "w") as f:
                f.write(f"offset={offset}\ntotal=4294967296\ncands={cands_found}\nerrno99={STAT_ERRNO99}\ntimeout={STAT_TIMEOUT}\nrefused={STAT_REFUSED}\nreq_s={req_s:.1f}\nstage={current_tier.lower()}_loop\n")
            os.replace(stats_file + ".tmp", stats_file)


# ==============================================================================
# FLEET MASTER SUPERVISOR
# ==============================================================================
def git_sync_and_push(msg):
    try:
        # Fetch only its own branch
        subprocess.run(["git", "-C", REPO, "fetch", "origin", f"{OUT_BRANCH}:{OUT_BRANCH}"], capture_output=True, check=False)

        # Stage its part, stats, progress, and stage files
        patterns = [
            f"ip/harvest/verified_alive_part_{SHARD_TAG}*.txt",
            f"ip/harvest/shodan_stats_v98_{SHARD_TAG}*.txt",
            f"ip/harvest/shodan_progress_v98_{SHARD_TAG}*.txt",
            f"ip/harvest/stage_{SHARD_TAG}.txt",
        ]
        for pat in patterns:
            subprocess.run(["git", "-C", REPO, "add", pat], capture_output=True, check=False)

        st = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True)
        if not st.stdout.strip():
            return True

        c_res = subprocess.run(["git", "-C", REPO, "commit", "-m", msg], capture_output=True, text=True)
        if c_res.returncode != 0 and ("nothing to commit" in c_res.stdout or "nothing to commit" in c_res.stderr):
            return True

        # Push directly to out/sh<SHARD_TAG> - no rebase, no retry loop needed
        p_res = subprocess.run(["git", "-C", REPO, "push", "origin", f"HEAD:refs/heads/{OUT_BRANCH}"], capture_output=True, text=True)
        if p_res.returncode == 0:
            return True
        # If remote exists and diverged, force push to own isolated branch
        p_res = subprocess.run(["git", "-C", REPO, "push", "-f", "origin", f"HEAD:refs/heads/{OUT_BRANCH}"], capture_output=True, text=True)
        return p_res.returncode == 0
    except Exception as e:
        print(f"[GIT EXCEPTION] {e}", file=sys.stderr, flush=True)
        return False

def run_master():
    def log(msg):
        t = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{t}] {msg}", flush=True)

    log("=" * 70)
    log(f"Fleet Master Supervisor Starting for Shard {SHARD_TAG} (Random IPv4 Looping)")
    log(f"Mode: RANDOM IPv4 LOOPING (Endless Continuous)")
    log(f"Ports: {DIRECT_PORTS} | Workers: {DEFAULT_WORKERS} processes | Batch: 500")
    log("=" * 70)

    if os.path.exists("/kaggle/working"):
        if not os.path.exists(REPO):
            subprocess.run(["git", "clone", "--depth", "1", REPO_URL, REPO], check=True)
        subprocess.run(["git", "-C", REPO, "config", "user.name", f"W{SHARD_TAG}"], check=False)
        subprocess.run(["git", "-C", REPO, "config", "user.email", f"w{SHARD_TAG}@depinfarm.org"], check=False)

    try:
        import resource
        resource.setrlimit(resource.RLIMIT_NOFILE, (65535, 65535))
    except Exception: pass
    try:
        subprocess.run(["sysctl", "-w", "net.ipv4.ip_local_port_range=10000 65535"], capture_output=True, check=False)
        subprocess.run(["sysctl", "-w", "net.ipv4.tcp_tw_reuse=1"], capture_output=True, check=False)
    except Exception: pass

    active_workers = DEFAULT_WORKERS
    procs = []

    def start_worker(wid):
        p = subprocess.Popen([sys.executable, __file__, str(SHARD_IDX), str(wid), str(active_workers)])
        return p

    for w in range(active_workers):
        procs.append(start_worker(w))
        time.sleep(1)

    log(f"Spawned {len(procs)} parallel worker processes.")

    shard_part = os.path.join(REPO, "ip", "harvest", f"verified_alive_part_{SHARD_TAG}.txt")
    last_shard_sig = (os.path.getmtime(shard_part), os.path.getsize(shard_part)) if os.path.exists(shard_part) else None
    last_push_t = time.time()

    while True:
        time.sleep(10)
        total_offset = 0
        total_total = 4294967296
        total_cands = 0
        total_errno99 = 0
        total_req_s = 0.0

        for w in range(6):
            w_tag = f"{SHARD_TAG}_w{w}"
            sf = os.path.join(REPO, "ip", "harvest", f"shodan_stats_v98_{w_tag}.txt")
            if os.path.exists(sf):
                try:
                    for line in open(sf):
                        if line.startswith("offset="): total_offset += int(line.split("=")[1])
                        elif line.startswith("cands="): total_cands += int(line.split("=")[1])
                        elif line.startswith("errno99="): total_errno99 += int(line.split("=")[1])
                        elif line.startswith("req_s="): total_req_s += float(line.split("=")[1])
                except Exception: pass

        # Aggregate stats
        shard_stat = os.path.join(REPO, "ip", "harvest", f"shodan_stats_v98_{SHARD_TAG}.txt")
        shard_prog = os.path.join(REPO, "ip", "harvest", f"shodan_progress_v98_{SHARD_IDX:02d}.txt")
        with open(shard_stat + ".tmp", "w") as f:
            f.write(f"engine={ENGINE_VER}\nshard={SHARD_TAG}\noffset={total_offset}\ntotal={total_total}\ncands={total_cands}\nerrno99={total_errno99}\nreq_s={total_req_s:.1f}\nworkers={active_workers}\nstage=random_ipv4_loop\n")
        os.replace(shard_stat + ".tmp", shard_stat)

        with open(shard_prog + ".tmp", "w") as f:
            f.write(f"{total_offset}\nchunk=1\n")
        os.replace(shard_prog + ".tmp", shard_prog)

        # Merge worker parts into master shard file
        shard_part = os.path.join(REPO, "ip", "harvest", f"verified_alive_part_{SHARD_TAG}.txt")
        seen_proxies = set()
        if os.path.exists(shard_part):
            for l in open(shard_part, errors="ignore"):
                if l.strip(): seen_proxies.add(l.strip())
        new_items = []
        for w in range(6):
            wp = os.path.join(REPO, "ip", "harvest", f"verified_alive_part_{SHARD_TAG}_w{w}.txt")
            if os.path.exists(wp):
                for l in open(wp, errors="ignore"):
                    ls = l.strip()
                    if ls and ls not in seen_proxies:
                        seen_proxies.add(ls)
                        new_items.append(ls)
        if new_items:
            with open(shard_part, "a", encoding="utf-8") as f:
                for it in new_items: f.write(it + "\n")
            log(f"Aggregated +{len(new_items)} fresh proxies from workers into part_{SHARD_TAG}.txt (Total: {len(seen_proxies)})")

        # Push to git when part file changed OR 300 seconds have passed since last push
        now = time.time()
        cur_sig = (os.path.getmtime(shard_part), os.path.getsize(shard_part)) if os.path.exists(shard_part) else None
        part_changed = (cur_sig is not None and cur_sig != last_shard_sig)
        time_elapsed = (now - last_push_t >= 300)

        if part_changed or time_elapsed:
            last_push_t = now
            commit_msg = f"{ENGINE_VER} shard_{SHARD_TAG}: offset={total_offset} cands={total_cands} stage_heartbeat"
            if git_sync_and_push(commit_msg):
                last_shard_sig = cur_sig

        # Supervise workers
        dead = []
        for idx, p in enumerate(procs):
            if p.poll() is not None:
                dead.append(idx)
        for idx in dead:
            log(f"Worker {idx} died. Restarting...")
            procs[idx] = start_worker(idx)

if __name__ == "__main__":
    if len(sys.argv) >= 4:
        s_idx = int(sys.argv[1])
        w_id = int(sys.argv[2])
        tot = int(sys.argv[3])
        asyncio.run(run_worker(s_idx, w_id, tot))
    else:
        run_master()
