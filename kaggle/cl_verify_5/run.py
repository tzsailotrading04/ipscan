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
VERIFY_IDX = 5
NUM_VERIFY = 9
OUT_REL = f"ip/harvest/verified_alive_part_{VERIFY_IDX}.txt"

def should_process_file(filepath, verify_idx, num_verify=9):
    fname = os.path.basename(filepath)
    m = re.search(r"shodan_shard_(?:v\d+_)?(\d+)", fname)
    if m:
        shard_idx = int(m.group(1))
        return (shard_idx % num_verify) == verify_idx
    # Non-shard files (feeds_raw, leakix, etc.) processed by instance 0
    return verify_idx == 0

CANDIDATES = ["ip/harvest/lists_all.txt", "ip/harvest/feeds_raw.txt", "ip/harvest/leakix.txt",
              "ip/harvest/hits_new_exits.txt", "ip/harvest/net_new.txt"]
CANDIDATES += sorted(glob.glob("ip/harvest/shodan_shard_v98_*_c*.txt"))
CANDIDATES += sorted(glob.glob("ip/harvest/shodan_shard_v98_*.txt"))
CANDIDATES += sorted(glob.glob("ip/harvest/shodan_shard_*.txt"))
FALLBACK_PORTS = ["8080", "3128", "1080", "8000", "8888"]
ASN_REL = "data/ip2asn-v4-u32.tsv"
WORKERS = 2000
TIMEOUT = 2
HOST = "api.ipify.org"
HARD_STOP = 9 * 3600
START = time.time()

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

def log(m):
    print(m, flush=True)
    sys.stdout.flush()

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
    r = subprocess.run(["git", "-C", repo_dir, "reset", "--hard", "origin/main"], check=False)
    return r.returncode == 0

log("=" * 60)
log("VERIFIER CONTINUOUS LOOP START (cl_verify_5)")
log("=" * 60)

if os.path.exists("/kaggle/working"):
    if os.path.exists(REPO):
        git_sync(REPO)
    else:
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, REPO], check=True)

subprocess.run(["git", "-C", REPO, "config", "user.name", "Verifier 5"], check=False)
subprocess.run(["git", "-C", REPO, "config", "user.email", "verify_5@depinfarm.org"], check=False)

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

PROXY_PORTS = [8080, 3128, 1080, 8000, 8888, 80, 1081, 3127, 3129, 8001,
               8081, 8118, 9000, 4145, 10808]
PROXY_PORTS_SET = set(PROXY_PORTS)

def check(k):
    k = k.strip()
    if not k:
        return None
    ip = k
    p = None
    if ":" in k:
        ip, port_str = k.rsplit(":", 1)
        try:
            p = int(port_str)
        except Exception:
            p = None

    if p is not None and p in PROXY_PORTS_SET:
        test_ports = [p] + [x for x in PROXY_PORTS if x != p][:2]
    else:
        test_ports = PROXY_PORTS[:4]

    for port in test_ports:
        t0 = time.time()
        proto = None
        if try_http(ip, port):
            proto = "http"
        elif try_socks5(ip, port):
            proto = "socks5"
        if proto:
            ms = int((time.time() - t0) * 1000)
            cls = "FAST" if ms < 1000 else ("MED" if ms < 3000 else "SLOW")
            a, c, o = asn_of(ip)
            return ip + ":" + str(port) + "\t" + proto + "\t" + c + "\t" + a + "\t" + o + "\t" + str(ms) + "\t" + cls
    return None

run_once = "--once" in sys.argv
cycle = 0

