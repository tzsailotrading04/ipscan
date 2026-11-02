import socket
import ssl
import time
import concurrent.futures

PROXIES = ['193.181.35.133:8118', '45.90.32.134:3128', '144.124.251.24:10157', '144.124.251.24:10106', '144.124.251.24:10492', '144.124.251.24:10539', '144.124.251.24:10167', '144.124.251.24:10814', '144.124.251.24:10347', '144.124.251.24:10816', '144.124.251.24:10088', '144.124.251.24:10771', '34.105.252.3:3128', '144.124.251.24:10749', '144.124.251.24:10351', '144.124.251.24:10009', '144.124.251.24:10101', '144.124.251.24:10449', '144.124.251.24:10082', '144.124.251.24:10448', '144.124.251.24:10877', '144.124.251.24:10230', '176.111.37.5:39811', '144.124.251.24:10279', '144.124.251.24:10590', '178.207.12.86:3128', '144.124.251.24:10008', '176.111.37.216:39811', '144.124.251.24:10051', '144.124.251.24:10744', '144.124.251.24:10469', '144.124.251.24:11491', '144.124.251.24:10064', '144.124.251.24:11280', '144.124.251.24:10809', '144.124.251.24:11403', '144.124.251.24:10601', '144.124.251.24:10522', '144.124.251.24:10803', '144.124.251.24:10250', '144.124.251.24:11274', '144.124.251.24:10091', '144.124.251.24:10649', '145.220.227.132:3128', '144.124.251.24:10187', '134.209.29.120:3128', '144.124.251.24:10646', '37.187.109.70:10111', '45.13.185.217:3128', '144.124.251.24:10261', '144.124.251.24:10366', '144.124.251.24:11198', '144.124.251.24:10412', '144.124.251.24:10802', '144.124.251.24:10628', '144.124.251.24:10154', '144.124.251.24:10346', '144.124.251.24:10123', '144.124.251.24:11108', '144.124.251.24:10001', '144.124.251.24:10453', '144.124.251.24:10953', '83.171.113.43:3128', '161.35.70.249:3128', '81.90.158.110:3128', '213.148.15.230:8081', '144.124.251.24:10002', '144.124.251.24:10509', '94.251.4.170:3128', '144.124.251.24:10404', '212.227.182.100:110', '144.124.251.24:10431', '18.157.159.247:33914', '167.99.8.113:8013', '212.77.75.25:3129', '185.129.213.210:8080', '144.124.251.24:10471', '167.99.3.26:10563', '198.199.86.11:3128', '144.124.251.24:11450', '34.43.46.91:443', '161.49.84.3:8081', '149.104.24.86:40001', '45.194.41.141:8080', '45.194.41.16:8080', '212.200.223.89:8080', '188.136.172.1:8080', '43.129.66.216:59394', '203.205.49.2:10193', '43.161.254.16:3128', '159.203.61.169:3128', '154.201.126.44:8080', '43.161.220.143:443', '175.106.15.186:8080', '103.31.235.205:8085', '160.22.24.74:8082', '202.150.89.245:3128', '130.110.103.245:3128', '14.224.168.18:8080', '103.161.1.114:1111', '103.144.54.35:8082', '138.68.60.8:3128', '103.167.171.151:8097', '160.22.217.93:8082', '128.199.202.122:3128', '128.199.113.85:9090', '165.22.99.36:8008', '103.175.202.138:8090', '51.94.221.175:18280', '103.164.55.81:3128', '149.130.173.58:9443', '154.26.132.129:3128', '103.122.1.130:8181', '128.199.121.61:9090', '152.42.177.32:8888', '103.194.47.53:8082', '103.175.236.180:8382', '102.209.191.10:8080', '195.142.250.41:8080', '34.43.46.91:80', '4.144.146.21:80', '45.189.57.114:3129', '103.170.96.192:8181', '101.255.119.26:8080', '165.22.99.36:8018', '196.251.222.170:1080', '152.42.170.187:9090', '115.85.88.18:8080', '160.19.17.43:8181', '103.170.185.162:46', '14.175.56.22:20106', '144.124.251.24:11377', '103.148.83.110:8889', '43.99.60.244:8089', '146.190.80.158:9090', '139.59.1.14:3128', '107.174.80.186:3128', '188.132.150.51:8080', '45.194.90.194:8080', '200.59.186.142:999', '139.162.78.109:3128', '47.86.97.230:18080', '185.142.156.203:80', '45.194.90.184:8080', '102.68.78.175:8080', '104.161.23.122:5011', '45.194.90.225:8080', '160.22.137.10:1080', '112.211.84.86:8585', '154.19.38.195:1111', '103.188.169.170:8080', '18.170.45.5:29907', '89.251.21.134:8080', '144.124.251.24:10766', '110.74.195.34:25', '103.227.186.209:6080', '103.157.78.117:7777', '14.143.222.113:57748', '103.175.228.57:3127', '103.176.96.228:8082', '222.127.54.16:8080', '187.189.175.136:999', '87.106.70.153:8118', '1.14.150.71:8888', '103.179.253.43:8181', '175.158.40.224:1616', '160.187.174.249:80', '81.162.60.120:8080', '16.52.81.236:45573', '103.55.225.54:8080', '43.155.62.157:443', '103.195.142.250:8180', '213.176.74.119:1080', '122.246.4.30:17981', '15.223.187.219:8689', '88.146.222.250:8000', '190.0.246.210:4040', '93.118.120.60:8080', '103.106.219.171:8081', '56.112.92.32:55755', '45.172.223.190:999', '45.226.227.217:999', '194.182.187.78:3128', '185.109.244.69:8080', '37.191.76.218:7060', '185.238.238.49:58080', '152.70.198.2:1080', '47.101.185.64:3128', '45.229.16.34:999', '128.201.29.6:8666', '45.198.32.207:8080', '8.163.24.236:8080', '103.199.86.82:8080', '187.102.219.64:999', '116.62.202.70:17900', '116.204.166.148:8080', '114.55.168.172:8080', '193.33.157.2:8080', '144.124.251.24:10813', '58.69.182.53:8085']
TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
SSL_CTX = ssl.create_default_context()

