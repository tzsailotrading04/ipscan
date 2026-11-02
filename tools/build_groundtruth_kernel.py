import os, json

with open("work/groundtruth.txt", "r", encoding="utf-8") as f:
    proxies = [l.strip() for l in f if l.strip()]

print(f"Loaded {len(proxies)} proxies from work/groundtruth.txt")

os.makedirs("kaggle/test_groundtruth", exist_ok=True)

meta = {
    "id": "remruata/test-groundtruth-probe",
    "title": "test-groundtruth-probe",
    "code_file": "run.py",
    "language": "python",
    "kernel_type": "script",
    "is_private": True,
    "enable_gpu": False,
    "enable_internet": True,
    "dataset_sources": [],
    "competition_sources": [],
    "kernel_sources": []
}
with open("kaggle/test_groundtruth/kernel-metadata.json", "w", encoding="utf-8") as f:
    json.dump(meta, f, indent=2)

proxies_repr = repr(proxies)

code = f'''import socket
import ssl
import time
import concurrent.futures

PROXIES = {proxies_repr}
TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
SSL_CTX = ssl.create_default_context()

# Precompute MemoryBIO ClientHellos with exact SNI
CLIENT_HELLOS = {{}}
for t in TARGETS:
    ctx = ssl.create_default_context()
    bio_in, bio_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    sslobj = ctx.wrap_bio(bio_in, bio_out, server_hostname=t)
    try:
        sslobj.do_handshake()
    except ssl.SSLWantReadError:
        pass
    CLIENT_HELLOS[t] = bio_out.read()

# Hardcoded ClientHello bytes (without SNI)
HARDCODED_CLIENT_HELLO = (
    b"\\x16\\x03\\x01\\x00\\xba\\x01\\x00\\x00\\xb6\\x03\\x03"
    b"\\x00\\x01\\x02\\x03\\x04\\x05\\x06\\x07\\x08\\t\\n\\x0b\\x0c\\r\\x0e\\x0f"
    b"\\x10\\x11\\x12\\x13\\x14\\x15\\x16\\x17\\x18\\x19\\x1a\\x1b\\x1c\\x1d\\x1e\\x1f"
    b"\\x00\\x00 \\x13\\x01\\x13\\x02\\x13\\x03\\xc0+\\xc0/\\xcc\\xa9\\xcc\\xa8"
    b"\\xc0,\\xc00\\xc0\\n\\xc0\\t\\xc0\\x13\\xc0\\x14\\x00\\x9c\\x00\\x9d\\x00/\\x005"
    b"\\x01\\x00\\x00m\\x00\\x17\\x00\\x00\\xff\\x01\\x00\\x01\\x00\\x00\\n\\x00\\x0e"
    b"\\x00\\x0c\\x00\\x1d\\x00\\x17\\x00\\x18\\x00\\x19\\x01\\x00\\x01\\x01\\x00\\x0b"
    b"\\x00\\x02\\x01\\x00\\x00#\\x00\\x00\\x00\\x10\\x00\\x0e\\x00\\x0c\\x02h2\\x08http/1.1"
)

# -------------------------------------------------------------
# 1. Shard Probe (exact run.py logic)
# -------------------------------------------------------------
def sync_tls_handshake(sock, target, timeout):
    try:
        sock.setblocking(True)
        sock.settimeout(timeout)
        req = f"CONNECT {{target}}:443 HTTP/1.1\\r\\nHost: {{target}}:443\\r\\n\\r\\n".encode()
        sock.sendall(req)
        resp = b""
        while b"\\r\\n\\r\\n" not in resp:
            chunk = sock.recv(512)
            if not chunk: return False
            resp += chunk
            if len(resp) > 2048: return False
        first_line = resp.split(b"\\r\\n")[0]
        if not (b" 200" in first_line or b"HTTP/1.1 200" in first_line or b"HTTP/1.0 200" in first_line):
            return False
        parts = resp.split(b"\\r\\n\\r\\n", 1)
        trailing = parts[1] if len(parts) > 1 else b""
        if trailing and trailing[:1] != b"\\x16":
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

def probe_shard_style(addr, timeout):
    ip, port_s = addr.split(":")
    port = int(port_s)
    # primary
    s = None
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        if sync_tls_handshake(s, TARGETS[0], timeout=timeout):
            return True
    except Exception:
        if s:
            try: s.close()
            except Exception: pass
    # fallbacks
    for t in TARGETS[1:]:
        s2 = None
        try:
            s2 = socket.create_connection((ip, port), timeout=timeout)
            if sync_tls_handshake(s2, t, timeout=timeout):
                return True
        except Exception:
            if s2:
                try: s2.close()
                except Exception: pass
    return False

# -------------------------------------------------------------
# 2. MemoryBIO ClientHello Probe (with correct SNI)
# -------------------------------------------------------------
def probe_memorybio_sni(addr, timeout=8.0):
    ip, port_s = addr.split(":")
    port = int(port_s)
    for target in TARGETS:
        s = None
        try:
            s = socket.create_connection((ip, port), timeout=timeout)
            s.settimeout(timeout)
            req = f"CONNECT {{target}}:443 HTTP/1.1\\r\\nHost: {{target}}:443\\r\\n\\r\\n".encode()
            s.sendall(req)
            resp = b""
            while b"\\r\\n\\r\\n" not in resp:
                chunk = s.recv(512)
                if not chunk: break
                resp += chunk
                if len(resp) > 2048: break
            first_line = resp.split(b"\\r\\n")[0]
            if not (b" 200" in first_line or b"HTTP/1.1 200" in first_line or b"HTTP/1.0 200" in first_line):
                s.close()
                continue
            parts = resp.split(b"\\r\\n\\r\\n", 1)
            trailing = parts[1] if len(parts) > 1 else b""
            if trailing:
                if trailing[:1] == b"\\x16":
                    s.close()
                    return True
                s.close()
                continue
            # Send MemoryBIO ClientHello carrying exact SNI for target
            s.sendall(CLIENT_HELLOS[target])
            b1 = s.recv(1)
            s.close()
            if b1 == b"\\x16":
                return True
        except Exception:
            if s:
                try: s.close()
                except Exception: pass
    return False

# -------------------------------------------------------------
# 3. Hardcoded Bytes Probe (no SNI)
# -------------------------------------------------------------
def probe_hardcoded_bytes(addr, timeout=8.0):
    ip, port_s = addr.split(":")
    port = int(port_s)
    for target in TARGETS:
        s = None
        try:
            s = socket.create_connection((ip, port), timeout=timeout)
            s.settimeout(timeout)
            req = f"CONNECT {{target}}:443 HTTP/1.1\\r\\nHost: {{target}}:443\\r\\n\\r\\n".encode()
            s.sendall(req)
            resp = b""
            while b"\\r\\n\\r\\n" not in resp:
                chunk = s.recv(512)
                if not chunk: break
                resp += chunk
                if len(resp) > 2048: break
            first_line = resp.split(b"\\r\\n")[0]
            if not (b" 200" in first_line or b"HTTP/1.1 200" in first_line or b"HTTP/1.0 200" in first_line):
                s.close()
                continue
            parts = resp.split(b"\\r\\n\\r\\n", 1)
            trailing = parts[1] if len(parts) > 1 else b""
            if trailing:
                if trailing[:1] == b"\\x16":
                    s.close()
                    return True
                s.close()
                continue
            # Send hardcoded bytes without target SNI
            s.sendall(HARDCODED_CLIENT_HELLO)
            b1 = s.recv(1)
            s.close()
            if b1 == b"\\x16":
                return True
        except Exception:
            if s:
                try: s.close()
                except Exception: pass
    return False

def main():
    total = len(PROXIES)
    print(f"Starting Groundtruth Evaluation on {{total}} proxies from Kaggle container...", flush=True)

    # 1. Exact shard probe (baseline 5.0s timeout)
    print("\\n--- 1. Running exact shard probe (5.0s timeout) ---", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        res1 = list(ex.map(lambda p: probe_shard_style(p, timeout=5.0), PROXIES))
    p1_pass = sum(res1)
    p1_pct = (p1_pass / total) * 100.0
    print(f"Shard Probe (5.0s): {{p1_pass}}/{{total}} passed ({{p1_pct:.2f}}%)", flush=True)

    # 2. Exact shard probe with 8.0s timeout
    print("\\n--- 2. Running shard probe with 8-second timeout ---", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        res2 = list(ex.map(lambda p: probe_shard_style(p, timeout=8.0), PROXIES))
    p2_pass = sum(res2)
    p2_pct = (p2_pass / total) * 100.0
    print(f"Shard Probe (8.0s): {{p2_pass}}/{{total}} passed ({{p2_pct:.2f}}%)", flush=True)

    # 3. ClientHello via ssl.MemoryBIO with correct SNI (8.0s timeout)
    print("\\n--- 3. Running ClientHello via ssl.MemoryBIO with correct SNI (8.0s timeout) ---", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        res3 = list(ex.map(lambda p: probe_memorybio_sni(p, timeout=8.0), PROXIES))
    p3_pass = sum(res3)
    p3_pct = (p3_pass / total) * 100.0
    print(f"MemoryBIO with SNI (8.0s): {{p3_pass}}/{{total}} passed ({{p3_pct:.2f}}%)", flush=True)

    # 4. Hardcoded bytes comparison
    print("\\n--- 4. Reference: Hardcoded bytes without correct SNI (8.0s timeout) ---", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        res4 = list(ex.map(lambda p: probe_hardcoded_bytes(p, timeout=8.0), PROXIES))
    p4_pass = sum(res4)
    p4_pct = (p4_pass / total) * 100.0
    print(f"Hardcoded bytes (8.0s): {{p4_pass}}/{{total}} passed ({{p4_pct:.2f}}%)", flush=True)

    print("\\n================ FINAL SUMMARY ================", flush=True)
    print(f"Total Groundtruth Tested      : {{total}}", flush=True)
    print(f"1. Shard Probe (5.0s)          : {{p1_pass}}/{{total}} ({{p1_pct:.2f}}%)", flush=True)
    print(f"2. Shard Probe (8.0s timeout)  : {{p2_pass}}/{{total}} ({{p2_pct:.2f}}%)", flush=True)
    print(f"3. MemoryBIO SNI ClientHello   : {{p3_pass}}/{{total}} ({{p3_pct:.2f}}%)", flush=True)
    print(f"4. Hardcoded Bytes (no SNI)    : {{p4_pass}}/{{total}} ({{p4_pct:.2f}}%)", flush=True)
    print("===============================================", flush=True)

if __name__ == '__main__':
    main()
'''

with open("kaggle/test_groundtruth/run.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Generated kaggle/test_groundtruth/run.py successfully!")
