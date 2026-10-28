"""
update_all_shards_multi_probe.py
Updates all 20 kaggle/cl_shodan_XX/run.py files:
- DIRECT_PORTS = [80, 443, 3128, 8080, 8000, 1080, 8118, 8888]
- Multi-target strict probe (speed.cloudflare.com, www.google.com, one.one.one.one) with 0x16 ServerHello check, 5s timeout
- Correct indentation of prog_file outside get_ip(offset)
- Resets progress/stats offsets
"""
import os
import re
import py_compile

ROOT = r"D:\DEpinFarm"
SHARDS = 20

PROBE_CODE = '''TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
CLIENT_HELLOS = {}
for _t in TARGETS:
    _ctx = ssl.create_default_context()
    _bio_in, _bio_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    _sslobj = _ctx.wrap_bio(_bio_in, _bio_out, server_hostname=_t)
    try:
        _sslobj.do_handshake()
    except ssl.SSLWantReadError:
        pass
    CLIENT_HELLOS[_t] = _bio_out.read()

async def inline_probe_connected(s, target, timeout=5.0):
    try:
        loop = asyncio.get_running_loop()
        req = f"CONNECT {target}:443 HTTP/1.1\\r\\nHost: {target}:443\\r\\n\\r\\n".encode()
        await loop.sock_sendall(s, req)
        resp = b""
        t_end = time.monotonic() + timeout
        while b"\\r\\n\\r\\n" not in resp:
            if time.monotonic() > t_end:
                return False
            c = await asyncio.wait_for(loop.sock_recv(s, 512), timeout=timeout)
            if not c:
                return False
            resp += c
        first_line = resp.split(b"\\r\\n")[0]
        if not (resp.startswith(b"HTTP/") and (b" 200" in first_line or b" 2" in first_line)):
            return False
        parts = resp.split(b"\\r\\n\\r\\n", 1)
        trailing = parts[1] if len(parts) > 1 else b""
        if trailing:
            return trailing[:1] == b"\\x16"
        await loop.sock_sendall(s, CLIENT_HELLOS[target])
        b1 = await asyncio.wait_for(loop.sock_recv(s, 1), timeout=timeout)
        return b1 == b"\\x16"
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass

async def probe_single_target(ip, port, target, timeout=5.0):
    loop = asyncio.get_running_loop()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setblocking(False)
    try:
        await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=timeout)
        return await inline_probe_connected(s, target, timeout=timeout)
    except Exception:
        try:
            s.close()
        except Exception:
            pass
        return False

async def check_direct_port(ip, port):
    global STAT_ERRNO99, STAT_TIMEOUT, STAT_REFUSED, STAT_GAIERROR, STAT_OTHER, DIRECT_SEM
    if DIRECT_SEM is None:
        DIRECT_SEM = asyncio.Semaphore(12000)
    async with DIRECT_SEM:
        loop = asyncio.get_running_loop()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        try:
            await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=2.0)
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
            if getattr(e, "errno", None) == 99 or "cannot assign requested address" in str(e).lower():
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

        if await inline_probe_connected(s, "speed.cloudflare.com", timeout=5.0):
            return port

        for t in ["www.google.com", "one.one.one.one"]:
            if await probe_single_target(ip, port, t, timeout=5.0):
                return port
        return None'''

def update_all():
    # Load subnets to know per-shard total
    subnets_file = os.path.join(ROOT, "data", "hosting_subnets.txt")
    with open(subnets_file, "r", encoding="utf-8") as f:
        all_subnets = [line.strip() for line in f if line.strip()]
    total_subnets = len(all_subnets)
    print(f"Total budget subnets: {total_subnets:,} ({total_subnets*256:,} IPs)")

    for i in range(SHARDS):
        stag = f"{i:02d}"
        shard_subnets = [s for idx, s in enumerate(all_subnets) if idx % SHARDS == i]
        shard_total_ips = len(shard_subnets) * 256

        fpath = os.path.join(ROOT, "kaggle", f"cl_shodan_{stag}", "run.py")
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        # 1. Replace old probe logic
        # Find from HOST = or TARGETS = down to async def scan_direct(ip):
        m = re.search(r'(HOST = "internetdb\.shodan\.io"|TARGETS = \[).*?(async def scan_direct\(ip\):)', content, re.DOTALL)
        if m:
            content = content[:m.start()] + PROBE_CODE + "\n\n" + m.group(2) + content[m.end():]
        else:
            print(f"WARN: could not match probe regex in shard {stag}")

        # 2. Fix prog_file indentation
        bad_indent = '        prog_file = os.path.join(REPO, "ip", "harvest", f"shodan_progress_{OUT_PREFIX}{SHARD_TAG}.txt")'
        good_indent = '    prog_file = os.path.join(REPO, "ip", "harvest", f"shodan_progress_{OUT_PREFIX}{SHARD_TAG}.txt")'
        content = content.replace(bad_indent, good_indent)

        # 3. DIRECT_PORTS exact
        content = re.sub(r'DIRECT_PORTS = \[.*?\]', 'DIRECT_PORTS = [80, 443, 3128, 8080, 8000, 1080, 8118, 8888]', content)

        # 4. Save and compile check
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        py_compile.compile(fpath, doraise=True)

        # 5. Reset progress and stats files
        prog_p = os.path.join(ROOT, "ip", "harvest", f"shodan_progress_v98_{stag}.txt")
        with open(prog_p, "w", encoding="utf-8") as f:
            f.write("0\nchunk=1\n")

        stats_p = os.path.join(ROOT, "ip", "harvest", f"shodan_stats_v98_{stag}.txt")
        with open(stats_p, "w", encoding="utf-8") as f:
            f.write(f"engine=v98.163\nshard={stag}\negress_ip=unknown\noffset=0\ntotal={shard_total_ips}\nchunk=1\n")

        print(f"Shard {stag}: {len(shard_subnets):,} subnets ({shard_total_ips:,} IPs) | compiled & reset OK")

if __name__ == "__main__":
    update_all()
