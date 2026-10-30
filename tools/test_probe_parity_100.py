import glob, os, sys, time, socket, ssl
from concurrent.futures import ThreadPoolExecutor

REPO = r"D:\DEpinFarm"

# 1. Sample 100 fresh unique part-file entries
files = sorted(glob.glob(os.path.join(REPO, "ip", "harvest", "verified_alive_part_*.txt")), key=os.path.getmtime, reverse=True)
entries = []
seen = set()
for f in files:
    for line in open(f, encoding="utf-8", errors="ignore"):
        l = line.strip()
        if l and ":" in l:
            ep = l.split("\t")[0].split()[0]
            if ep not in seen:
                seen.add(ep)
                entries.append(l)
                if len(entries) >= 100:
                    break
    if len(entries) >= 100:
        break

print(f"Sampled {len(entries)} fresh unique part-file entries.")

# 2. Standalone probe
sys.path.insert(0, REPO)
from tools.pool_reverify import verify_proxy_worker as standalone_worker

# 3. Shard probe (imported/constructed identically to cl_shodan/run.py)
SSL_CTX = ssl.create_default_context()

def shard_sync_tls_handshake(sock, target, timeout=8.0):
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

def shard_sync_probe_target(ip, port, target, timeout=8.0):
    s = None
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        return shard_sync_tls_handshake(s, target, timeout=timeout)
    except Exception:
        if s:
            try: s.close()
            except Exception: pass
        return False

def shard_worker(entry):
    raw = entry.strip()
    ep = raw.split("\t")[0].split()[0]
    ip, port_s = ep.split(":")
    port = int(port_s)
    s = None
    try:
        s = socket.create_connection((ip, port), timeout=8.0)
    except Exception:
        return raw, False, "CONNECT_FAIL"

    if shard_sync_tls_handshake(s, "speed.cloudflare.com", timeout=8.0):
        return raw, True, "speed.cloudflare.com"

    for t in ["www.google.com", "one.one.one.one"]:
        if shard_sync_probe_target(ip, port, t, timeout=8.0):
            return raw, True, t
    return raw, False, "FAIL_TLS_OR_CONNECT"

print(f"Running 100 entries through Standalone Check (pool_reverify.py)...", flush=True)
with ThreadPoolExecutor(max_workers=50) as executor:
    st_results = list(executor.map(standalone_worker, entries))

print(f"Running 100 entries through Shard Check (cl_shodan/run.py)...", flush=True)
with ThreadPoolExecutor(max_workers=50) as executor:
    sh_results = list(executor.map(shard_worker, entries))

st_passed = sum(1 for _, ok, _ in st_results if ok)
sh_passed = sum(1 for _, ok, _ in sh_results if ok)

st_pct = (st_passed / len(entries)) * 100
sh_pct = (sh_passed / len(entries)) * 100
diff = abs(st_pct - sh_pct)

print("=" * 65)
print(f"STANDALONE CHECK SURVIVAL : {st_passed}/{len(entries)} ({st_pct:.1f}%)")
print(f"SHARD CHECK SURVIVAL      : {sh_passed}/{len(entries)} ({sh_pct:.1f}%)")
print(f"ABSOLUTE DIFFERENCE       : {diff:.1f}% (Required: within 10%)")
print("=" * 65)

if diff <= 10.0:
    print("PROBE_PARITY_PASSED: The shard probe and standalone probe match within 10%!")
else:
    print("PROBE_PARITY_FAILED: Difference exceeds 10%!")
    sys.exit(1)