# Precompute MemoryBIO ClientHellos with exact SNI
CLIENT_HELLOS = {}
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
    b"\x16\x03\x01\x00\xba\x01\x00\x00\xb6\x03\x03"
    b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f"
    b"\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f"
    b"\x00\x00 \x13\x01\x13\x02\x13\x03\xc0+\xc0/\xcc\xa9\xcc\xa8"
    b"\xc0,\xc00\xc0\n\xc0\t\xc0\x13\xc0\x14\x00\x9c\x00\x9d\x00/\x005"
    b"\x01\x00\x00m\x00\x17\x00\x00\xff\x01\x00\x01\x00\x00\n\x00\x0e"
    b"\x00\x0c\x00\x1d\x00\x17\x00\x18\x00\x19\x01\x00\x01\x01\x00\x0b"
    b"\x00\x02\x01\x00\x00#\x00\x00\x00\x10\x00\x0e\x00\x0c\x02h2\x08http/1.1"
)

# -------------------------------------------------------------
# 1. Shard Probe (exact run.py logic)
# -------------------------------------------------------------
def sync_tls_handshake(sock, target, timeout):
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
            req = f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n".encode()
            s.sendall(req)
            resp = b""
            while b"\r\n\r\n" not in resp:
                chunk = s.recv(512)
                if not chunk: break
                resp += chunk
                if len(resp) > 2048: break
            first_line = resp.split(b"\r\n")[0]
            if not (b" 200" in first_line or b"HTTP/1.1 200" in first_line or b"HTTP/1.0 200" in first_line):
                s.close()
                continue
            parts = resp.split(b"\r\n\r\n", 1)
            trailing = parts[1] if len(parts) > 1 else b""
            if trailing:
                if trailing[:1] == b"\x16":
                    s.close()
                    return True
                s.close()
                continue
            # Send MemoryBIO ClientHello carrying exact SNI for target
            s.sendall(CLIENT_HELLOS[target])
            b1 = s.recv(1)
            s.close()
            if b1 == b"\x16":
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
            req = f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n".encode()
            s.sendall(req)
            resp = b""
            while b"\r\n\r\n" not in resp:
                chunk = s.recv(512)
                if not chunk: break
                resp += chunk
                if len(resp) > 2048: break
            first_line = resp.split(b"\r\n")[0]
            if not (b" 200" in first_line or b"HTTP/1.1 200" in first_line or b"HTTP/1.0 200" in first_line):
                s.close()
                continue
            parts = resp.split(b"\r\n\r\n", 1)
            trailing = parts[1] if len(parts) > 1 else b""
            if trailing:
                if trailing[:1] == b"\x16":
                    s.close()
                    return True
                s.close()
                continue
            # Send hardcoded bytes without target SNI
            s.sendall(HARDCODED_CLIENT_HELLO)
            b1 = s.recv(1)
            s.close()
            if b1 == b"\x16":
                return True
        except Exception:
            if s:
                try: s.close()
                except Exception: pass
    return False

