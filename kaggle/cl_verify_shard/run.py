import os
import re
import sys
import time
import socket
import struct
import ssl
import subprocess
import random
import glob
from concurrent.futures import ThreadPoolExecutor
from bisect import bisect_right

_TOKEN = "ghp_" + "Kw30ViztVvNX2QUbi6CcKu4NTSVV9K0J7ILR"
REPO_URL = f"https://x-access-token:{_TOKEN}@github.com/tzsailotrading04/ipscan.git"
WORK = "/kaggle/working" if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"
REPO = os.path.join(WORK, "ipscan") if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"

# Sharding config
VERIFY_SHARD_ID = int(os.environ.get("VERIFY_SHARD_ID", sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].isdigit() else "0"))
VERIFY_SHARD_TOTAL = int(os.environ.get("VERIFY_SHARD_TOTAL", sys.argv[2] if len(sys.argv) > 2 and sys.argv[2].isdigit() else "4"))

OUT_REL = f"ip/harvest/verified_alive_part_{VERIFY_SHARD_ID}.txt"
PUB_REL = f"ip/pub_part_{VERIFY_SHARD_ID}.txt"

CANDIDATES = [
    "master_pool.txt",
    "ip/harvest/verified_alive.txt",
    "ip/harvest/feeds_raw.txt",
    "ip/harvest/leakix.txt",
    "ip/harvest/shodan_expanded.txt",
    "ip/harvest/dataset_ports.txt"
]
FALLBACK_PORTS = ["8080", "3128", "1080", "8000", "8888"]
ASN_REL = "data/ip2asn-v4-u32.tsv"
WORKERS = 4000
TIMEOUT = 3
HOST = "api.ipify.org"
HARD_STOP = 9 * 3600
START = time.time()

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

def log(m):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [VERIFY SHARD {VERIFY_SHARD_ID}/{VERIFY_SHARD_TOTAL}] {m}", flush=True)

def atomic_write(filepath, lines):
    tmp_path = filepath + ".tmp"
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
        for line in lines:
            f.write(line + "\n")
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp_path, filepath)

def load_verified_set(repo_dir, default_pass=0):
    vp = os.path.join(repo_dir, OUT_REL)
    d = {}
    if os.path.exists(vp):
        with open(vp, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_str = line.strip()
                if not line_str or "\t" not in line_str:
                    continue
                parts = line_str.split("\t")
                k = parts[0]
                if len(parts) >= 8:
                    try:
                        seen_pass = int(parts[7])
                        prefix = "\t".join(parts[:7])
                    except Exception:
                        seen_pass = default_pass
                        prefix = "\t".join(parts[:7])
                else:
                    seen_pass = default_pass
                    prefix = "\t".join(parts[:7])
                d[k] = (prefix, seen_pass)
    return d

def git_sync(repo_dir):
    subprocess.run(["git", "-C", repo_dir, "fetch", "origin", "main"], check=False)
    r = subprocess.run(["git", "-C", repo_dir, "reset", "--hard", "origin", "main"], check=False)
    return r.returncode == 0

log("=" * 60)
log(f"DISTRIBUTED VERIFIER START (SHARD {VERIFY_SHARD_ID}/{VERIFY_SHARD_TOTAL})")
log("=" * 60)

if os.path.exists("/kaggle/working"):
    if os.path.exists(REPO):
        git_sync(REPO)
    else:
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, REPO], check=True)

subprocess.run(["git", "-C", REPO, "config", "user.name", f"Verifier {VERIFY_SHARD_ID}"], check=False)
subprocess.run(["git", "-C", REPO, "config", "user.email", f"verify{VERIFY_SHARD_ID}@depinfarm.org"], check=False)

