import os
import re

ROOT = r"D:\DEpinFarm"

# 1. Update all 21 shard files
shard_files = [os.path.join(ROOT, "kaggle", "cl_shodan", "run.py")] + [
    os.path.join(ROOT, "kaggle", f"cl_shodan_{i:02d}", "run.py") for i in range(20)
]

new_build_pool = """async def build_pool(items):
    pool = []
    fail_counts = {"connect_error": 0, "timeout": 0, "bad_status": 0, "other": 0}
    sem = asyncio.Semaphore(600)
    async with aiohttp.ClientSession(headers=HEADERS) as shared:
        async def v(item):
            addr, proto = item
            last_err = None
            async with sem:
                if proto == "socks5":
                    if not HAVE_SOCKS:
                        fail_counts["other"] += 1
                        return
                    for _ in range(2):
                        try:
                            conn = ProxyConnector.from_url(f"socks5://{addr}")
                            async with aiohttp.ClientSession(headers=HEADERS, connector=conn) as s:
                                async with s.get(BASE + rand_ip(), timeout=5) as r:
                                    if r.status < 500 and r.status != 407:
                                        pool.append((addr, "socks5"))
                                        return
                                    else:
                                        last_err = "bad_status"
                        except asyncio.TimeoutError:
                            last_err = "timeout"
                        except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError,
                                aiohttp.ClientProxyConnectionError, ConnectionError, OSError):
                            last_err = "connect_error"
                        except Exception:
                            last_err = "other"
                else:
                    # proto == "http"
                    http_ok = False
                    for _ in range(2):
                        try:
                            async with shared.get(BASE + rand_ip(), proxy=f"http://{addr}", timeout=5) as r:
                                if r.status < 500 and r.status != 407:
                                    pool.append((addr, "http"))
                                    http_ok = True
                                    return
                                else:
                                    last_err = "bad_status"
                        except asyncio.TimeoutError:
                            last_err = "timeout"
                        except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError,
                                aiohttp.ClientProxyConnectionError, ConnectionError, OSError):
                            last_err = "connect_error"
                        except Exception:
                            last_err = "other"
                    # If http failed, try one socks5 attempt before discarding
                    if not http_ok and HAVE_SOCKS:
                        try:
                            conn = ProxyConnector.from_url(f"socks5://{addr}")
                            async with aiohttp.ClientSession(headers=HEADERS, connector=conn) as s:
                                async with s.get(BASE + rand_ip(), timeout=5) as r:
                                    if r.status < 500 and r.status != 407:
                                        pool.append((addr, "socks5"))
                                        return
                                    else:
                                        last_err = "bad_status"
                        except asyncio.TimeoutError:
                            last_err = "timeout"
                        except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError,
                                aiohttp.ClientProxyConnectionError, ConnectionError, OSError):
                            last_err = "connect_error"
                        except Exception:
                            last_err = "other"
            if last_err:
                fail_counts[last_err] += 1

        await asyncio.gather(*[v(i) for i in items], return_exceptions=True)
    log(f"[build_pool_fails] tested={len(items)} passed={len(pool)} connect_error={fail_counts['connect_error']} timeout={fail_counts['timeout']} bad_status={fail_counts['bad_status']} other={fail_counts['other']}")
    return pool"""

old_build_pool_pattern = re.compile(r"async def build_pool\(items\):[\s\S]*?return pool")

