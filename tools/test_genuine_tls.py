import socket
import ssl
from concurrent.futures import ThreadPoolExecutor

def test_genuine_proxy(proxy):
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
            return proxy, False, f"CONNECT_REJECTED"
            
        # Wrap SSL with REAL STRICT CA VERIFICATION!
        ctx = ssl.create_default_context()
        # Default context has verify_mode = CERT_REQUIRED and check_hostname = True
        ss = ctx.wrap_socket(s, server_hostname=target)
        ss.settimeout(4.0)
        ss.do_handshake()
        cert = ss.getpeercert()
        ss.close()
        subject = dict(x[0] for x in cert.get('subject', []))
        common_name = subject.get('commonName', '')
        return proxy, True, f"GENUINE_TLS_OK (CN={common_name})"
    except ssl.SSLCertVerificationError as e:
        return proxy, False, f"MITM_SELF_SIGNED: {e.verify_message}"
    except Exception as e:
        return proxy, False, f"{type(e).__name__}: {str(e)[:40]}"

def main():
    with open(r"D:\DEpinFarm\work\traff_200_proxies.txt", "r") as f:
        proxies = [l.strip() for l in f if l.strip()]

    print("Auditing 200 proxies for GENUINE TLS pass-through (Strict CA Verification)...")
    with ThreadPoolExecutor(max_workers=50) as ex:
        results = list(ex.map(test_genuine_proxy, proxies))

    ok = [p for p, success, _ in results if success]
    print(f"\nGENUINE TLS PROXIES: {len(ok)} / {len(proxies)} ({(len(ok)/len(proxies))*100:.1f}%)")
    for p, success, reason in results[:25]:
        print(f"  [{'PASS' if success else 'FAIL'}] {p}: {reason}")

if __name__ == "__main__":
    main()
