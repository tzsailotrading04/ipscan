import os
import re

ROOT = r"D:\DEpinFarm"
shard_files = [os.path.join(ROOT, "kaggle", "cl_shodan", "run.py")] + [
    os.path.join(ROOT, "kaggle", f"cl_shodan_{i:02d}", "run.py") for i in range(20)
]

new_build_pool = '''async def build_pool(items):
    high_pri_pool = []  # 200, 404
    low_pri_pool = []   # 429, 403, other
    fail_counts = {"connect_error": 0, "timeout": 0, "bad_status": 0, "other": 0}
    status_counts = {"200": 0, "404": 0, "429": 0, "403": 0, "407": 0, "other": 0}
    lat_hist = {"<1s": 0, "1-3s": 0, "3-8s": 0, "8-15s": 0, "15-25s": 0, ">25s": 0}
    after_8s_count = 0
    other_types = {}
    sem = asyncio.Semaphore(600)

    def record_other(proto_tag, e):
        name = type(e).__name__
        count = other_types.get(name, 0)
        other_types[name] = count + 1
        if count < 10:
            print(f"[build_pool_other] {proto_tag} {name}: {e}", flush=True)

    def record_latency(dur):
        nonlocal after_8s_count
        if dur < 1.0:
            lat_hist["<1s"] += 1
        elif dur < 3.0:
            lat_hist["1-3s"] += 1
        elif dur < 8.0:
            lat_hist["3-8s"] += 1
        elif dur < 15.0:
            lat_hist["8-15s"] += 1
        elif dur < 25.0:
            lat_hist["15-25s"] += 1
        else:
            lat_hist[">25s"] += 1
        if dur >= 8.0:
            after_8s_count += 1

    async with aiohttp.ClientSession(headers=HEADERS) as shared:
        async def try_http(addr):
            t0 = time.monotonic()
            try:
                async with shared.get(BASE + rand_ip(), proxy=f"http://{addr}", timeout=15) as r:
                    dur = time.monotonic() - t0
                    st_k = str(r.status)
                    status_counts[st_k if st_k in status_counts else "other"] += 1
                    if r.status < 500 and r.status != 407:
                        record_latency(dur)
                        return r.status
                    return "bad_status"
            except asyncio.TimeoutError:
                return "timeout"
            except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError,
                    aiohttp.ClientProxyConnectionError, ConnectionError, OSError):
                return "connect_error"
            except Exception as e:
                record_other("http", e)
                return "other"

        async def try_socks5(addr):
            if not HAVE_SOCKS:
                record_other("socks5", RuntimeError("aiohttp_socks not available"))
                return "other"
            t0 = time.monotonic()
            try:
                conn = ProxyConnector.from_url(f"socks5://{addr}")
                async with aiohttp.ClientSession(headers=HEADERS, connector=conn) as s:
                    async with s.get(BASE + rand_ip(), timeout=15) as r:
                        dur = time.monotonic() - t0
                        st_k = str(r.status)
                        status_counts[st_k if st_k in status_counts else "other"] += 1
                        if r.status < 500 and r.status != 407:
                            record_latency(dur)
                            return r.status
                        return "bad_status"
            except asyncio.TimeoutError:
                return "timeout"
            except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError,
                    aiohttp.ClientProxyConnectionError, ConnectionError, OSError):
                return "connect_error"
            except Exception as e:
                record_other("socks5", e)
                return "other"

        async def v(item):
            addr, proto = item
            last_err = None
            async with sem:
                if proto == "socks5":
                    # STEP 1: Try socks5, if it fails retry once as http before rejecting
                    res = await try_socks5(addr)
                    if isinstance(res, int):
                        if res in (200, 404):
                            high_pri_pool.append((addr, "socks5"))
                        else:
                            low_pri_pool.append((addr, "socks5"))
                        return
                    last_err = res
                    # Retry once as http
                    res_http = await try_http(addr)
                    if isinstance(res_http, int):
                        if res_http in (200, 404):
                            high_pri_pool.append((addr, "http"))
                        else:
                            low_pri_pool.append((addr, "http"))
                        return
                    last_err = res_http
                else:
                    # proto == "http": Try http, if it fails retry once as socks5 before rejecting
                    res = await try_http(addr)
                    if isinstance(res, int):
                        if res in (200, 404):
                            high_pri_pool.append((addr, "http"))
                        else:
                            low_pri_pool.append((addr, "http"))
                        return
                    last_err = res
                    # Retry once as socks5
                    if HAVE_SOCKS:
                        res_s5 = await try_socks5(addr)
                        if isinstance(res_s5, int):
                            if res_s5 in (200, 404):
                                high_pri_pool.append((addr, "socks5"))
                            else:
                                low_pri_pool.append((addr, "socks5"))
                            return
                        last_err = res_s5

            if last_err and last_err in fail_counts:
                fail_counts[last_err] += 1

        await asyncio.gather(*[v(i) for i in items], return_exceptions=True)

    # STEP 3: Prioritise real responses: 200/404 at front, 429/403 at back
    pool = high_pri_pool + low_pri_pool
    log(f"[build_pool_fails] tested={len(items)} passed={len(pool)} connect_error={fail_counts['connect_error']} timeout={fail_counts['timeout']} bad_status={fail_counts['bad_status']} other={fail_counts['other']}")
    print(f"[build_pool_fails] tested={len(items)} passed={len(pool)} connect_error={fail_counts['connect_error']} timeout={fail_counts['timeout']} bad_status={fail_counts['bad_status']} other={fail_counts['other']}", flush=True)
    log(f"[build_pool_status] 200={status_counts['200']} 404={status_counts['404']} 429={status_counts['429']} 403={status_counts['403']} 407={status_counts['407']} other={status_counts['other']}")
    print(f"[build_pool_status] 200={status_counts['200']} 404={status_counts['404']} 429={status_counts['429']} 403={status_counts['403']} 407={status_counts['407']} other={status_counts['other']}", flush=True)
    log(f"[build_pool_latency] <1s={lat_hist['<1s']} 1-3s={lat_hist['1-3s']} 3-8s={lat_hist['3-8s']} 8-15s={lat_hist['8-15s']} 15-25s={lat_hist['15-25s']} >25s={lat_hist['>25s']} after_8s={after_8s_count}")
    print(f"[build_pool_latency] <1s={lat_hist['<1s']} 1-3s={lat_hist['1-3s']} 3-8s={lat_hist['3-8s']} 8-15s={lat_hist['8-15s']} 15-25s={lat_hist['15-25s']} >25s={lat_hist['>25s']} after_8s={after_8s_count}", flush=True)
    if other_types:
        log(f"[build_pool_other_types] {other_types}")
        print(f"[build_pool_other_types] {other_types}", flush=True)
    else:
        log(f"[build_pool_other_types] none (other=0)")
        print(f"[build_pool_other_types] none (other=0)", flush=True)
    return pool'''

