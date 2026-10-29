"""
tools/generate_shards_dc_loop.py
Generates the Datacenter-Only Looping configuration for all 20 Kaggle shards:
- Drop residential entirely (datacenter only)
- Broadened hosting list (262,960 /24 subnets, 67.3M IPs worldwide, no hyperscalers)
- Endless loop: when a pass completes, wraps offset to 0 and continues indefinitely
- 2 workers per container, batch size 500, 5 direct ports, strict probe
- ENGINE_VER = "v98.170"
"""
import os
import py_compile

ROOT = r"D:\DEpinFarm"
NUM_SHARDS = 20

CODE_TEMPLATE = '''import os
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

NUM_SHARDS = 20
DEFAULT_WORKERS = 2
BACKOFF_WORKERS = 1

ENGINE_VER = "v98.170"
OUT_PREFIX = "v98_"

SCAN_MODE = "direct"
DIRECT_PORTS = [443, 3128, 8080, 80, 8888]

TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
CLIENT_HELLOS = {}
for _t in TARGETS:
    _ctx = ssl.create_default_context()
    _bio_in, _bio_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    _sslobj = _ctx.wrap_bio(_bio_in, _bio_out, server_hostname=_t)
    try:
        _sslobj.do_handshake()
    except ssl.SSLWantReadError:
        pass
    CLIENT_HELLOS[_t] = _bio_out.read()

_TOKEN = "ghp_" + "Kw30ViztVvNX2QUbi6CcKu4NTSVV9K0J7ILR"
REPO_URL = f"https://x-access-token:{_TOKEN}@github.com/tzsailotrading04/ipscan.git"
WORK = "/kaggle/working" if os.path.exists("/kaggle/working") else r"D:\\DEpinFarm"
REPO = os.path.join(WORK, "ipscan") if os.path.exists("/kaggle/working") else r"D:\\DEpinFarm"

SHARD_IDX = __SHARD_IDX__
SHARD_TAG = f"{SHARD_IDX:02d}"

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
                p = line.rstrip("\\n").split("\\t")
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

async def inline_probe_connected(s, target, timeout=5.0):
    try:
        loop = asyncio.get_running_loop()
        req = f"CONNECT {target}:443 HTTP/1.1\\r\\nHost: {target}:443\\r\\n\\r\\n".encode()
        await loop.sock_sendall(s, req)
        resp = b""
        t_end = time.monotonic() + timeout
        while b"\\r\\n\\r\\n" not in resp:
            if time.monotonic() > t_end:
                return False
            c = await asyncio.wait_for(loop.sock_recv(s, 512), timeout=timeout)
            if not c:
                return False
            resp += c
        first_line = resp.split(b"\\r\\n")[0]
        if not (resp.startswith(b"HTTP/") and (b" 200" in first_line or b" 2" in first_line)):
            return False
        parts = resp.split(b"\\r\\n\\r\\n", 1)
        trailing = parts[1] if len(parts) > 1 else b""
        if trailing:
            return trailing[:1] == b"\\x16"
        await loop.sock_sendall(s, CLIENT_HELLOS[target])
        b1 = await asyncio.wait_for(loop.sock_recv(s, 1), timeout=timeout)
        return b1 == b"\\x16"
    except Exception:
        return False
    finally:
        try: s.close()
        except Exception: pass

async def probe_single_target(ip, port, target, timeout=5.0):
    loop = asyncio.get_running_loop()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setblocking(False)
    try:
        await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=timeout)
        return await inline_probe_connected(s, target, timeout=timeout)
    except Exception:
        try: s.close()
        except Exception: pass
        return False

# ==============================================================================
# WORKER PROCESS FUNCTION (DATACENTER ONLY, LOOPING)
# ==============================================================================
async def run_worker(shard_idx, worker_id, total_workers):
    tag = f"{shard_idx:02d}"
    w_tag = f"{tag}_w{worker_id}"
    log_pfx = f"[{ENGINE_VER} SHARD {tag} W{worker_id}]"
    print(f"{log_pfx} Worker {worker_id}/{total_workers} starting (Datacenter Looping)...", flush=True)

    load_asn_table()

    # Semaphore for socket concurrency
    DIRECT_SEM = asyncio.Semaphore(2500)
    STAT_ERRNO99 = 0
    STAT_TIMEOUT = 0
    STAT_REFUSED = 0
    STAT_OTHER = 0

    async def check_port(ip, port):
        nonlocal STAT_ERRNO99, STAT_TIMEOUT, STAT_REFUSED, STAT_OTHER
        async with DIRECT_SEM:
            loop = asyncio.get_running_loop()
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setblocking(False)
            try:
                await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=1.8)
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

            if await inline_probe_connected(s, "speed.cloudflare.com", timeout=5.0):
                return port, "speed.cloudflare.com"

            for t in ["www.google.com", "one.one.one.one"]:
                if await probe_single_target(ip, port, t, timeout=5.0):
                    return port, t
            return None

    BATCH_SIZE = 500

    # Load Broadened Hosting Subnets
    subnets_file = os.path.join(REPO, "data", "hosting_subnets.txt")
    if not os.path.exists(subnets_file):
        subnets_file = os.path.join(os.path.dirname(__file__), "..", "..", "data", "hosting_subnets.txt")

    all_host_subnets = []
    with open(subnets_file, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx % NUM_SHARDS == shard_idx:
                all_host_subnets.append(line.strip())

    worker_host_subnets = all_host_subnets[worker_id::total_workers]
    total_host_ips = len(worker_host_subnets) * 256
    print(f"{log_pfx} Datacenter Subnets: {len(worker_host_subnets):,} subnets ({total_host_ips:,} IPs per pass)", flush=True)

    prog_file = os.path.join(REPO, "ip", "harvest", f"shodan_progress_v98_{w_tag}.txt")
    stats_file = os.path.join(REPO, "ip", "harvest", f"shodan_stats_v98_{w_tag}.txt")
    part_file = os.path.join(REPO, "ip", "harvest", f"verified_alive_part_{w_tag}.txt")

    offset = 0
    if os.path.exists(prog_file):
        try:
            line = open(prog_file).readline().strip()
            if line.isdigit(): offset = int(line) % max(1, total_host_ips)
        except Exception: pass

    cands_found = 0
    if os.path.exists(part_file):
        cands_found = sum(1 for _ in open(part_file, errors="ignore"))

    print(f"{log_pfx} Resume offset={offset:,}/{total_host_ips:,} cands={cands_found:,}", flush=True)
    part_fp = open(part_file, "a", encoding="utf-8")

    def get_host_ip(off):
        sub_i = (off >> 8) % len(worker_host_subnets)
        h = off & 0xFF
        return f"{worker_host_subnets[sub_i]}.{h}"

    start_t = time.time()
    last_stats_t = time.time()
    epoch = 1

    # ENDLESS DATACENTER LOOP
    while True:
        while offset < total_host_ips:
            batch_ips = [get_host_ip(offset + i) for i in range(min(BATCH_SIZE, total_host_ips - offset))]
            tasks = []
            for ip in batch_ips:
                for p in DIRECT_PORTS:
                    tasks.append((ip, p, check_port(ip, p)))

            results = await asyncio.gather(*[t[2] for t in tasks], return_exceptions=True)

            for (ip, port, _), res in zip(tasks, results):
                if isinstance(res, tuple) and res[0] is not None:
                    passed_port, target = res
                    prov = lookup_prov(ip)
                    part_fp.write(f"{ip}:{passed_port}\\t{target}\\tDATACENTER\\t0\\t{prov}\\n")
                    part_fp.flush()
                    cands_found += 1
                    print(f"{log_pfx} [FOUND DC] {ip}:{passed_port} ({prov}) via {target} | cands={cands_found}", flush=True)

            offset += len(batch_ips)
            now = time.time()
            if now - last_stats_t >= 15:
                last_stats_t = now
                dt = max(0.1, now - start_t)
                req_s = (offset * len(DIRECT_PORTS)) / dt
                with open(prog_file + ".tmp", "w") as f:
                    f.write(f"{offset}\\nchunk=1\\n")
                os.replace(prog_file + ".tmp", prog_file)
                with open(stats_file + ".tmp", "w") as f:
                    f.write(f"offset={offset}\\ntotal={total_host_ips}\\ncands={cands_found}\\nerrno99={STAT_ERRNO99}\\ntimeout={STAT_TIMEOUT}\\nrefused={STAT_REFUSED}\\nreq_s={req_s:.1f}\\nstage=datacenter_loop\\nepoch={epoch}\\n")
                os.replace(stats_file + ".tmp", stats_file)

        # Finished pass: loop back to offset 0 (never enter residential)
        epoch += 1
        print(f"{log_pfx} Finished pass #{epoch-1} over {total_host_ips:,} IPs. Looping back to offset 0 (DC Only)...", flush=True)
        offset = 0

# ==============================================================================
# FLEET MASTER SUPERVISOR
# ==============================================================================
def run_master():
    def log(msg):
        t = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{t}] {msg}", flush=True)

    log("=" * 70)
    log(f"Fleet Master Supervisor Starting for Shard {SHARD_TAG} (Datacenter Looping)")
    log(f"Mode: DATACENTER ONLY (LOOPING) | No Residential")
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

    last_push_t = time.time()

    while True:
        time.sleep(10)
        total_offset = 0
        total_total = 0
        total_cands = 0
        total_errno99 = 0
        total_req_s = 0.0

        for w in range(6):
            w_tag = f"{SHARD_TAG}_w{w}"
            for pfx in ["shodan_stats_v98_", "shodan_stats_res_"]:
                stats_p = os.path.join(REPO, "ip", "harvest", f"{pfx}{w_tag}.txt")
                if os.path.exists(stats_p):
                    try:
                        for line in open(stats_p):
                            if line.startswith("offset="): total_offset += int(line.split("=")[1])
                            elif line.startswith("total="): total_total += int(line.split("=")[1])
                            elif line.startswith("cands="): total_cands += int(line.split("=")[1])
                            elif line.startswith("errno99="): total_errno99 += int(line.split("=")[1])
                            elif line.startswith("req_s="): total_req_s += float(line.split("=")[1])
                    except Exception: pass

        # Restart dead workers if needed
        for i, p in enumerate(procs):
            if p.poll() is not None:
                log(f"Worker {i} exited (rc={p.returncode}), restarting...")
                procs[i] = start_worker(i)

        # Merge verified files and push to origin/main
        now = time.time()
        if now - last_push_t >= 120:
            last_push_t = now

            for pfx in ["verified_alive_part_", "verified_alive_part_res_"]:
                shard_part_file = os.path.join(REPO, "ip", "harvest", f"{pfx}{SHARD_TAG}.txt")
                seen_lines = set()
                if os.path.exists(shard_part_file):
                    for l in open(shard_part_file, errors="ignore"):
                        if l.strip(): seen_lines.add(l.strip())

                for w in range(6):
                    w_tag = f"{SHARD_TAG}_w{w}"
                    w_part = os.path.join(REPO, "ip", "harvest", f"{pfx}{w_tag}.txt")
                    if os.path.exists(w_part):
                        for l in open(w_part, errors="ignore"):
                            l = l.strip()
                            if l and l not in seen_lines:
                                seen_lines.add(l)

                with open(shard_part_file, "w", encoding="utf-8") as out_fp:
                    for l in sorted(seen_lines):
                        out_fp.write(l + "\\n")

            # Write master progress and stats
            master_prog = os.path.join(REPO, "ip", "harvest", f"shodan_progress_v98_{SHARD_TAG}.txt")
            with open(master_prog, "w") as f:
                f.write(f"{total_offset}\\nchunk=1\\n")

            master_stats = os.path.join(REPO, "ip", "harvest", f"shodan_stats_v98_{SHARD_TAG}.txt")
            with open(master_stats, "w") as f:
                f.write(f"engine={ENGINE_VER}\\nshard={SHARD_TAG}\\noffset={total_offset}\\ntotal={total_total}\\ncands={total_cands}\\nerrno99={total_errno99}\\nreq_s={total_req_s:.1f}\\nworkers={len(procs)}\\n")

            log(f"FLEET STATUS: offset={total_offset:,} | cands={total_cands:,} | rate={total_req_s:.1f} req/s | workers={len(procs)}")

            # Git commit and push with jitter
            if os.path.exists("/kaggle/working"):
                msg = f"{ENGINE_VER} shard_{SHARD_TAG}: offset={total_offset} cands={total_cands} chunk=1"
                subprocess.run(["git", "-C", REPO, "add", f"ip/harvest/*{SHARD_TAG}*"], check=False)
                subprocess.run(["git", "-C", REPO, "commit", "-m", msg], check=False)
                for _ in range(3):
                    time.sleep(random.uniform(2.0, 5.0))
                    r_pull = subprocess.run(["git", "-C", REPO, "pull", "--rebase", "origin", "main"], capture_output=True, text=True)
                    if r_pull.returncode == 0:
                        r_push = subprocess.run(["git", "-C", REPO, "push", "origin", "main"], capture_output=True, text=True)
                        if r_push.returncode == 0:
                            log(f"Successfully pushed shard {SHARD_TAG} update to origin/main.")
                            break
                        else:
                            subprocess.run(["git", "-C", REPO, "rebase", "--abort"], capture_output=True)

if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[2].isdigit() and sys.argv[3].isdigit():
        s_idx = int(sys.argv[1])
        w_id = int(sys.argv[2])
        w_tot = int(sys.argv[3])
        asyncio.run(run_worker(s_idx, w_id, w_tot))
    else:
        run_master()
'''

def main():
    print(f"Generating run.py for {NUM_SHARDS} shards (Datacenter Looping, 2W/B500)...")
    for shard_idx in range(NUM_SHARDS):
        tag = f"{shard_idx:02d}"
        kdir = os.path.join(ROOT, "kaggle", f"cl_shodan_{tag}")
        os.makedirs(kdir, exist_ok=True)
        run_path = os.path.join(kdir, "run.py")
        code = CODE_TEMPLATE.replace("__SHARD_IDX__", str(shard_idx))
        with open(run_path, "w", encoding="utf-8") as f:
            f.write(code)
        py_compile.compile(run_path, doraise=True)
        print(f"Generated and compiled: {run_path}")

    print("All 20 shards generated and syntax validated successfully.")

if __name__ == "__main__":
    main()
