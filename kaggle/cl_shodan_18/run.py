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

ENGINE_VER = "v98.173"
OUT_PREFIX = "v98_"

SCAN_MODE = "direct"
DIRECT_PORTS = [443, 3128, 8080, 80, 8888]

TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
SSL_CTX = ssl.create_default_context()

_TOKEN = "ghp_" + "Kw30ViztVvNX2QUbi6CcKu4NTSVV9K0J7ILR"
REPO_URL = f"https://x-access-token:{_TOKEN}@github.com/tzsailotrading04/ipscan.git"
WORK = "/kaggle/working" if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"
REPO = os.path.join(WORK, "ipscan") if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"

SHARD_IDX = 18
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

    sem = asyncio.Semaphore(150)
    loop = asyncio.get_running_loop()

    STAT_ERRNO99 = 0
    STAT_TIMEOUT = 0
    STAT_REFUSED = 0
    STAT_OTHER = 0

    def sync_tls_handshake(sock, target, timeout=4.0):
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
            ss = SSL_CTX.wrap_socket(sock, server_hostname=target)
            ss.settimeout(timeout)
            ss.do_handshake()
            _ = ss.getpeercert()
            ss.close()
            return True
        except Exception:
            try: sock.close()
            except Exception: pass
            return False

    def sync_probe_target(ip, port, target, timeout=4.0):
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

            # Primary target probe with connected socket
            if await loop.run_in_executor(None, sync_tls_handshake, s, "speed.cloudflare.com", 4.0):
                return port, "speed.cloudflare.com"

            for t in ["www.google.com", "one.one.one.one"]:
                if await loop.run_in_executor(None, sync_probe_target, ip, port, t, 4.0):
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

    print(f"{log_pfx} Random IPv4 Looping: Resume offset={offset:,} cands={cands_found:,}", flush=True)
    part_fp = open(part_file, "a", encoding="utf-8")

    start_t = time.time()
    last_stats_t = time.time()

    # ENDLESS RANDOM IPv4 LOOP (Never Idle)
    while True:
        batch_ips = [rand_ipv4() for _ in range(BATCH_SIZE)]
        tasks = []
        for ip in batch_ips:
            for p in DIRECT_PORTS:
                tasks.append((ip, p, check_port(ip, p)))

        results = await asyncio.gather(*[t[2] for t in tasks], return_exceptions=True)

        for (ip, port, _), res in zip(tasks, results):
            if isinstance(res, tuple) and res[0] is not None:
                passed_port, target = res
                prov = lookup_prov(ip)
                part_fp.write(f"{ip}:{passed_port}\t{target}\tRANDOM\t0\t{prov}\n")
                part_fp.flush()
                cands_found += 1
                print(f"{log_pfx} [FOUND RANDOM] {ip}:{passed_port} ({prov}) via {target} | cands={cands_found}", flush=True)

        offset += len(batch_ips)
        now = time.time()
        if now - last_stats_t >= 15:
            last_stats_t = now
            dt = max(0.1, now - start_t)
            req_s = (offset * len(DIRECT_PORTS)) / dt
            with open(prog_file + ".tmp", "w") as f:
                f.write(f"{offset}\nchunk=1\n")
            os.replace(prog_file + ".tmp", prog_file)
            with open(stats_file + ".tmp", "w") as f:
                f.write(f"offset={offset}\ntotal=4294967296\ncands={cands_found}\nerrno99={STAT_ERRNO99}\ntimeout={STAT_TIMEOUT}\nrefused={STAT_REFUSED}\nreq_s={req_s:.1f}\nstage=random_ipv4_loop\n")
            os.replace(stats_file + ".tmp", stats_file)

# ==============================================================================
# FLEET MASTER SUPERVISOR
# ==============================================================================
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
        shard_prog = os.path.join(REPO, "ip", "harvest", f"shodan_progress_v98_{SHARD_TAG}.txt")
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

        # Push to git every 30s
        now = time.time()
        if now - last_push_t >= 30:
            last_push_t = now
            try:
                subprocess.run(["git", "-C", REPO, "add", "ip/harvest/"], check=False)
                res = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True)
                if res.stdout.strip():
                    subprocess.run(["git", "-C", REPO, "commit", "-m", f"{ENGINE_VER} shard_{SHARD_TAG}: offset={total_offset} cands={total_cands} random_loop"], check=False)
                    for _ in range(5):
                        subprocess.run(["git", "-C", REPO, "pull", "--rebase", "origin", "main"], check=False)
                        p_res = subprocess.run(["git", "-C", REPO, "push", "origin", "main"], check=False)
                        if p_res.returncode == 0:
                            break
                        time.sleep(2)
            except Exception: pass

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