for p in shard_files:
    with open(p, "r", encoding="utf-8") as f:
        c = f.read()

    # 1. Update ENGINE_VER to v98.154
    c = re.sub(r'ENGINE_VER = "v\d+\.\d+"', 'ENGINE_VER = "v98.154"', c)

    # 2. Update build_pool (timeout 15s + latency histogram)
    build_pool_pattern = re.compile(r'async def build_pool\(items\):.*?(?=\n\nclass HttpStatus|\nclass HttpStatus)', re.DOTALL)
    m = build_pool_pattern.search(c)
    assert m, f"build_pool not found in {p}"
    c = c[:m.start()] + new_build_pool + c[m.end():]

    # 3. Update FETCH_TIMEOUTS to {"FAST": 15, "MED": 20, "OK": 25}
    c = re.sub(r'FETCH_TIMEOUTS = \{[^}]+\}', 'FETCH_TIMEOUTS = {"FAST": 15, "MED": 20, "OK": 25}', c)
    # in fetch_ip fallback
    c = re.sub(r'FETCH_TIMEOUTS\.get\(PROXY_CLASS\.get\(addr, "MED"\), \d+\)', 'FETCH_TIMEOUTS.get(PROXY_CLASS.get(addr, "MED"), 25)', c)

    # 4. Update CONC = min(4000, max(120, int(1.5 * len(PROXY_POOL))))
    c = re.sub(r'CONC = min\(2000, max\(120, 2 \* len\(PROXY_POOL\)\)\)', 'CONC = min(4000, max(120, int(1.5 * len(PROXY_POOL))))', c)

    with open(p, "w", encoding="utf-8") as f:
        f.write(c)

print(f"Applied v98.154 to {len(shard_files)} shard files.")

# Update work/VERSION to v98.154
with open(os.path.join(ROOT, "work", "VERSION"), "w", encoding="utf-8") as f:
    f.write("v98.154\n")
print("Updated work/VERSION to v98.154.")