for sf in shard_files:
    with open(sf, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(r'ENGINE_VER\s*=\s*"v98\.\d+"', 'ENGINE_VER = "v98.147"', content)

    content, n = old_build_pool_pattern.subn(new_build_pool, content)
    if n != 1:
        print(f"Warning: build_pool replaced {n} times in {sf}")

    with open(sf, "w", encoding="utf-8") as f:
        f.write(content)

print(f"Updated {len(shard_files)} shard files.")

# 2. Update all 10 verifier files
verifier_files = [os.path.join(ROOT, "kaggle", "cl_verify", "run.py")] + [
    os.path.join(ROOT, "kaggle", f"cl_verify_{i}", "run.py") for i in range(9)
]

new_verify_funcs = """def try_http(ip, port):
    try:
        s = socket.create_connection((ip, port), TIMEOUT)
        s.settimeout(TIMEOUT)
        s.sendall(f"CONNECT {HOST}:443 HTTP/1.1\\r\\nHost: {HOST}:443\\r\\n\\r\\n".encode())
        resp = b""
        while b"\\r\\n\\r\\n" not in resp:
            c = s.recv(256)
            if not c:
                break
            resp += c
        first_line = resp.split(b"\\r\\n")[0]
        if not (resp.startswith(b"HTTP/") and (b" 200" in first_line or b" 2" in first_line)):
            s.close()
            return False

        tls_s = SSL_CTX.wrap_socket(s, server_hostname=HOST)
        tls_s.settimeout(TIMEOUT)
        tls_s.sendall(f"GET /1.1.1.1 HTTP/1.1\\r\\nHost: {HOST}\\r\\nConnection: close\\r\\n\\r\\n".encode())
        body = b""
        while True:
            c = tls_s.recv(256)
            if not c:
                break
            body += c
        tls_s.close()
        if b"\\r\\n\\r\\n" in body:
            header, _ = body.split(b"\\r\\n\\r\\n", 1)
            status_line = header.split(b"\\r\\n")[0]
            if status_line.startswith(b"HTTP/") and not any(status_line.startswith(p) for p in (b"HTTP/1.1 5", b"HTTP/1.0 5", b"HTTP/1.1 407", b"HTTP/1.0 407")):
                return True
        return False
    except Exception:
        return False

def try_socks5(ip, port):
    try:
        s = socket.create_connection((ip, port), TIMEOUT)
        s.settimeout(TIMEOUT)
        s.sendall(b"\\x05\\x01\\x00")
        greet = s.recv(2)
        if greet != b"\\x05\\x00":
            s.close()
            return False
        h = HOST.encode()
        s.sendall(b"\\x05\\x01\\x00\\x03" + bytes([len(h)]) + h + struct.pack(">H", 443))
        head = s.recv(4)
        if len(head) < 4 or head[1] != 0:
            s.close()
            return False
        atyp = head[3]
        if atyp == 1:
            s.recv(4 + 2)
        elif atyp == 3:
            alen = s.recv(1)[0]
            s.recv(alen + 2)
        elif atyp == 4:
            s.recv(16 + 2)

        tls_s = SSL_CTX.wrap_socket(s, server_hostname=HOST)
        tls_s.settimeout(TIMEOUT)
        tls_s.sendall(f"GET /1.1.1.1 HTTP/1.1\\r\\nHost: {HOST}\\r\\nConnection: close\\r\\n\\r\\n".encode())
        body = b""
        while True:
            c = tls_s.recv(256)
            if not c:
                break
            body += c
        tls_s.close()
        if b"\\r\\n\\r\\n" in body:
            header, _ = body.split(b"\\r\\n\\r\\n", 1)
            status_line = header.split(b"\\r\\n")[0]
            if status_line.startswith(b"HTTP/") and not any(status_line.startswith(p) for p in (b"HTTP/1.1 5", b"HTTP/1.0 5", b"HTTP/1.1 407", b"HTTP/1.0 407")):
                return True
        return False
    except Exception:
        return False"""

old_funcs_pattern = re.compile(r"def try_http\(ip, port\):[\s\S]*?def try_socks5\(ip, port\):[\s\S]*?return False\s*\n\s*except Exception:\s*\n\s*return False")

for vf in verifier_files:
    with open(vf, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(r'HOST = "api\.ipify\.org"', 'HOST = "internetdb.shodan.io"', content)
    content = re.sub(r'TIMEOUT = 2', 'TIMEOUT = 5', content)

    content, n = old_funcs_pattern.subn(lambda m: new_verify_funcs, content)
    if n != 1:
        print(f"Warning: verify funcs replaced {n} times in {vf}")

    with open(vf, "w", encoding="utf-8") as f:
        f.write(content)

print(f"Updated {len(verifier_files)} verifier files.")
