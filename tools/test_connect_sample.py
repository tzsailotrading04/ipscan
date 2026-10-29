import socket

def test_proxy(proxy_str):
    ip, port = proxy_str.split(":")
    port = int(port)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3.0)
    try:
        s.connect((ip, port))
        req = b"CONNECT 168.119.91.41:443 HTTP/1.1\r\nHost: 168.119.91.41:443\r\n\r\n"
        s.sendall(req)
        resp = s.recv(512)
        return resp.decode("utf-8", errors="ignore").split("\r\n")[0]
    except Exception as e:
        return str(e)
    finally:
        s.close()

with open("/mnt/d/DEpinFarm/work/traff_200_proxies.txt") as f:
    proxies = [line.strip() for line in f if line.strip()][:10]

for p in proxies:
    print(p, "->", test_proxy(p))
