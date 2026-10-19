import asyncio, socket, ssl, os, sys, time, ipaddress, urllib.request

ROOT  = r"D:\DEpinFarm"
SRC   = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "ip", "scan18.txt")
CONC  = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
REALF = os.environ.get("REALF", os.path.join(ROOT, "ip", "real.txt"))
DEADF = os.environ.get("DEADF", os.path.join(ROOT, "ip", "dead3.txt"))
DONEF = os.environ.get("DONEF", os.path.join(ROOT, "ip", "done3.txt"))
TIO   = 4.0

TARGETS = [("1.1.1.1", "/cdn-cgi/trace"), ("checkip.amazonaws.com", "/")]
TLS = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
TLS.check_hostname = False
TLS.verify_mode = ssl.CERT_NONE

def is_lit(h):
    try:
        ipaddress.ip_address(h)
        return True
    except Exception:
        return False

def my_ip():
    for u in ("https://checkip.amazonaws.com", "https://api.ipify.org"):
        try:
            with urllib.request.urlopen(u, timeout=6) as r:
                return r.read().decode().strip()
        except Exception:
            pass
    return "0.0.0.0"

OWN = my_ip()
HOSTIP = {h: (h if is_lit(h) else socket.gethostbyname(h)) for h, _ in TARGETS}
print("own ip:", OWN, "| targets:", TARGETS, flush=True)

def find_ip(buf):
    if not buf:
        return None
    txt = buf.decode("latin-1").replace("\r", " ").replace("\n", " ").replace("<", " ").replace(">", " ")
    for tok in txt.split():
        t = tok.strip(".,;:\"'()[]{}")
        try:
            a = ipaddress.ip_address(t)
            if a.is_global and str(a) != OWN:
                return str(a)
        except Exception:
            pass
    return None

async def read_some(r, limit=8192, stop=None):
    out = b""
    try:
        while len(out) < limit:
            b = await asyncio.wait_for(r.read(4096), TIO)
            if not b:
                break
            out += b
            if stop and stop in out:
                break
    except Exception:
        pass
    return out

async def socks5_hs(r, w, host, port):
    w.write(b"\x05\x01\x00")
    await w.drain()
    d = await asyncio.wait_for(r.readexactly(2), TIO)
    if d[1] != 0:
        return False
    if is_lit(host):
        addr = b"\x01" + socket.inet_aton(host)
    else:
        hb = host.encode()
        addr = b"\x03" + bytes([len(hb)]) + hb
    w.write(b"\x05\x01\x00" + addr + port.to_bytes(2, "big"))
    await w.drain()
    h = await asyncio.wait_for(r.readexactly(4), TIO)
    if h[1] != 0:
        return False
    if h[3] == 1:
        await asyncio.wait_for(r.readexactly(6), TIO)
    elif h[3] == 3:
        n = (await asyncio.wait_for(r.readexactly(1), TIO))[0]
        await asyncio.wait_for(r.readexactly(n + 2), TIO)
    elif h[3] == 4:
        await asyncio.wait_for(r.readexactly(18), TIO)
    return True

async def socks4_hs(r, w, host, port):
    w.write(b"\x04\x01" + port.to_bytes(2, "big") + socket.inet_aton(HOSTIP[host]) + b"\x00")
    await w.drain()
    d = await asyncio.wait_for(r.readexactly(8), TIO)
    return d[1] == 0x5a

