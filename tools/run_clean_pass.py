import os
import re
import sys
import time
import socket
import struct
import ssl
from concurrent.futures import ThreadPoolExecutor
from bisect import bisect_right

REPO = r"D:\DEpinFarm"
OUT_REL = "ip/harvest/verified_alive.txt"
ASN_REL = "data/ip2asn-v4-u32.tsv"
WORKERS = 400
TIMEOUT = 3
HOST = "api.ipify.org"

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# Load ASN table
starts, ends, asns, ccs, orgs = [], [], [], [], []
ap = os.path.join(REPO, ASN_REL)
if os.path.exists(ap):
    with open(ap, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 5: continue
            try:
                starts.append(int(p[0]))
                ends.append(int(p[1]))
            except Exception: continue
            asns.append(p[2])
            ccs.append(p[3])
            orgs.append(p[4])

def ip2int(ip):
    a, b, c, d = ip.split(".")
    return (int(a) << 24) | (int(b) << 16) | (int(c) << 8) | int(d)

def asn_of(ip):
    if not starts: return ("", "", "")
    try:
        v = ip2int(ip)
        i = bisect_right(starts, v) - 1
        if i < 0 or v > ends[i]: return ("", "", "")
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
            if not c: break
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
            if not c: break
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
        if atyp == 1: s.recv(4 + 2)
        elif atyp == 3:
            alen = s.recv(1)[0]
            s.recv(alen + 2)
        elif atyp == 4: s.recv(16 + 2)

        tls_s = SSL_CTX.wrap_socket(s, server_hostname=HOST)
        tls_s.settimeout(TIMEOUT)
        tls_s.sendall(f"GET / HTTP/1.1\r\nHost: {HOST}\r\nConnection: close\r\n\r\n".encode())
        body = b""
        while True:
            c = tls_s.recv(256)
            if not c: break
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
    if try_http(ip, port): proto = "http"
    elif try_socks5(ip, port): proto = "socks5"
    if not proto: return None
    ms = int((time.time() - t0) * 1000)
    cls = "FAST" if ms < 1000 else ("MED" if ms < 3000 else "SLOW")
    a, c, o = asn_of(ip)
    return ip + ":" + str(port) + "\t" + proto + "\t" + c + "\t" + a + "\t" + o + "\t" + str(ms) + "\t" + cls

def atomic_write(filepath, lines):
    tmp_path = filepath + ".tmp"
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
        for line in lines:
            f.write(line + "\n")
        f.flush()
        try: os.fsync(f.fileno())
        except Exception: pass
    os.replace(tmp_path, filepath)

def run_pass():
    val_path = os.path.join(REPO, OUT_REL)
    existing = {}
    if os.path.exists(val_path):
        with open(val_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_str = line.strip()
                if line_str and "\t" in line_str:
                    parts = line_str.split("\t")
                    k = parts[0]
                    seen_pass = int(parts[7]) if len(parts) >= 8 else 0
                    prefix = "\t".join(parts[:7])
                    existing[k] = (prefix, seen_pass)

    keys = list(existing.keys())
    print(f"STARTING CLEAN FULL PASS: {len(keys):,} candidates with {WORKERS} workers...", flush=True)

    CURRENT_PASS = 1
    t0 = time.time()
    survivors = []
    done = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for r in ex.map(check, keys, chunksize=32):
            done += 1
            if r:
                survivors.append(r)
                k = r.split("\t")[0]
                existing[k] = (r, CURRENT_PASS)
            if done % 2000 == 0 or done == len(keys):
                rate = done / (time.time() - t0)
                print(f"  Progress: {done:,}/{len(keys):,} ({done/len(keys)*100:.1f}%) survivors={len(survivors):,} ({rate:.1f} tests/s)", flush=True)

    dt = time.time() - t0
    pass_survivors = len(survivors)
    print(f"\nPASS COMPLETE in {dt:.1f}s")
    print(f"PASS_SURVIVORS={pass_survivors}")

    # PRUNE: Drop any proxy whose last_seen is older than 2 full passes (CURRENT_PASS - seen > 2)
    pruned = {}
    dropped = 0
    for k, (prefix, seen) in existing.items():
        if (CURRENT_PASS - seen) <= 2:
            pruned[k] = (prefix, seen)
        else:
            dropped += 1

    print(f"PRUNING: dropped={dropped:,} remaining={len(pruned):,} (retention window: last_seen >= {CURRENT_PASS - 2})")

    # Atomic write verified_alive.txt with 8 columns
    full_lines = sorted(f"{prefix}\t{seen}" for prefix, seen in pruned.values())
    atomic_write(val_path, full_lines)

    # Atomic write pub.txt and pub_fast.txt
    pub_file = os.path.join(REPO, "ip", "pub.txt")
    atomic_write(pub_file, sorted(pruned.keys()))

    pub_fast_file = os.path.join(REPO, "ip", "pub_fast.txt")
    fast_rows = [k for k, (prefix, _) in sorted(pruned.items()) if "\tFAST" in prefix or "\tMED" in prefix]
    atomic_write(pub_fast_file, fast_rows[:1000])

    print(f"Wrote {len(full_lines):,} rows to {val_path}")
    return pass_survivors, len(full_lines)

if __name__ == "__main__":
    run_pass()
