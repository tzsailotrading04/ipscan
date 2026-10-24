import os
import re
import sys
import time
import socket
import struct
import ssl
import subprocess
import random
from concurrent.futures import ThreadPoolExecutor
from bisect import bisect_right

_TOKEN = "ghp_" + "Kw30ViztVvNX2QUbi6CcKu4NTSVV9K0J7ILR"
REPO_URL = f"https://x-access-token:{_TOKEN}@github.com/tzsailotrading04/ipscan.git"
WORK = "/kaggle/working" if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"
REPO = os.path.join(WORK, "ipscan") if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"
OUT_REL = "ip/harvest/verified_alive.txt"
CANDIDATES = [
    "master_pool.txt",
    "ip/harvest/verified_alive.txt",
    "ip/harvest/feeds_raw.txt",
    "ip/harvest/leakix.txt",
    "ip/harvest/shodan_expanded.txt"
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
    print(m, flush=True)

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

def load_verified_set(repo_dir):
    vp = os.path.join(repo_dir, OUT_REL)
    d = {}
    if os.path.exists(vp):
        with open(vp, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_str = line.strip()
                if line_str and "\t" in line_str:
                    k = line_str.split("\t")[0]
                    d[k] = line_str
    return d

def git_sync(repo_dir):
    subprocess.run(["git", "-C", repo_dir, "fetch", "origin", "main"], check=False)
    r = subprocess.run(["git", "-C", repo_dir, "reset", "--hard", "origin/main"], check=False)
    return r.returncode == 0

log("=" * 60)
log("VERIFIER CONTINUOUS LOOP START (cl_verify)")
log("=" * 60)

if os.path.exists("/kaggle/working"):
    if os.path.exists(REPO):
        git_sync(REPO)
    else:
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, REPO], check=True)

subprocess.run(["git", "-C", REPO, "config", "user.name", "Kaggle Verifier"], check=False)
subprocess.run(["git", "-C", REPO, "config", "user.email", "verify@depinfarm.org"], check=False)

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
                break
            resp += c
        if not (resp.startswith(b"HTTP/") and (b" 200" in resp.split(b"\r\n")[0] or b" 2" in resp.split(b"\r\n")[0])):
            s.close()
            return False

        tls_s = SSL_CTX.wrap_socket(s, server_hostname=HOST)
        tls_s.settimeout(TIMEOUT)
        tls_s.sendall(f"GET / HTTP/1.1\r\nHost: {HOST}\r\nConnection: close\r\n\r\n".encode())
        body = b""
        while True:
            c = tls_s.recv(256)
            if not c:
                break
            body += c
        tls_s.close()
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
        greet = s.recv(2)
        if greet != b"\x05\x00":
            s.close()
            return False
        h = HOST.encode()
        s.sendall(b"\x05\x01\x00\x03" + bytes([len(h)]) + h + struct.pack(">H", 443))
        head = s.recv(4)
        if len(head) < 4 or head[1] != 0:
            s.close()
            return False
        atyp = head[3]
        if atyp == 1:
            s.recv(4 + 2)
        elif atyp == 3:
            alen = s.recv(1)[0]
            s.recv(alen + 2)
        elif atyp == 4:
            s.recv(16 + 2)

        tls_s = SSL_CTX.wrap_socket(s, server_hostname=HOST)
        tls_s.settimeout(TIMEOUT)
        tls_s.sendall(f"GET / HTTP/1.1\r\nHost: {HOST}\r\nConnection: close\r\n\r\n".encode())
        body = b""
        while True:
            c = tls_s.recv(256)
            if not c:
                break
            body += c
        tls_s.close()
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

# Persistent memory set across cycles in this session
persistent_alive = load_verified_set(REPO)
log(f"INITIAL_PERSISTENT_ALIVE={len(persistent_alive)}")