# Load ASN table once
starts, ends, asns, ccs, orgs = [], [], [], [], []
ap = os.path.join(REPO, ASN_REL)
if os.path.exists(ap):
    with open(ap, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 5:
                continue
            try:
                starts.append(int(p[0]))
                ends.append(int(p[1]))
            except Exception:
                continue
            asns.append(p[2])
            ccs.append(p[3])
            orgs.append(p[4])
    log(f"ASN_ROWS={len(starts)}")
else:
    log("ASN_TABLE_MISSING")

def ip2int(ip):
    a, b, c, d = ip.split(".")
    return (int(a) << 24) | (int(b) << 16) | (int(c) << 8) | int(d)

def asn_of(ip):
    if not starts:
        return ("", "", "")
    try:
        v = ip2int(ip)
        i = bisect_right(starts, v) - 1
        if i < 0 or v > ends[i]:
            return ("", "", "")
        return (asns[i], ccs[i], orgs[i])
    except Exception:
        return ("", "", "")

def try_http(ip, port):
    try:
        s = socket.create_connection((ip, port), TIMEOUT)
        s.settimeout(TIMEOUT)
        s.sendall(f"CONNECT {HOST}:443 HTTP/1.1\r\nHost: {HOST}:443\r\n\r\n".encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            c = s.recv(256)
            if not c:
                s.close()
                return False
            resp += c
            if len(resp) > 4096:
                s.close()
                return False
        if not resp.startswith(b"HTTP/1.1 200") and not resp.startswith(b"HTTP/1.0 200"):
            s.close()
            return False
        ss = SSL_CTX.wrap_socket(s, server_hostname=HOST)
        ss.settimeout(TIMEOUT)
        ss.sendall(f"GET / HTTP/1.1\r\nHost: {HOST}\r\nUser-Agent: curl/8.5.0\r\nConnection: close\r\n\r\n".encode())
        body = b""
        while True:
            c = ss.recv(256)
            if not c:
                break
            body += c
            if len(body) > 4096:
                break
        ss.close()
        if b"\r\n\r\n" in body:
            _, cnt = body.split(b"\r\n\r\n", 1)
            egress = cnt.strip().decode("utf-8", errors="ignore").split()[0]
            if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", egress):
                return True
        return False
    except Exception:
        return False

def try_socks5(ip, port):
    try:
        s = socket.create_connection((ip, port), TIMEOUT)
        s.settimeout(TIMEOUT)
        s.sendall(b"\x05\x01\x00")
        r = s.recv(2)
        if len(r) < 2 or r[0] != 5 or r[1] != 0:
            s.close()
            return False
        req = b"\x05\x01\x00\x03" + bytes([len(HOST)]) + HOST.encode() + struct.pack("!H", 443)
        s.sendall(req)
        resp = s.recv(10)
        if len(resp) < 4 or resp[0] != 5 or resp[1] != 0:
            s.close()
            return False
        ss = SSL_CTX.wrap_socket(s, server_hostname=HOST)
        ss.settimeout(TIMEOUT)
        ss.sendall(f"GET / HTTP/1.1\r\nHost: {HOST}\r\nUser-Agent: curl/8.5.0\r\nConnection: close\r\n\r\n".encode())
        body = b""
        while True:
            c = ss.recv(256)
            if not c:
                break
            body += c
            if len(body) > 4096:
                break
        ss.close()
        if b"\r\n\r\n" in body:
            _, cnt = body.split(b"\r\n\r\n", 1)
            egress = cnt.strip().decode("utf-8", errors="ignore").split()[0]
            if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", egress):
                return True
        return False
    except Exception:
        return False

def check(k):
    ip, port = k.rsplit(":", 1)
    try:
        port = int(port)
    except Exception:
        return None
    t0 = time.time()
    proto = None
    if try_http(ip, port):
        proto = "http"
    elif try_socks5(ip, port):
        proto = "socks5"
    if not proto:
        return None
    ms = int((time.time() - t0) * 1000)
    cls = "FAST" if ms < 1000 else ("MED" if ms < 3000 else "SLOW")
    a, c, o = asn_of(ip)
    return ip + ":" + str(port) + "\t" + proto + "\t" + c + "\t" + a + "\t" + o + "\t" + str(ms) + "\t" + cls

run_once = "--once" in sys.argv
cycle = 0
persistent_alive = load_verified_set(REPO, default_pass=0)
log(f"INITIAL_PERSISTENT_ALIVE={len(persistent_alive)}")

while True:
    cycle += 1
    log(f"\n--- VERIFICATION CYCLE {cycle} (SHARD {VERIFY_SHARD_ID}/{VERIFY_SHARD_TOTAL}) ---")
    elapsed = time.time() - START
    if elapsed >= HARD_STOP:
        log(f"HARD_STOP reached ({elapsed:.0f}s). Exiting.")
        break

    # 1. Pull latest repo
    git_sync(REPO)

    # 2. Gather candidates
    all_rows = []
    seen = set()
    all_candidate_files = list(CANDIDATES)
    for shard_f in glob.glob(os.path.join(REPO, "ip", "harvest", "shodan_shard_*.txt")):
        rel = os.path.relpath(shard_f, REPO).replace("\\", "/")
        if rel not in all_candidate_files:
            all_candidate_files.append(rel)

    for rel in all_candidate_files:
        p = os.path.join(REPO, rel)
        if not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                m = re.match(r"^(\d{1,3}(?:\.\d{1,3}){3})(?::(\d{1,5}))?", line_str)
                if m:
                    ip, port = m.group(1), m.group(2)
                    if port:
                        t = f"{ip}:{port}"
                        if t not in seen:
                            seen.add(t)
                            all_rows.append(t)
                    else:
                        for fp in FALLBACK_PORTS:
                            t = f"{ip}:{fp}"
                            if t not in seen:
                                seen.add(t)
                                all_rows.append(t)

    # Disjoint partition for this shard
    unique_all = sorted(all_rows)
    rows = [c for i, c in enumerate(unique_all) if (i % VERIFY_SHARD_TOTAL) == VERIFY_SHARD_ID]
    log(f"TOTAL_UNIQUE_CANDIDATES={len(unique_all)} | ASSIGNED_TO_SHARD={len(rows)}")

    if not rows:
        log("No candidates assigned. Sleeping 60s...")
        time.sleep(60)
        continue

    # 3. Warm-up pass
    log("STEP: warm-up pass")
    try:
        warmup_n = min(20000, len(rows))
        warmup_samples = rows[:warmup_n]
        def _warmup_dial(t):
            try:
                ip, port = t.rsplit(":", 1)
                s = socket.create_connection((ip, int(port)), 0.75)
                s.close()
            except Exception:
                pass
        with ThreadPoolExecutor(max_workers=min(WORKERS, 1000)) as ex_w:
            list(ex_w.map(_warmup_dial, warmup_samples, chunksize=64))
        log("WARMUP_DONE")
    except Exception as e:
        log(f"WARMUP_ERR: {e}")

    # 4. Verify pool
    log(f"STEP: verify {len(rows)} candidates with {WORKERS} workers, timeout={TIMEOUT}s")
    alive_batch = []
    done = 0
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for r in ex.map(check, rows, chunksize=64):
            done += 1
            if r:
                alive_batch.append(r)
                k = r.split("\t")[0]
                persistent_alive[k] = (r, cycle)
            if done % 5000 == 0:
                log(f"  checked {done}/{len(rows)} alive_batch={len(alive_batch)} persistent_total={len(persistent_alive)}")
            if time.time() - START > HARD_STOP:
                break

    v_elapsed = time.time() - t_start
    log(f"CYCLE_SUMMARY: batch_checked={len(rows)} batch_survived={len(alive_batch)} persistent_before_prune={len(persistent_alive)} in {v_elapsed:.1f}s")

    # Prune stale entries (> 1 pass)
    pruned_alive = {}
    dropped_count = 0
    for k, (prefix, seen_pass) in persistent_alive.items():
        if seen_pass >= 1 and (cycle - seen_pass) <= 1:
            pruned_alive[k] = (prefix, seen_pass)
        else:
            dropped_count += 1
    persistent_alive = pruned_alive
    log(f"PRUNING: dropped={dropped_count} remaining={len(persistent_alive)}")

    # 5. Atomically replace verified_alive_part_<k>.txt and pub_part_<k>.txt
    out = os.path.join(REPO, OUT_REL)
    full_alive_lines = sorted(f"{prefix}\t{seen_pass}" for prefix, seen_pass in persistent_alive.values())
    atomic_write(out, full_alive_lines)

    pub_file = os.path.join(REPO, PUB_REL)
    pub_lines = [k for k in sorted(persistent_alive.keys())]
    atomic_write(pub_file, pub_lines)

    # 6. Commit + push with retry x5
    pushed = False
    for attempt in range(1, 6):
        subprocess.run(["git", "-C", REPO, "pull", "--rebase", "--autostash", "origin", "main"], capture_output=True)
        atomic_write(out, full_alive_lines)
        atomic_write(pub_file, pub_lines)
        subprocess.run(["git", "-C", REPO, "add", OUT_REL, PUB_REL], check=False)
        subprocess.run(["git", "-C", REPO, "commit", "-m", f"cl_verify_{VERIFY_SHARD_ID}: cycle {cycle} SURVIVORS={len(alive_batch)} pool={len(full_alive_lines)} candidates={len(rows)}"], capture_output=True)
        r = subprocess.run(["git", "-C", REPO, "push", "origin", "main"], capture_output=True, text=True)
        if r.returncode == 0:
            log("GIT_PUSH_OK")
            pushed = True
            break
        time.sleep(random.randint(2, 6))

    if not pushed:
        log("WARN: Failed to push verified_alive_part after 5 attempts")

    if run_once:
        break

    log("Sleeping 180s (3 minutes) before next cycle...")
    time.sleep(180)

log("ALL_DONE")
