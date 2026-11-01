import os, sys, ssl, time, socket, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
SSL_CTX = ssl.create_default_context()

def hs(sock, target, timeout=8.0):
    try:
        sock.setblocking(True)
        sock.settimeout(timeout)
        sock.sendall(f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n".encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            ch = sock.recv(512)
            if not ch:
                return False
            resp += ch
            if len(resp) > 2048:
                return False
        first = resp.split(b"\r\n")[0]
        if not (b" 200" in first or b"HTTP/1.1 200" in first or b"HTTP/1.0 200" in first):
            return False
        ss = SSL_CTX.wrap_socket(sock, server_hostname=target)
        ss.settimeout(timeout)
        ss.do_handshake()
        c = ss.getpeercert()
        ss.close()
        return bool(c)
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        return False

def one(ip, port, timeout=8.0):
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
    except Exception:
        return ip, port, False, None
    if hs(s, TARGETS[0], timeout):
        return ip, port, True, TARGETS[0]
    for t in TARGETS[1:]:
        try:
            s2 = socket.create_connection((ip, port), timeout=timeout)
            if hs(s2, t, timeout):
                return ip, port, True, t
        except Exception:
            pass
    return ip, port, False, None

ap = argparse.ArgumentParser()
ap.add_argument("--input", required=True)
ap.add_argument("--pool", default="ip/harvest/real_pool.txt")
ap.add_argument("--out-alive", default="ip/harvest/verified_alive_part_local.txt")
ap.add_argument("--out-dead", default="cache/pool_dead.txt")
ap.add_argument("--workers", type=int, default=200)
ap.add_argument("--timeout", type=float, default=8.0)
a = ap.parse_args()

pool = set()
if os.path.exists(a.pool):
    with open(a.pool, encoding="utf-8", errors="ignore") as f:
        for l in f:
            if l.strip():
                pool.add(l.strip().split("\t")[0].split()[0])

cands = []
seen = set()
with open(a.input, encoding="utf-8", errors="ignore") as f:
    for l in f:
        ep = l.strip().split("\t")[0].split()[0] if l.strip() else ""
        if not ep or ep in pool or ep in seen:
            continue
        p = ep.split(":")
        if len(p) == 2 and p[1].isdigit():
            cands.append((p[0], int(p[1])))
            seen.add(ep)

print("to verify:", len(cands))
if not cands:
    sys.exit()

os.makedirs(os.path.dirname(a.out_alive), exist_ok=True)
ok = 0
t0 = time.time()
with ThreadPoolExecutor(max_workers=a.workers) as ex:
    futs = [ex.submit(one, ip, pt, a.timeout) for ip, pt in cands]
    for fu in as_completed(futs):
        ip, pt, good, tgt = fu.result()
        if good:
            ok += 1
            with open(a.out_alive, "a", encoding="utf-8") as af:
                af.write(f"{ip}:{pt}\t{tgt}\tLOCAL\t0\tUNKNOWN\n")
            print("ALIVE", ip, pt)
        else:
            with open(a.out_dead, "a", encoding="utf-8") as df:
                df.write(f"{ip}:{pt}\tspeed.cloudflare.com\tLOCAL\tREASON:FAIL_CONNECT\tRETIRED\n")
print(f"done in {time.time()-t0:.1f}s: {ok} alive of {len(cands)}")
