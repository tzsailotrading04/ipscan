import socket
from concurrent.futures import ThreadPoolExecutor

def inspect_proxy(proxy):
    p_ip, p_port = proxy.strip().split(":")
    p_port = int(p_port)
    try:
        s = socket.create_connection((p_ip, p_port), timeout=3.0)
        s.sendall(b"CONNECT speed.cloudflare.com:443 HTTP/1.1\r\nHost: speed.cloudflare.com:443\r\n\r\n")
        resp = s.recv(1024)
        s.close()
        first_line = resp.split(b"\r\n")[0].decode(errors='ignore')
        headers = resp.decode(errors='ignore')
        is_real_tunnel = ("connection established" in headers.lower() or 
                          ("200" in first_line and "content-type" not in headers.lower() and "server: microsoft" not in headers.lower()))
        return proxy, is_real_tunnel, first_line, headers[:120].replace('\r\n', ' | ')
    except Exception as e:
        return proxy, False, type(e).__name__, str(e)[:40]

def main():
    with open(r"D:\DEpinFarm\work\traff_200_proxies.txt", "r") as f:
        proxies = [l.strip() for l in f if l.strip()]

    print("Auditing 200 proxies for REAL proxy tunnel vs FAKE web server...")
    with ThreadPoolExecutor(max_workers=50) as ex:
        results = list(ex.map(inspect_proxy, proxies))

    real_proxies = [p for p, is_real, _, _ in results if is_real]
    print(f"\nREAL PROXIES: {len(real_proxies)} / {len(proxies)} ({(len(real_proxies)/len(proxies))*100:.1f}%)")
    for p, is_real, fl, h in results[:20]:
        print(f"[{'REAL' if is_real else 'FAKE'}] {p}: {fl} || {h}")

if __name__ == "__main__":
    main()