async def attempt(ip, port, proto, host, path, tls):
    r = w = None
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(ip, port), TIO)
        tp = 443 if tls else 80
        if proto == "socks5":
            if not await socks5_hs(r, w, host, tp):
                return None
        elif proto == "socks4":
            if not await socks4_hs(r, w, host, tp):
                return None
        elif tls:
            w.write(("CONNECT %s:%d HTTP/1.1\r\nHost: %s:%d\r\nUser-Agent: curl/7.88.1\r\n\r\n" % (host, tp, host, tp)).encode())
            await w.drain()
            head = await read_some(r, 1024, b"\r\n\r\n")
            if not head.startswith(b"HTTP/") or b" 200" not in head.split(b"\r\n")[0]:
                return None
        if tls:
            loop = asyncio.get_running_loop()
            tr = w.transport
            new = await loop.start_tls(tr, tr.get_protocol(), TLS, server_hostname=host)
            tr.get_protocol()._transport = new
            r._transport = new
            w._transport = new
        if proto == "http" and not tls:
            req = "GET http://%s%s HTTP/1.1\r\nHost: %s\r\nUser-Agent: curl/7.88.1\r\nAccept: */*\r\nConnection: close\r\n\r\n" % (host, path, host)
        else:
            req = "GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: curl/7.88.1\r\nAccept: */*\r\nConnection: close\r\n\r\n" % (path, host)
        w.write(req.encode())
        await w.drain()
        return find_ip(await read_some(r))
    except Exception:
        return None
    finally:
        try:
            w.close()
        except Exception:
            pass

async def test(line):
    try:
        ip, ps, proto = line.split(":")
        port = int(ps)
    except Exception:
        return None
    if proto not in ("http", "socks5", "socks4"):
        proto = "http"
    other = [p for p in ("http", "socks5", "socks4") if p != proto][0]
    plan = [(TARGETS[0], proto, False), (TARGETS[0], other, False),
            (TARGETS[0], proto, True), (TARGETS[1], proto, False)]
    for (host, path), p, tls in plan:
        if await attempt(ip, port, p, host, path, tls):
            return "%s:%d:%s" % (ip, port, p)
    return None

async def main():
    done, real = set(), set()
    if os.path.exists(DONEF):
        with open(DONEF, encoding="utf-8", errors="ignore") as f:
            for l in f:
                done.add(l.strip())
    if os.path.exists(REALF):
        with open(REALF, encoding="utf-8", errors="ignore") as f:
            for l in f:
                if l.strip():
                    real.add(l.strip())
    lines = []
    with open(SRC, encoding="utf-8", errors="ignore") as f:
        for l in f:
            l = l.strip()
            if l and l not in done and l not in real:
                lines.append(l)
    total = len(lines)
    print("to test:", total, "| concurrency:", CONC, flush=True)
    if not total:
        return
    asyncio.get_running_loop().set_exception_handler(lambda l, c: None)
    q, resq = asyncio.Queue(maxsize=50000), asyncio.Queue()
    rf = open(REALF, "a", encoding="utf-8")
    df = open(DEADF, "a", encoding="utf-8")
    dnf = open(DONEF, "a", encoding="utf-8")
    t0 = time.time()
    state = {"n": 0, "f": 0}

    async def worker():
        while True:
            l = await q.get()
            if l is None:
                return
            try:
                r = await test(l)
            except Exception:
                r = None
            await resq.put((l, r))

    async def feeder():
        for l in lines:
            await q.put(l)
        for _ in range(CONC):
            await q.put(None)

    async def consumer():
        while state["n"] < total:
            l, r = await resq.get()
            state["n"] += 1
            dnf.write(l + "\n")
            if r:
                state["f"] += 1
                rf.write(r + "\n")
                if state["f"] % 20 == 0:
                    rf.flush()
            else:
                df.write(l + "\n")
            if state["n"] % 1000 == 0:
                el = time.time() - t0
                print("tested %d/%d | REAL %d | %.0f/s | %.3f%%" % (state["n"], total, state["f"], state["n"] / el, 100.0 * state["f"] / state["n"]), flush=True)
                dnf.flush(); df.flush(); rf.flush()

    await asyncio.gather(feeder(), consumer(), *[worker() for _ in range(CONC)])
    el = time.time() - t0
    print("DONE tested %d REAL %d in %.0fs (%.3f%%)" % (state["n"], state["f"], el, 100.0 * state["f"] / max(state["n"], 1)), flush=True)
    dnf.flush(); df.flush(); rf.flush()

if __name__ == "__main__":
    asyncio.run(main())