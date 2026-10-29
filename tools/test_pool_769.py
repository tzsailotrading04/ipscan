import socket
from concurrent.futures import ThreadPoolExecutor

def test_proxy_769(proxy_str):
    ip, port = proxy_str.split(":")
    port = int(port)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3.0)
    try:
        s.connect((ip, port))
        req = b"CONNECT 67.213.124.163:769 HTTP/1.1\r\nHost: 67.213.124.163:769\r\n\r\n"
        s.sendall(req)
        resp = s.recv(256)
        first_line = resp.decode("utf-8", errors="ignore").split("\r\n")[0]
        if "200" in first_line:
            return proxy_str, True, first_line
        else:
            return proxy_str, False, first_line
    except Exception as e:
        return proxy_str, False, str(e)
    finally:
        s.close()

with open("/mnt/d/DEpinFarm/work/traff_200_proxies.txt") as f:
    proxies = [line.strip() for line in f if line.strip()]

print(f"Testing {len(proxies)} proxies against Traffmonetizer port 769...")
passed = []
with ThreadPoolExecutor(max_workers=30) as pool:
    for proxy_str, ok, res in pool.map(test_proxy_769, proxies):
        if ok:
            passed.append((proxy_str, res))
            print(f"[PASS] {proxy_str} -> {res}")

print(f"Total passed port 769: {len(passed)} / {len(proxies)}")
