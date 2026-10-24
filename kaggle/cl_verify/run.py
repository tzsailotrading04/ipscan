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
WORK = "/kaggle/working"
REPO = os.path.join(WORK, "ipscan")
OUT_REL = "ip/harvest/verified_alive.txt"
CANDIDATES = ["ip/harvest/verified_alive.txt", "ip/harvest/feeds_raw.txt", "ip/harvest/leakix.txt",
              "ip/harvest/hits_new_exits.txt", "ip/harvest/net_new.txt"]
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

log("=" * 60)
log("VERIFIER START")
log("=" * 60)

if os.path.exists(REPO):
    subprocess.run(["git", "-C", REPO, "pull", "--rebase", "--autostash", "origin", "main"], capture_output=True)
else:
    subprocess.run(["git", "clone", "--depth", "1", REPO_URL, REPO], check=True)

subprocess.run(["git", "-C", REPO, "config", "user.name", "Kaggle Verifier"], check=False)
subprocess.run(["git", "-C", REPO, "config", "user.email", "verify@depinfarm.org"], check=False)

rows = []
seen = set()
for rel in CANDIDATES:
    p = os.path.join(REPO, rel)
    if not os.path.exists(p):
        log("MISSING " + rel)
        continue
    n = 0
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = re.match(r"^(\d{1,3}(?:\.\d{1,3}){3})(?::(\d{1,5}))?", line.strip())
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
    log("LOADED " + rel + " new=" + str(n))

log("TOTAL_CANDIDATES=" + str(len(rows)))

starts, ends, asns, ccs, orgs = [], [], [], [], []
ap = os.path.join(REPO, ASN_REL)
if os.path.exists(ap):
    with open(ap, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 5:
                continue
            try:
                starts.append(int(p[0])); ends.append(int(p[1]))
            except Exception:
                continue
            asns.append(p[2]); ccs.append(p[3]); orgs.append(p[4])
    log("ASN_ROWS=" + str(len(starts)))
else:
    log("ASN_TABLE_MISSING")

def ip2int(ip):
    a, b, c, d = ip.split(".")
    return (int(a) << 24) | (int(b) << 16) | (int(c) << 8) | int(d)

def asn_of(ip):
    if not starts:
        return ("", "", "")
    v = ip2int(ip)
    i = bisect_right(starts, v) - 1
    if i < 0 or v > ends[i]:
        return ("", "", "")
    return (asns[i], ccs[i], orgs[i])

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
        
        # TLS Handshake + egress IP check
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
        
        # TLS Handshake + egress IP check
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

# Warm-up pass (50k throwaway sockets)
log("STEP: warm-up pass")
try:
    warmup_n = 50000
    if rows:
        multiplier = (warmup_n // len(rows)) + 1
        warmup_samples = (rows * multiplier)[:warmup_n]
    else:
        warmup_samples = []

    def _warmup_dial(t):
        try:
            ip, port = t.rsplit(":", 1)
            s = socket.create_connection((ip, int(port)), 0.75)
            s.close()
        except Exception:
            pass

    if warmup_samples:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex_w:
            list(ex_w.map(_warmup_dial, warmup_samples, chunksize=64))
    log("WARMUP_DONE")
except Exception as e:
    log(f"WARMUP_ERR: {e}")

log("STEP: verify with " + str(WORKERS) + " workers")
alive = []
done = 0
with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    for r in ex.map(check, rows, chunksize=64):
        done += 1
        if r:
            alive.append(r)
        if done % 5000 == 0:
            log("  checked " + str(done) + "/" + str(len(rows)) + " alive=" + str(len(alive)))
        if time.time() - START > HARD_STOP:
            log("HARD_STOP")
            break

out = os.path.join(REPO, OUT_REL)
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8", newline="\n") as f:
    for r in alive:
        f.write(r + "\n")

log("VERIFIED_ALIVE=" + str(len(alive)))

for attempt in range(5):
    subprocess.run(["git", "-C", REPO, "pull", "--rebase", "--autostash", "origin", "main"], capture_output=True)
    subprocess.run(["git", "-C", REPO, "add", OUT_REL], check=False)
    subprocess.run(["git", "-C", REPO, "commit", "-m", "verified_alive " + str(len(alive))], capture_output=True)
    r = subprocess.run(["git", "-C", REPO, "push", "origin", "main"], capture_output=True, text=True)
    if r.returncode == 0:
        log("GIT_PUSH_OK")
        break
    time.sleep(random.randint(2, 8))

log("ALL_DONE")
