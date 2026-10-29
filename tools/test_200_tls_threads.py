import socket
import ssl
from concurrent.futures import ThreadPoolExecutor

def test_proxy(proxy):
    p_ip, p_port = proxy.strip().split(":")
    p_port = int(p_port)
    target = "blnc.traffmonetizer.com"
    port = 443
    try:
        s = socket.create_connection((p_ip, p_port), timeout=4.0)
        req = f"CONNECT {target}:{port} HTTP/1.1\r\nHost: {target}:{port}\r\n\r\n".encode()
        s.sendall(req)
        s.settimeout(4.0)
        resp = s.recv(1024)
        if not (b" 200" in resp):
            s.close()
            return proxy, False, f"CONNECT_REJECTED_{resp[:30]}"
            
        # Wrap SSL
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ss = ctx.wrap_socket(s, server_hostname=target)
        ss.settimeout(4.0)
        ss.do_handshake()
        ss.close()
        return proxy, True, "TLS_OK"
    except Exception as e:
        return proxy, False, f"{type(e).__name__}: {str(e)[:40]}"

def main():
    with open(r"D:\DEpinFarm\work\traff_200_proxies.txt", "r") as f:
        proxies = [l.strip() for l in f if l.strip()]

    print(f"Testing TLS Handshake for 200 proxies with ThreadPool...")
    with ThreadPoolExecutor(max_workers=50) as ex:
        results = list(ex.map(test_proxy, proxies))

    ok = [p for p, success, _ in results if success]
    print(f"\nREAL TLS SUCCESS: {len(ok)} / {len(proxies)} ({(len(ok)/len(proxies))*100:.1f}%)")
    for p, success, reason in results[:25]:
        print(f"  {p}: {'PASS' if success else 'FAIL'} ({reason})")

if __name__ == "__main__":
    main()
