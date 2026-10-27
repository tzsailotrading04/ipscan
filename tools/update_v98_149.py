import os
import re

ROOT = r"D:\DEpinFarm"

# 1. Update all 21 shard files
shard_files = [os.path.join(ROOT, "kaggle", "cl_shodan", "run.py")] + [
    os.path.join(ROOT, "kaggle", f"cl_shodan_{i:02d}", "run.py") for i in range(20)
]

for p in shard_files:
    with open(p, "r", encoding="utf-8") as f:
        content = f.read()

    # Engine version
    content = re.sub(r'ENGINE_VER = "v\d+\.\d+"', 'ENGINE_VER = "v98.149"', content)

    # Globals: add FETCH_TIMEOUTS and TOTAL_VERIFIED_PARSED
    if "FETCH_TIMEOUTS" not in content:
        content = content.replace(
            'PROXY_CLASS = {}\n',
            'PROXY_CLASS = {}\nTOTAL_VERIFIED_PARSED = 0\nFETCH_TIMEOUTS = {"FAST": 10, "MED": 15, "OK": 20}\n'
        )

    # STEP 1: Raise build_pool validation timeout 5s to 8s
    build_pool_pattern = re.compile(r'async def build_pool\(items\):.*?(?=\n\nclass HttpStatus|\nclass HttpStatus)', re.DOTALL)
    m = build_pool_pattern.search(content)
    if m:
        old_bp = m.group(0)
        new_bp = old_bp.replace("timeout=5", "timeout=8")
        content = content[:m.start()] + new_bp + content[m.end():]

    # STEP 2: Raise fetch timeouts: FAST 10s, MED 15s, OK 20s
    content = re.sub(
        r'to = 6 if PROXY_CLASS\.get\(addr, "MED"\) == "FAST" else 10',
        'to = FETCH_TIMEOUTS.get(PROXY_CLASS.get(addr, "MED"), 20)',
        content
    )

    # STEP 3 & STEP 4: Relax cycle cutoff (max_cycle - 20) and accept OK latency (<8000ms)
    old_load_cands_pattern = re.compile(r'def load_candidates\(\):.*?(?=\nasync def build_pool)', re.DOTALL)
    m_lc = old_load_cands_pattern.search(content)
    if m_lc:
        new_load_cands = '''def load_candidates():
    """Newest-first verified entries, cycle-filtered and latency-filtered:
    1. Read cycle field (last column).
    2. Discard entries more than 20 cycles behind the highest seen (relaxed cutoff).
    3. Sort candidates descending by cycle (newest first).
    4. Apply FAST (<1000ms), MED (<3000ms), OK (<8000ms) latency filter.
    5. Log pool_pass_rate as kept/parsed.
    """
    def parse_verified(path):
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
        return res

    v_files = sorted(glob.glob(os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive_part_*.txt")))
    v_files += [os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive.txt")]
    v_files += [os.path.join(REPO_ROOT, "ip", "harvest", "verified_alive.bak.txt")]

    all_parsed = []
    total_parsed = 0
    max_cycle = 0

    for vf in v_files:
        if not os.path.exists(vf):
            continue
        is_legacy = "part_" not in os.path.basename(vf)
        entries = parse_verified(vf)
        total_parsed += len(entries)
        for addr, proto, ms, cls, raw_cycle in entries:
            # Legacy files (verified_alive.txt / .bak) were pre-partition, default to cycle 1
            cycle = 1 if is_legacy else raw_cycle
            if cycle > max_cycle:
                max_cycle = cycle
            all_parsed.append((addr, proto, ms, cls, cycle))

    # Cutoff: discard entries whose cycle is more than 20 cycles behind highest seen
    cutoff = max(0, max_cycle - 20)
    log(f"[cycle_filter] max_cycle={max_cycle} cutoff={cutoff}")

    # Deduplicate by addr, keeping highest cycle
    best_by_addr = {}
    for addr, proto, ms, cls, cycle in all_parsed:
        if cycle < cutoff:
            continue
        if addr not in best_by_addr or cycle > best_by_addr[addr][4]:
            best_by_addr[addr] = (addr, proto, ms, cls, cycle)

    # Sort candidates by cycle descending (newest verified come first)
    candidates = list(best_by_addr.values())
    candidates.sort(key=lambda x: x[4], reverse=True)

    # Filter FAST (<1000ms), MED (<3000ms), OK (<8000ms)
    fast_entries = []
    med_entries = []
    ok_entries = []
    slow_entries = []
    for addr, proto, ms, cls, cycle in candidates:
        if cls == "FAST" or ms < 1000:
            fast_entries.append((addr, proto, ms, "FAST", cycle))
        elif cls == "MED" or ms < 3000:
            med_entries.append((addr, proto, ms, "MED", cycle))
        elif cls == "OK" or ms < 8000:
            ok_entries.append((addr, proto, ms, "OK", cycle))
        else:
            slow_entries.append((addr, proto, ms, "SLOW", cycle))

    pool_cands = fast_entries + med_entries + ok_entries
    slow_used = 0
    if len(pool_cands) < 200 and slow_entries:
        slow_entries.sort(key=lambda x: x[2])
        needed = 200 - len(pool_cands)
        fill_slow = slow_entries[:needed]
        pool_cands += fill_slow
        slow_used = len(fill_slow)

    global PROXY_CLASS, TOTAL_VERIFIED_PARSED
    PROXY_CLASS = {x[0]: x[3] for x in pool_cands}
    TOTAL_VERIFIED_PARSED = total_parsed

    # STEP 4: Log pool_pass_rate as kept/parsed
    pass_rate_str = f"{len(pool_cands)}/{total_parsed} ({100.0 * len(pool_cands) / max(1, total_parsed):.1f}%)"
    log(f"pool_pass_rate={pass_rate_str} | FAST={len(fast_entries)} MED={len(med_entries)} OK={len(ok_entries)} SLOW={slow_used}")

    out = [(x[0], x[1]) for x in pool_cands]
    return out
'''
        content = content[:m_lc.start()] + new_load_cands + content[m_lc.end():]

    # STEP 5: Log ceiling at startup
    old_startup_block = '''    allc = []
    try:
        allc = load_candidates()
        mine = allc[SHARD_IDX::NUM_SHARDS]          # DISJOINT slice
        mine = mine[:20000]
        async with aiohttp.ClientSession(headers=HEADERS) as tmp:
            PROXY_POOL = await build_pool(mine)
    except Exception as e:
        log(f"build_pool error: {e}")
        PROXY_POOL = []'''

    new_startup_block = '''    allc = []
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
        PROXY_POOL = []'''

    content = content.replace(old_startup_block, new_startup_block)

    with open(p, "w", encoding="utf-8") as f:
        f.write(content)

