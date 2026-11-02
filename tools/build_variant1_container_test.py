import os, json

with open("work/groundtruth.txt", "r", encoding="utf-8") as f:
    proxies = [l.strip() for l in f if l.strip()]

os.makedirs("kaggle/test_variant1_probe", exist_ok=True)

meta = {
    "id": "lalsangkima/test-variant1-probe",
    "title": "test-variant1-probe",
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
with open("kaggle/test_variant1_probe/kernel-metadata.json", "w", encoding="utf-8") as f:
    json.dump(meta, f, indent=2)

proxies_repr = repr(proxies)

code = f'''import socket
import ssl
import time
import concurrent.futures

TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
SSL_CTX = ssl.create_default_context()

PROXIES = {proxies_repr}

def sync_tls_handshake(sock, target, timeout=5.0):
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

def sync_probe_target(ip, port, target, timeout=5.0):
    s = None
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        return sync_tls_handshake(s, target, timeout=timeout)
    except Exception:
        if s:
            try: s.close()
            except Exception: pass
        return False

def probe_one(addr):
    ip, port_s = addr.split(":")
    port = int(port_s)
    # primary
    s = None
    try:
        s = socket.create_connection((ip, port), timeout=5.0)
        if sync_tls_handshake(s, TARGETS[0], timeout=5.0):
            return True
    except Exception:
        if s:
            try: s.close()
            except Exception: pass
    # fallbacks
    for t in TARGETS[1:]:
        if sync_probe_target(ip, port, t, timeout=5.0):
            return True
    return False

def main():
    total = len(PROXIES)
    print(f"Testing {{total}} groundtruth proxies with exact variant-1 probe...", flush=True)
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        results = list(ex.map(probe_one, PROXIES))
    dur = time.time() - t0
    passed = sum(results)
    pct = (passed / total) * 100.0
    print(f"\\n================ GROUNDTRUTH TEST RESULT ================", flush=True)
    print(f"Total Proxies Tested : {{total}}", flush=True)
    print(f"Passed               : {{passed}}", flush=True)
    print(f"Percentage           : {{pct:.2f}}%", flush=True)
    print(f"Duration             : {{dur:.1f}}s", flush=True)
    print(f"=========================================================", flush=True)

if __name__ == "__main__":
    main()
'''

with open("kaggle/test_variant1_probe/run.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Generated kaggle/test_variant1_probe files successfully.")
