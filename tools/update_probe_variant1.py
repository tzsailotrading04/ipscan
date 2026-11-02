import os

REPO_ROOT = r"D:\DEpinFarm"

NEW_PROBE_BLOCK = '''    def sync_tls_handshake(sock, target, timeout=5.0):
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
            return None

'''

START_PREFIX = "    def sync_tls_handshake(sock, target, timeout="
END_MARKER = "    BATCH_SIZE = 500"

updated = 0
for idx in range(20):
    fpath = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{idx:02d}", "run.py")
    if not os.path.exists(fpath):
        print(f"Missing {fpath}")
        continue
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    
    start_pos = content.find(START_PREFIX)
    if start_pos == -1:
        print(f"Could not find start marker in cl_shodan_{idx:02d}")
        continue
    end_pos = content.find(END_MARKER, start_pos)
    if end_pos == -1:
        print(f"Could not find end marker in cl_shodan_{idx:02d}")
        continue
    
    new_content = content[:start_pos] + NEW_PROBE_BLOCK + content[end_pos:]
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(new_content)
    updated += 1
    print(f"Updated cl_shodan_{idx:02d}/run.py successfully")

print(f"\nTotal updated: {updated}/20")
