import os
import re

ROOT = r"D:\DEpinFarm"
shard_files = [os.path.join(ROOT, "kaggle", "cl_shodan", "run.py")] + [
    os.path.join(ROOT, "kaggle", f"cl_shodan_{i:02d}", "run.py") for i in range(20)
]

scan_direct_def = r'''SCAN_MODE = "direct"  # "direct" or "shodan"
DIRECT_PORTS = [8080, 3128, 1080, 8000]

async def check_direct_port(ip, port):
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=1.0)
        w.close()
        try:
            await w.wait_closed()
        except Exception:
            pass
        return port
    except Exception:
        return None

async def scan_direct(ip):
    res = await asyncio.gather(*[check_direct_port(ip, p) for p in DIRECT_PORTS], return_exceptions=True)
    return [p for p in res if isinstance(p, int)]
'''

new_startup = r'''    # Raise file descriptor limit
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = 65535
        if hard > 0 and hard < target:
            target = hard
        resource.setrlimit(resource.RLIMIT_NOFILE, (target, max(hard, target)))
        soft_eff, hard_eff = resource.getrlimit(resource.RLIMIT_NOFILE)
        log(f"[ulimit] RLIMIT_NOFILE soft={soft_eff} hard={hard_eff}")
        print(f"[ulimit] RLIMIT_NOFILE soft={soft_eff} hard={hard_eff}", flush=True)
    except Exception as e:
        log(f"[ulimit] {e}")

    if SCAN_MODE == "direct":
        PROXY_POOL = []
        CONC = 15000
        pacer = AdaptivePacer(start=15000.0, lo=1000.0, hi=30000.0)
        log(f"[mode] direct scan mode: skipping build_pool, CONC={CONC}")
        print(f"[mode] direct scan mode: skipping build_pool, CONC={CONC}", flush=True)
    else:
        # Startup — build pool BEFORE creating the main semaphore / worker tasks
        allc = []
        try:
            allc = load_candidates()
            mine = allc[SHARD_IDX::NUM_SHARDS]          # DISJOINT slice
            mine = mine[:20000]
            pass_rate_str = f"{len(allc)}/{max(1, TOTAL_VERIFIED_PARSED)} ({100.0 * len(allc) / max(1, TOTAL_VERIFIED_PARSED):.1f}%)"
            log(f"[ceiling] total_candidates={len(allc)} slice_size={len(mine)} pool_pass_rate={pass_rate_str}")
            print(f"[ceiling] total_candidates={len(allc)} slice_size={len(mine)} pool_pass_rate={pass_rate_str}", flush=True)
            async with aiohttp.ClientSession(headers=HEADERS) as tmp:
                PROXY_POOL = await build_pool(mine)
        except Exception as e:
            log(f"build_pool error: {e}")
            PROXY_POOL = []
        parsed_cnt = len(mine) if 'mine' in locals() else 0
        dropped_cnt = parsed_cnt - len(PROXY_POOL)
        log(f"[pool] shard={SHARD_IDX} parsed={parsed_cnt} dropped={dropped_cnt} pool_size={len(PROXY_POOL)}")
        print(f"[pool] shard={SHARD_IDX} parsed={parsed_cnt} dropped={dropped_cnt} pool_size={len(PROXY_POOL)}", flush=True)
        global POOL_MIN
        POOL_MIN = len(PROXY_POOL)

        CONC = min(4000, max(120, int(1.5 * len(PROXY_POOL))))
        PACER_HI = min(30000.0, max(3000.0, 15.0 * len(PROXY_POOL)))
        lo = max(200.0, PACER_HI * 0.1)
        start = min(PACER_HI, 500.0)
        pacer = AdaptivePacer(start=start, lo=lo, hi=PACER_HI)

        log(f"Configured CONC={CONC} pacer.rate={pacer.rate:.1f} pacer.hi={pacer.hi:.1f} pool_size={len(PROXY_POOL)}")'''