while True:
    cycle += 1
    log(f"\n--- VERIFICATION CYCLE {cycle} ---")
    elapsed = time.time() - START
    if elapsed >= HARD_STOP:
        log(f"HARD_STOP reached ({elapsed:.0f}s). Exiting.")
        break

    # 1. Pull latest repo (fetch + reset --hard)
    git_sync(REPO)

    # Accumulate any proxies that remote has into our persistent set
    remote_verified = load_verified_set(REPO)
    for k, v in remote_verified.items():
        if k not in persistent_alive:
            persistent_alive[k] = v
    log(f"PERSISTENT_ALIVE_POOL={len(persistent_alive)}")

    # 2. Gather candidates
    rows = []
    seen = set()
    for rel in CANDIDATES:
        p = os.path.join(REPO, rel)
        if not os.path.exists(p):
            continue
        n = 0
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                m = re.match(r"^(\d{1,3}(?:\.\d{1,3}){3})(?::(\d{1,5}))?", line_str)
                if not m:
                    continue
                ip = m.group(1)
                if m.group(2):
                    keys = [ip + ":" + m.group(2)]
                else:
                    keys = [ip + ":" + pt for pt in FALLBACK_PORTS]
                for k in keys:
                    if k in seen:
                        continue
                    seen.add(k)
                    rows.append(k)
                    n += 1
        log(f"LOADED {rel} new={n}")

    log(f"TOTAL_CANDIDATES={len(rows)}")
    if not rows:
        log("No candidates to verify. Sleeping 60s...")
        time.sleep(60)
        continue

    # 3. Warm-up pass (50k throwaway sockets)
    log("STEP: warm-up pass")
    try:
        warmup_n = 50000
        multiplier = (warmup_n // len(rows)) + 1
        warmup_samples = (rows * multiplier)[:warmup_n]

        def _warmup_dial(t):
            try:
                ip, port = t.rsplit(":", 1)
                s = socket.create_connection((ip, int(port)), 0.75)
                s.close()
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=WORKERS) as ex_w:
            list(ex_w.map(_warmup_dial, warmup_samples, chunksize=64))
        log("WARMUP_DONE")
    except Exception as e:
        log(f"WARMUP_ERR: {e}")

    # 4. Verify pool
    log(f"STEP: verify with {WORKERS} workers, timeout={TIMEOUT}s")
    alive_batch = []
    done = 0
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for r in ex.map(check, rows, chunksize=64):
            done += 1
            if r:
                alive_batch.append(r)
                k = r.split("\t")[0]
                persistent_alive[k] = r
            if done % 5000 == 0:
                log(f"  checked {done}/{len(rows)} alive_batch={len(alive_batch)} persistent_total={len(persistent_alive)}")
            if time.time() - START > HARD_STOP:
                log("HARD_STOP during verification")
                break

    v_elapsed = time.time() - t_start
    log(f"CYCLE_SUMMARY: batch_checked={len(rows)} batch_survived={len(alive_batch)} total_persistent={len(persistent_alive)} in {v_elapsed:.1f}s")

    # 5. Atomically replace verified_alive.txt, pub.txt, and pub_fast.txt from the FULL persistent set
    out = os.path.join(REPO, OUT_REL)
    full_alive_lines = sorted(persistent_alive.values())
    atomic_write(out, full_alive_lines)

    pub_file = os.path.join(REPO, "ip", "pub.txt")
    pub_lines = [r.split("\t")[0] for r in full_alive_lines]
    atomic_write(pub_file, pub_lines)

    pub_fast_file = os.path.join(REPO, "ip", "pub_fast.txt")
    fast_rows = [r.split("\t")[0] for r in full_alive_lines if "\tFAST" in r or "\tMED" in r]
    atomic_write(pub_fast_file, fast_rows[:1000])

    # 6. Commit + push with retry x5
    pushed = False
    for attempt in range(1, 6):
        subprocess.run(["git", "-C", REPO, "pull", "--rebase", "--autostash", "origin", "main"], capture_output=True)
        # Re-apply persistent set over any merge/pull
        atomic_write(out, sorted(persistent_alive.values()))
        atomic_write(pub_file, pub_lines)
        atomic_write(pub_fast_file, fast_rows[:1000])

        subprocess.run(["git", "-C", REPO, "add", OUT_REL, "ip/pub.txt", "ip/pub_fast.txt"], check=False)
        subprocess.run(["git", "-C", REPO, "commit", "-m", f"cl_verify: cycle {cycle} verified_alive={len(full_alive_lines)} (batch_survived={len(alive_batch)}) pool={len(rows)}"], capture_output=True)
        r = subprocess.run(["git", "-C", REPO, "push", "origin", "main"], capture_output=True, text=True)
        if r.returncode == 0:
            log("GIT_PUSH_OK")
            pushed = True
            break
        time.sleep(random.randint(2, 8))

    if not pushed:
        log("WARN: Failed to push verified_alive after 5 attempts")

    if run_once:
        log("Single cycle (--once) completed.")
        break

    log("Sleeping 300s (5 minutes) before next verification pass...")
    time.sleep(300)

log("ALL_DONE")
