import socket
import ssl
from concurrent.futures import ThreadPoolExecutor

ssl_ctx = ssl.create_default_context()

def probe_strict(endpoint, target="speed.cloudflare.com", timeout=4.0):
    try:
        ip, port_s = endpoint.split(":", 1)
        port = int(port_s)
    except Exception:
        return endpoint, False, "BAD_FMT"

    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        req = f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n".encode()
        s.sendall(req)
        s.settimeout(timeout)
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = s.recv(512)
            if not chunk:
                break
            resp += chunk
            if len(resp) > 4096:
                break
                
        first_line = resp.split(b"\r\n")[0]
        if not (b" 200" in first_line or b"HTTP/1.1 200" in first_line or b"HTTP/1.0 200" in first_line):
            s.close()
            return endpoint, False, f"CONNECT_REJECTED_{first_line.decode(errors='ignore')[:30]}"
            
        # Complete full TLS handshake and validate against System CA store
        ss = ssl_ctx.wrap_socket(s, server_hostname=target)
        ss.settimeout(timeout)
        ss.do_handshake()
        cert = ss.getpeercert()
        ss.close()
        return endpoint, True, "TLS_VALIDATED"
    except ssl.SSLCertVerificationError as e:
        return endpoint, False, f"CERT_VALIDATION_FAIL: {e.verify_message}"
    except (socket.timeout, TimeoutError):
        return endpoint, False, "TIMEOUT"
    except ConnectionRefusedError:
        return endpoint, False, "CONN_REFUSED"
    except ConnectionResetError:
        return endpoint, False, "CONN_RESET"
    except Exception as e:
        return endpoint, False, f"OTHER_FAIL_{type(e).__name__}"

if __name__ == "__main__":
    with open(r"D:\DEpinFarm\ip\harvest\real_pool.txt", "r", encoding="utf-8") as f:
        sample = [l.strip().split("\t")[0] for l in f if "DATACENTER" in l][:30]

    with ThreadPoolExecutor(max_workers=15) as ex:
        for ep, ok, reason in ex.map(probe_strict, sample):
            print(f"[{'PASS' if ok else 'FAIL'}] {ep} -> {reason}")