new_worker = r'''    async def worker():
        nonlocal current_idx, processed_count, cands_found, log_window_count
        global current_chunk, chunk_lines, chunk_handle
        while current_idx < total_ips:
            if STOPPING:
                break
            if time.time() - START_TIME >= HARD_STOP:
                break
            async with idx_lock:
                if current_idx >= total_ips:
                    break
                my_offset = current_idx
                current_idx += 1

            ip = get_ip(my_offset)
            if SCAN_MODE == "direct":
                hits = await scan_direct(ip)
                async with write_lock:
                    if hits:
                        stats["ok"] += 1
                        stats["ok_with_ports"] += 1
                        lines = [f"{ip}:{p}\n" for p in hits]
                        if chunk_lines + len(lines) >= CHUNK_MAX:
                            if chunk_handle:
                                chunk_handle.flush()
                                chunk_handle.close()
                            current_chunk += 1
                            next_chunk_file = os.path.join(REPO, "ip", "harvest", f"shodan_shard_{OUT_PREFIX}{SHARD_TAG}_c{current_chunk:03d}.txt")
                            chunk_handle = open(next_chunk_file, "a", encoding="utf-8")
                            chunk_lines = 0
                        chunk_handle.writelines(lines)
                        chunk_handle.flush()
                        chunk_lines += len(lines)
                        cands_found += len(lines)
                        stats["kept_lines"] += len(lines)
            else:
                await pacer.acquire()
                status = await fetch_ip(session, ip, pacer)
                ports = getattr(status, "ports", [])
                async with write_lock:
                    if status == 200:
                        stats["ok"] += 1
                        if ports:
                            stats["ok_with_ports"] += 1
                            first_match = next((p for p in ports if int(p) in PROXY_PORTS), None)
                            if first_match is None:
                                first_match = next((p for p in ports if int(p) in {443, 8443}), None)
                            if first_match is not None:
                                lines = [f"{ip}:{first_match}\n"]
                                if chunk_lines >= CHUNK_MAX:
                                    if chunk_handle:
                                        chunk_handle.flush()
                                        chunk_handle.close()
                                    current_chunk += 1
                                    next_chunk_file = os.path.join(REPO, "ip", "harvest", f"shodan_shard_{OUT_PREFIX}{SHARD_TAG}_c{current_chunk:03d}.txt")
                                    chunk_handle = open(next_chunk_file, "a", encoding="utf-8")
                                    chunk_lines = 0
                                chunk_handle.writelines(lines)
                                chunk_handle.flush()
                                chunk_lines += len(lines)
                                cands_found += len(lines)
                                stats["kept_lines"] += len(lines)
                            else:
                                stats["ok_no_keep"] += 1
                    elif status == 404:
                        stats["not_found"] += 1
                    elif status == 429:
                        stats["rate_limit"] += 1
                    elif status is None or status == 0:
                        stats["timeout"] += 1
                    else:
                        stats["other"] += 1

            async with idx_lock:
                if my_offset + 1 > processed_count:
                    processed_count = my_offset + 1
                log_window_count += 1'''

new_monitor_log = r'''                if SCAN_MODE == "direct":
                    hit_rate = (stats["kept_lines"] / max(1, processed_count)) * 1000.0
                    log(f"Rate {ir:.1f}/s | {processed_count:,}/{total_ips:,} ({pct:.2f}%) | cands={cands_found} chunk={current_chunk} | hit_rate={hit_rate:.2f}/1000 IPs | hits={stats['kept_lines']}")
                    print(f"Rate {ir:.1f}/s | {processed_count:,}/{total_ips:,} ({pct:.2f}%) | cands={cands_found} chunk={current_chunk} | hit_rate={hit_rate:.2f}/1000 IPs | hits={stats['kept_lines']}", flush=True)
                else:
                    usable_now = sum(1 for p in PROXY_POOL if BANNED.get(p[0], 0.0) <= now_m and FAILS_UNTIL.get(p[0], 0.0) <= now_m)
                    log(f"Rate {ir:.1f}/s (pacer: {pacer.rate:.1f}/s) | {processed_count:,}/{total_ips:,} ({pct:.2f}%) | usable={usable_now} pool={len(PROXY_POOL)} | "
                        f"cands={cands_found:,} chunk={current_chunk} | ok={stats['ok']} 404={stats['not_found']} "
                        f"429={stats['rate_limit']} to={stats['timeout']} "
                        f"ok_ports={stats['ok_with_ports']} no_keep={stats['ok_no_keep']}")
                '''

for p in shard_files:
    with open(p, "r", encoding="utf-8") as f:
        c = f.read()

    # 1. Update ENGINE_VER and add SCAN_MODE + scan_direct
    c = re.sub(r'ENGINE_VER = "v\d+\.\d+"', 'ENGINE_VER = "v98.158"', c)

    if 'SCAN_MODE =' not in c:
        c = c.replace('CHUNK_MAX = 100_000\n', 'CHUNK_MAX = 100_000\n\n' + scan_direct_def + '\n')

    # 2. Add ulimit and direct mode initialization in async_main
    s_startup = c.find('    # Startup')
    e_startup = c.find('    idx_lock = asyncio.Lock()', s_startup)
    assert s_startup != -1 and e_startup != -1, f"Startup block not found in {p}"
    c = c[:s_startup] + new_startup + '\n\n' + c[e_startup:]

    # 3. Update pool_refill call
    c = c.replace('rev_task = asyncio.create_task(pool_refill())',
                  'rev_task = asyncio.create_task(pool_refill()) if SCAN_MODE != "direct" else None')

    # 4. Replace worker()
    s_worker = c.find('    async def worker():')
    e_worker = c.find('    async def monitor():', s_worker)
    assert s_worker != -1 and e_worker != -1, f"Worker block not found in {p}"
    c = c[:s_worker] + new_worker + '\n\n' + c[e_worker:]

    # 5. Update monitor() rate log
    s_mon = c.find('usable_now = sum(1 for p in PROXY_POOL')
    e_mon = c.find('last_log_time = now', s_mon)
    assert s_mon != -1 and e_mon != -1, f"Monitor log block not found in {p}"
    c = c[:s_mon] + new_monitor_log.strip() + '\n                ' + c[e_mon:]

    with open(p, "w", encoding="utf-8") as f:
        f.write(c)

print(f"Applied v98.158 direct scan mode cleanly to {len(shard_files)} shard files.")

# Update work/VERSION
with open(os.path.join(ROOT, "work", "VERSION"), "w", encoding="utf-8") as f:
    f.write("v98.158\n")
print("Updated work/VERSION to v98.158.")