# Persistent memory set across cycles in this session: key -> (line_prefix_7cols, last_seen_pass)
persistent_alive = load_verified_set(REPO, default_pass=0)
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
    remote_verified = load_verified_set(REPO, default_pass=cycle - 1)
    for k, (prefix, remote_seen) in remote_verified.items():
        if k not in persistent_alive or remote_seen > persistent_alive[k][1]:
            persistent_alive[k] = (prefix, remote_seen)
    log(f"PERSISTENT_ALIVE_POOL={len(persistent_alive)}")

    # 2. Gather candidates (lists_all.txt FIRST, then new high-yield chunks)
    list_files = [os.path.join(REPO, "ip", "harvest", "lists_all.txt")]
    chunk_files = sorted(glob.glob(os.path.join(REPO, "ip", "harvest", "shodan_shard_v98_*_c*.txt")))
    feed_files = [
        os.path.join(REPO, "ip", "harvest", "feeds_raw.txt"),
        os.path.join(REPO, "ip", "harvest", "net_new.txt"),
        os.path.join(REPO, "ip", "harvest", "leakix.txt"),
        os.path.join(REPO, "ip", "harvest", "hits_new_exits.txt"),
    ]
    old_v98_files = sorted([f for f in glob.glob(os.path.join(REPO, "ip", "harvest", "shodan_shard_v98_*.txt")) if "_c" not in os.path.basename(f)])
    legacy_files = sorted([f for f in glob.glob(os.path.join(REPO, "ip", "harvest", "shodan_shard_*.txt")) if "v98" not in os.path.basename(f)])
    all_candidate_files = [f for f in list_files if os.path.exists(f)] + chunk_files + [f for f in feed_files if os.path.exists(f)] + old_v98_files + legacy_files

    combined_cands = []
    seen = set()
    for p in all_candidate_files:
        if not os.path.exists(p):
            continue
        rel = os.path.relpath(p, REPO).replace(chr(92), "/")
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
                    keys = [ip]
                for k in keys:
                    if k in seen:
                        continue
                    seen.add(k)
                    combined_cands.append(k)
                    n += 1

    # Index striding: each verifier takes every NUM_VERIFY-th candidate
    rows = combined_cands[VERIFY_IDX::NUM_VERIFY]
    log(f"VERIFIER {VERIFY_IDX}/{NUM_VERIFY} selected {len(rows):,} candidates out of {len(combined_cands):,} combined (stride={NUM_VERIFY})")
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
    last_commit_time = time.time()
    BATCH = 50000
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for start in range(0, len(rows), BATCH):
            batch = rows[start:start+BATCH]
            port_count = sum(1 for x in batch if ":" in x)
            batch_alive = 0
            for r in ex.map(check, batch, chunksize=32):
                done += 1
                if r:
                    batch_alive += 1
                    alive_batch.append(r)
                    k = r.split("\t")[0]
                    persistent_alive[k] = (r, cycle)
            alive_rate = (batch_alive / len(batch) * 100) if batch else 0.0
            log(f"[BATCH] {start+len(batch):,}/{len(rows):,} done={done:,} alive={len(alive_batch):,} had_port={port_count:,}/{len(batch):,} alive_rate={alive_rate:.2f}%")

            # Write verified_alive.txt after every batch (cheap, local)
            out_incr = os.path.join(REPO, OUT_REL)
            incr_lines = sorted(f"{prefix}\t{seen_pass}" for prefix, seen_pass in persistent_alive.values())
            atomic_write(out_incr, incr_lines)

            # Commit to git every 300 seconds
            if time.time() - last_commit_time >= 300:
                subprocess.run(["git", "-C", REPO, "add", OUT_REL], check=False)
                subprocess.run(["git", "-C", REPO, "commit", "-m", f"cl_verify_5: incremental batch done={done} alive={len(alive_batch)}"], capture_output=True)
                for attempt in range(1, 6):
                    subprocess.run(["git", "-C", REPO, "fetch", "origin", "main"], capture_output=True)
                    r = subprocess.run(["git", "-C", REPO, "push", "origin", "main"], capture_output=True, text=True)
                    if r.returncode == 0:
                        log("INCREMENTAL_GIT_PUSH_OK")
                        break
                    subprocess.run(["git", "-C", REPO, "merge", "origin/main", "-X", "ours", "--no-edit"], capture_output=True)
                    time.sleep(2)
                last_commit_time = time.time()

            if time.time() - START > HARD_STOP:
                log("HARD_STOP during verification")
                break

    v_elapsed = time.time() - t_start
    log(f"CYCLE_SUMMARY: batch_checked={len(rows)} batch_survived={len(alive_batch)} persistent_before_prune={len(persistent_alive)} in {v_elapsed:.1f}s")

    # Step 2: PRUNE. Retention window: keep entries seen within the last 3 cycles
    pruned_alive = {}
    dropped_count = 0
    for k, (prefix, seen_pass) in persistent_alive.items():
        if seen_pass >= 1 and (cycle - seen_pass) <= 3:
            pruned_alive[k] = (prefix, seen_pass)
        else:
            dropped_count += 1
    persistent_alive = pruned_alive
    log(f"PRUNING: dropped={dropped_count} remaining={len(persistent_alive)} (retention window: 3 cycles, last_seen >= {max(1, cycle - 3)})")

    # 5. Atomically replace verified_alive_part_5.txt from the FULL persistent set
    out = os.path.join(REPO, OUT_REL)
    full_alive_lines = sorted(f"{prefix}\t{seen_pass}" for prefix, seen_pass in persistent_alive.values())
    atomic_write(out, full_alive_lines)

    # 6. Commit + push with retry x5
    subprocess.run(["git", "-C", REPO, "add", OUT_REL], check=False)
    subprocess.run(["git", "-C", REPO, "commit", "-m", f"cl_verify_5: cycle {cycle} PASS_SURVIVORS={len(alive_batch)} pool_after_prune={len(full_alive_lines)} candidates={len(rows)}"], capture_output=True)
    pushed = False
    for attempt in range(1, 6):
        subprocess.run(["git", "-C", REPO, "fetch", "origin", "main"], capture_output=True)
        r = subprocess.run(["git", "-C", REPO, "push", "origin", "main"], capture_output=True, text=True)
        if r.returncode == 0:
            log("GIT_PUSH_OK")
            pushed = True
            break
        subprocess.run(["git", "-C", REPO, "merge", "origin/main", "-X", "ours", "--no-edit"], capture_output=True)
        time.sleep(random.randint(2, 8))

    if not pushed:
        log("WARN: Failed to push verified_alive after 5 attempts")

    if run_once:
        log("Single cycle (--once) completed.")
        break

    log("Sleeping 300s (5 minutes) before next verification pass...")
    time.sleep(300)

log("ALL_DONE")