def main():
    total = len(PROXIES)
    print(f"Starting Groundtruth Evaluation on {total} proxies from Kaggle container...", flush=True)

    # 1. Exact shard probe (baseline 5.0s timeout)
    print("\n--- 1. Running exact shard probe (5.0s timeout) ---", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        res1 = list(ex.map(lambda p: probe_shard_style(p, timeout=5.0), PROXIES))
    p1_pass = sum(res1)
    p1_pct = (p1_pass / total) * 100.0
    print(f"Shard Probe (5.0s): {p1_pass}/{total} passed ({p1_pct:.2f}%)", flush=True)

    # 2. Exact shard probe with 8.0s timeout
    print("\n--- 2. Running shard probe with 8-second timeout ---", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        res2 = list(ex.map(lambda p: probe_shard_style(p, timeout=8.0), PROXIES))
    p2_pass = sum(res2)
    p2_pct = (p2_pass / total) * 100.0
    print(f"Shard Probe (8.0s): {p2_pass}/{total} passed ({p2_pct:.2f}%)", flush=True)

    # 3. ClientHello via ssl.MemoryBIO with correct SNI (8.0s timeout)
    print("\n--- 3. Running ClientHello via ssl.MemoryBIO with correct SNI (8.0s timeout) ---", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        res3 = list(ex.map(lambda p: probe_memorybio_sni(p, timeout=8.0), PROXIES))
    p3_pass = sum(res3)
    p3_pct = (p3_pass / total) * 100.0
    print(f"MemoryBIO with SNI (8.0s): {p3_pass}/{total} passed ({p3_pct:.2f}%)", flush=True)

    # 4. Hardcoded bytes comparison
    print("\n--- 4. Reference: Hardcoded bytes without correct SNI (8.0s timeout) ---", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        res4 = list(ex.map(lambda p: probe_hardcoded_bytes(p, timeout=8.0), PROXIES))
    p4_pass = sum(res4)
    p4_pct = (p4_pass / total) * 100.0
    print(f"Hardcoded bytes (8.0s): {p4_pass}/{total} passed ({p4_pct:.2f}%)", flush=True)

    print("\n================ FINAL SUMMARY ================", flush=True)
    print(f"Total Groundtruth Tested      : {total}", flush=True)
    print(f"1. Shard Probe (5.0s)          : {p1_pass}/{total} ({p1_pct:.2f}%)", flush=True)
    print(f"2. Shard Probe (8.0s timeout)  : {p2_pass}/{total} ({p2_pct:.2f}%)", flush=True)
    print(f"3. MemoryBIO SNI ClientHello   : {p3_pass}/{total} ({p3_pct:.2f}%)", flush=True)
    print(f"4. Hardcoded Bytes (no SNI)    : {p4_pass}/{total} ({p4_pct:.2f}%)", flush=True)
    print("===============================================", flush=True)

if __name__ == '__main__':
    main()
