import os, py_compile

REPO = r"D:\DEpinFarm"
master_file = os.path.join(REPO, "kaggle", "cl_shodan", "run.py")

with open(master_file, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update ENGINE_VER
content = content.replace('ENGINE_VER = "v98.182"', 'ENGINE_VER = "v98.184"')

# 2. Update sync_tls_handshake & sync_probe_target
old_tls = """    def sync_tls_handshake(sock, target, timeout=4.0):
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
            _ = ss.getpeercert()
            ss.close()
            return True
        except Exception:
            try: sock.close()
            except Exception: pass
            return False

    def sync_probe_target(ip, port, target, timeout=4.0):
        s = None
        try:
            s = socket.create_connection((ip, port), timeout=timeout)
            return sync_tls_handshake(s, target, timeout=timeout)
        except Exception:
            if s:
                try: s.close()
                except Exception: pass
            return False"""

new_tls = """    def sync_tls_handshake(sock, target, timeout=8.0):
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
            parts = resp.split(b"\\r\\n\\r\\n", 1)
            trailing = parts[1] if len(parts) > 1 else b""
            if trailing and trailing[:1] != b"\\x16":
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

    def sync_probe_target(ip, port, target, timeout=8.0):
        s = None
        try:
            s = socket.create_connection((ip, port), timeout=timeout)
            return sync_tls_handshake(s, target, timeout=timeout)
        except Exception:
            if s:
                try: s.close()
                except Exception: pass
            return False"""

# Handle potential CRLF vs LF
if old_tls not in content and old_tls.replace("\n", "\r\n") in content:
    content = content.replace(old_tls.replace("\n", "\r\n"), new_tls.replace("\n", "\r\n"))
elif old_tls in content:
    content = content.replace(old_tls, new_tls)
else:
    raise RuntimeError("old_tls block not found in cl_shodan/run.py")

# 3. Update timeout in check_port
old_conn = "await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=1.8)"
new_conn = "await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=8.0)"
if old_conn in content:
    content = content.replace(old_conn, new_conn)
else:
    raise RuntimeError("old_conn not found in cl_shodan/run.py")

old_exec = """            # Primary target probe with connected socket
            if await loop.run_in_executor(None, sync_tls_handshake, s, "speed.cloudflare.com", 4.0):
                return port, "speed.cloudflare.com"

            for t in ["www.google.com", "one.one.one.one"]:
                if await loop.run_in_executor(None, sync_probe_target, ip, port, t, 4.0):
                    return port, t"""

new_exec = """            # Primary target probe with connected socket
            if await loop.run_in_executor(None, sync_tls_handshake, s, "speed.cloudflare.com", 8.0):
                return port, "speed.cloudflare.com"

            for t in ["www.google.com", "one.one.one.one"]:
                if await loop.run_in_executor(None, sync_probe_target, ip, port, t, 8.0):
                    return port, t"""

if old_exec not in content and old_exec.replace("\n", "\r\n") in content:
    content = content.replace(old_exec.replace("\n", "\r\n"), new_exec.replace("\n", "\r\n"))
elif old_exec in content:
    content = content.replace(old_exec, new_exec)
else:
    raise RuntimeError("old_exec not found in cl_shodan/run.py")

with open(master_file, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated master template kaggle/cl_shodan/run.py successfully.")

# Propagate to all 34 shards
compile_errors = []
for i in range(34):
    shard_tag = f"{i:02d}"
    shard_file = os.path.join(REPO, "kaggle", f"cl_shodan_{shard_tag}", "run.py")
    shard_code = content.replace("SHARD_IDX = 0\n", f"SHARD_IDX = {i}\n").replace("SHARD_IDX = 0\r\n", f"SHARD_IDX = {i}\r\n")
    with open(shard_file, "w", encoding="utf-8") as sf:
        sf.write(shard_code)

print("Propagated to all 34 shards.")

# Also update kaggle/cl_harvest/run.py
harvest_file = os.path.join(REPO, "kaggle", "cl_harvest", "run.py")
with open(harvest_file, "r", encoding="utf-8") as hf:
    h_content = hf.read()

# Update cl_harvest sync_tls_handshake & sync_probe_candidate
h_old = """def sync_tls_handshake(sock, target, timeout=6.0):
    try:
        sock.setblocking(True)
        sock.settimeout(timeout)
        req = f"CONNECT {target}:443 HTTP/1.1\\r\\nHost: {target}:443\\r\\nUser-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)\\r\\nProxy-Connection: Keep-Alive\\r\\n\\r\\n".encode()
        sock.sendall(req)

        resp = b""
        while b"\\r\\n\\r\\n" not in resp:
            chunk = sock.recv(512)
            if not chunk:
                return False
            resp += chunk
            if len(resp) > 4096:
                return False

        first_line = resp.split(b"\\r\\n")[0]
        if not (b" 200" in first_line or b"HTTP/1.1 200" in first_line or b"HTTP/1.0 200" in first_line):
            return False

        # Peek TLS record header: MUST be 0x16 (TLS Handshake record type)
        peek_hdr = sock.recv(5, socket.MSG_PEEK)
        if len(peek_hdr) < 5 or peek_hdr[0] != 0x16:
            return False

        # Full TLS handshake validated against system CA chain
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
        try:
            sock.close()
        except Exception:
            pass
        return False"""

h_new = """def sync_tls_handshake(sock, target, timeout=8.0):
    try:
        sock.setblocking(True)
        sock.settimeout(timeout)
        req = f"CONNECT {target}:443 HTTP/1.1\\r\\nHost: {target}:443\\r\\n\\r\\n".encode()
        sock.sendall(req)

        resp = b""
        while b"\\r\\n\\r\\n" not in resp:
            chunk = sock.recv(512)
            if not chunk:
                return False
            resp += chunk
            if len(resp) > 2048:
                return False

        first_line = resp.split(b"\\r\\n")[0]
        if not (b" 200" in first_line or b"HTTP/1.1 200" in first_line or b"HTTP/1.0 200" in first_line):
            return False

        parts = resp.split(b"\\r\\n\\r\\n", 1)
        trailing = parts[1] if len(parts) > 1 else b""
        if trailing and trailing[:1] != b"\\x16":
            return False

        # Full TLS handshake validated against system CA chain
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
        try:
            sock.close()
        except Exception:
            pass
        return False"""

if h_old not in h_content and h_old.replace("\n", "\r\n") in h_content:
    h_content = h_content.replace(h_old.replace("\n", "\r\n"), h_new.replace("\n", "\r\n"))
elif h_old in h_content:
    h_content = h_content.replace(h_old, h_new)

h_content = h_content.replace("timeout=6.0", "timeout=8.0")
with open(harvest_file, "w", encoding="utf-8") as hf:
    hf.write(h_content)
print("Updated kaggle/cl_harvest/run.py successfully.")

# Update work/VERSION to v98.184
with open(os.path.join(REPO, "work", "VERSION"), "w", encoding="utf-8") as vf:
    vf.write("v98.184\n")
print("Updated work/VERSION to v98.184.")