print(f"Updated {len(shard_files)} shard files.")

# 2. Update verifier files (cl_verify and cl_verify_0 .. cl_verify_8)
verify_files = [os.path.join(ROOT, "kaggle", "cl_verify", "run.py")] + [
    os.path.join(ROOT, "kaggle", f"cl_verify_{i}", "run.py") for i in range(9)
]

for vp in verify_files:
    if not os.path.exists(vp):
        continue
    with open(vp, "r", encoding="utf-8") as f:
        vcontent = f.read()

    # Latency class OK
    vcontent = vcontent.replace(
        'cls = "FAST" if ms < 1000 else ("MED" if ms < 3000 else "SLOW")',
        'cls = "FAST" if ms < 1000 else ("MED" if ms < 3000 else ("OK" if ms < 8000 else "SLOW"))'
    )
    vcontent = vcontent.replace(
        'if "\\tFAST" in prefix or "\\tMED" in prefix]',
        'if "\\tFAST" in prefix or "\\tMED" in prefix or "\\tOK" in prefix]'
    )

    with open(vp, "w", encoding="utf-8") as f:
        f.write(vcontent)

print(f"Updated {len(verify_files)} verifier files.")

# 3. Update work/VERSION
with open(os.path.join(ROOT, "work", "VERSION"), "w", encoding="utf-8") as f:
    f.write("v98.149\n")
print("Updated work/VERSION to v98.149.")
