import os, re

REPO_ROOT = r"D:\DEpinFarm"

NEW_PROBE = '''    def sync_tls_handshake(sock, target, timeout=5.0):
        try:
            sock.setblocking(True)
            sock.settimeout(timeout)
            req = f"CONNECT {target}:443 HTTP/1.1\\r\\nHost: {target}:443\\r\\n\\r\\n".encode()
            sock.sendall(req)
            resp = b""
            while b"\\r\\n\\r\\n" not in resp:
                chunk = sock.recv(512)
                if not chunk: return False
                resp += chunk
                if len(resp) > 2048: return False
            first_line = resp.split(b"\\r\\n")[0]
            if not (b" 200" in first_line or b"HTTP/1.1 200" in first_line or b"HTTP/1.0 200" in first_line):
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

    def sync_probe_target(ip, port, target, timeout=5.0):
        s = None
        try:
            s = socket.create_connection((ip, port), timeout=timeout)
            return sync_tls_handshake(s, target, timeout=timeout)
        except Exception:
            if s:
                try: s.close()
                except Exception: pass
            return False

    async def check_port(ip, port):
        nonlocal STAT_ERRNO99, STAT_TIMEOUT, STAT_REFUSED, STAT_OTHER
        async with sem:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setblocking(False)
            try:
                await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=5.0)
            except asyncio.TimeoutError:
                STAT_TIMEOUT += 1
                try: s.close()
                except Exception: pass
                return None
            except ConnectionRefusedError:
                STAT_REFUSED += 1
                try: s.close()
                except Exception: pass
                return None
            except OSError as e:
                if getattr(e, "errno", None) == 99 or "cannot assign" in str(e).lower():
                    STAT_ERRNO99 += 1
                else:
                    STAT_OTHER += 1
                try: s.close()
                except Exception: pass
                return None
            except Exception:
                STAT_OTHER += 1
                try: s.close()
                except Exception: pass
                return None

            # Primary target probe with connected socket
            if await loop.run_in_executor(None, sync_tls_handshake, s, "speed.cloudflare.com", 5.0):
                return port, "speed.cloudflare.com"

            for t in ["www.google.com", "one.one.one.one"]:
                if await loop.run_in_executor(None, sync_probe_target, ip, port, t, 5.0):
                    return port, t
            return None'''

PROBE_PATTERN = re.compile(
    r"    def sync_tls_handshake\(.*?return None\n",
    re.DOTALL
)

count = 0
for idx in range(20):
    fpath = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{idx:02d}", "run.py")
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        new_content, n = PROBE_PATTERN.subn(NEW_PROBE + "\n", content, count=1)
        if n == 1:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(new_content)
            count += 1
            print(f"Updated cl_shodan_{idx:02d}/run.py")
        else:
            print(f"FAILED to match pattern in cl_shodan_{idx:02d}/run.py")

print(f"\nTotal files updated: {count}/20")
