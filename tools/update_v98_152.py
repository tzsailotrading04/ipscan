import os
import re

ROOT = r"D:\DEpinFarm"
shard_files = [os.path.join(ROOT, "kaggle", "cl_shodan", "run.py")] + [
    os.path.join(ROOT, "kaggle", f"cl_shodan_{i:02d}", "run.py") for i in range(20)
]

for p in shard_files:
    with open(p, "r", encoding="utf-8") as f:
        c = f.read()

    # 1. Engine version
    c = re.sub(r'ENGINE_VER = "v\d+\.\d+"', 'ENGINE_VER = "v98.152"', c)

    # 2. STEP 1 - Gentler cooling: 2 consecutive failures, cap cooldown at 20s
    old_cooling = """        except (asyncio.TimeoutError, aiohttp.ClientError, ConnectionError):
            if use_proxy:
                STATS_PROXY_FAIL += 1
                key = (addr, proto)
                FAILS[key] = FAILS.get(key, 0) + 1
                FAILS_UNTIL[addr] = time.monotonic() + min(60.0, 5.0 * FAILS[key])
            continue"""

    new_cooling = """        except (asyncio.TimeoutError, aiohttp.ClientError, ConnectionError):
            if use_proxy:
                STATS_PROXY_FAIL += 1
                key = (addr, proto)
                FAILS[key] = FAILS.get(key, 0) + 1
                if FAILS[key] >= 2:
                    FAILS_UNTIL[addr] = time.monotonic() + min(20.0, 5.0 * FAILS[key])
            continue"""

    assert old_cooling in c, f"old_cooling not found in {p}"
    c = c.replace(old_cooling, new_cooling)

    # 3. STEP 2 - Inject volume from lists_all.txt in load_candidates
    # Add lists_all.txt to v_files
    old_vfiles = """    v_files = sorted(glob.glob(os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive_part_*.txt")))
    v_files += [os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive.txt")]
    v_files += [os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive.bak.txt")]"""

    new_vfiles = """    v_files = sorted(glob.glob(os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive_part_*.txt")))
    v_files += [os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive.txt")]
    v_files += [os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive.bak.txt")]
    v_files += [os.path.join(REPO_ROOT, "ip", "harvest", "lists_all.txt")]"""

    assert old_vfiles in c, f"old_vfiles not found in {p}"
    c = c.replace(old_vfiles, new_vfiles)

    # Update parse_verified in load_candidates to handle lists_all.txt
    old_parse = """    def parse_verified(path):
        res = []
        if not os.path.exists(path):
            return res
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    p = line.split("\\t")
                    if len(p) < 2:
                        continue
                    addr = p[0].strip()
                    if ":" not in addr:
                        continue
                    proto = p[1].strip().lower()
                    if proto not in ("http", "socks5"):
                        proto = "http"
                    ms = 99999
                    cls = "SLOW"
                    if len(p) >= 6:
                        try:
                            ms = int(p[5].strip())
                        except Exception:
                            ms = 99999
                    if len(p) >= 7:
                        cls = p[6].strip().upper()
                    raw_cycle = 1
                    if len(p) >= 8:
                        try:
                            raw_cycle = int(p[7].strip())
                        except Exception:
                            raw_cycle = 1
                    res.append((addr, proto, ms, cls, raw_cycle))
        except Exception:
            pass
        return res"""

    new_parse = """    def parse_verified(path):
        res = []
        if not os.path.exists(path):
            return res
        is_list = "lists_all" in os.path.basename(path)
        is_legacy = "part_" not in os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    p = line.split("\\t")
                    addr = p[0].strip()
                    if ":" not in addr:
                        continue
                    if is_list:
                        res.append((addr, "http", 2000, "OK", 1))
                    else:
                        proto = p[1].strip().lower() if len(p) >= 2 else "http"
                        if proto not in ("http", "socks5"):
                            proto = "http"
                        ms = 99999
                        cls = "SLOW"
                        if len(p) >= 6:
                            try:
                                ms = int(p[5].strip())
                            except Exception:
                                ms = 99999
                        if len(p) >= 7:
                            cls = p[6].strip().upper()
                        raw_cycle = 1
                        if len(p) >= 8:
                            try:
                                raw_cycle = int(p[7].strip())
                            except Exception:
                                raw_cycle = 1
                        cycle = 1 if is_legacy else raw_cycle
                        res.append((addr, proto, ms, cls, cycle))
        except Exception:
            pass
        return res"""

    assert old_parse in c, f"old_parse not found in {p}"
    c = c.replace(old_parse, new_parse)

    # 4. STEP 3 - Status distribution in build_pool
    old_build_pool_head = """async def build_pool(items):
    pool = []
    fail_counts = {"connect_error": 0, "timeout": 0, "bad_status": 0, "other": 0}
    sem = asyncio.Semaphore(600)"""

    new_build_pool_head = """async def build_pool(items):
    pool = []
    fail_counts = {"connect_error": 0, "timeout": 0, "bad_status": 0, "other": 0}
    status_counts = {"200": 0, "404": 0, "429": 0, "403": 0, "407": 0, "other": 0}
    sem = asyncio.Semaphore(600)"""

    assert old_build_pool_head in c, f"old_build_pool_head not found in {p}"
    c = c.replace(old_build_pool_head, new_build_pool_head)

    # In socks5:
    old_s5_status = """                                async with s.get(BASE + rand_ip(), timeout=8) as r:
                                    if r.status < 500 and r.status != 407:"""

    new_s5_status = """                                async with s.get(BASE + rand_ip(), timeout=8) as r:
                                    st_k = str(r.status)
                                    status_counts[st_k if st_k in status_counts else "other"] += 1
                                    if r.status < 500 and r.status != 407:"""

    assert old_s5_status in c, f"old_s5_status not found in {p}"
    c = c.replace(old_s5_status, new_s5_status)

    # In http:
    old_http_status = """                        try:
                            async with shared.get(BASE + rand_ip(), proxy=f"http://{addr}", timeout=8) as r:
                                if r.status < 500 and r.status != 407:"""

    new_http_status = """                        try:
                            async with shared.get(BASE + rand_ip(), proxy=f"http://{addr}", timeout=8) as r:
                                st_k = str(r.status)
                                status_counts[st_k if st_k in status_counts else "other"] += 1
                                if r.status < 500 and r.status != 407:"""

    assert old_http_status in c, f"old_http_status not found in {p}"
    c = c.replace(old_http_status, new_http_status)

    # At end of build_pool, log status_counts
    old_bp_log = """    log(f"[build_pool_fails] tested={len(items)} passed={len(pool)} connect_error={fail_counts['connect_error']} timeout={fail_counts['timeout']} bad_status={fail_counts['bad_status']} other={fail_counts['other']}")
    return pool"""

    new_bp_log = """    log(f"[build_pool_fails] tested={len(items)} passed={len(pool)} connect_error={fail_counts['connect_error']} timeout={fail_counts['timeout']} bad_status={fail_counts['bad_status']} other={fail_counts['other']}")
    log(f"[build_pool_status] 200={status_counts['200']} 404={status_counts['404']} 429={status_counts['429']} 403={status_counts['403']} 407={status_counts['407']} other={status_counts['other']}")
    print(f"[build_pool_status] 200={status_counts['200']} 404={status_counts['404']} 429={status_counts['429']} 403={status_counts['403']} 407={status_counts['407']} other={status_counts['other']}", flush=True)
    return pool"""

    assert old_bp_log in c, f"old_bp_log not found in {p}"
    c = c.replace(old_bp_log, new_bp_log)

    with open(p, "w", encoding="utf-8") as f:
        f.write(c)

print(f"Applied v98.152 updates to {len(shard_files)} shard files.")

# Update work/VERSION
with open(os.path.join(ROOT, "work", "VERSION"), "w", encoding="utf-8") as f:
    f.write("v98.152\n")
print("Updated work/VERSION to v98.152.")
