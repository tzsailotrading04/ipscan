import os
import re

ROOT = r"D:\DEpinFarm"

# 1. Update all 21 shard files
shard_files = [os.path.join(ROOT, "kaggle", "cl_shodan", "run.py")] + [
    os.path.join(ROOT, "kaggle", f"cl_shodan_{i:02d}", "run.py") for i in range(20)
]

new_fetch = """async def fetch_ip(session, ip, pacer):
    global STATS_PROXY_OK, STATS_PROXY_FAIL, STATS_DIRECT_USED, STATS_BANNED_TOTAL
    for attempt in range(2):
        if PROXY_POOL:
            now = time.monotonic()
            usable = [p for p in PROXY_POOL if BANNED.get(p[0], 0.0) <= now and FAILS_UNTIL.get(p[0], 0.0) <= now]
            if usable:
                addr, proto = random.choice(usable)
            else:
                addr, proto = min(PROXY_POOL, key=lambda p: max(BANNED.get(p[0], 0.0), FAILS_UNTIL.get(p[0], 0.0)))
            use_proxy = f"socks5://{addr}" if proto == "socks5" else f"http://{addr}"
            to = 6 if PROXY_CLASS.get(addr, "MED") == "FAST" else 10
            await proxy_gate(addr)
        else:
            use_proxy = None
            to = 10
        try:
            async with session.get(BASE + ip, proxy=use_proxy, timeout=to) as r:
                if use_proxy:
                    FAILS[(addr, proto)] = 0
                    FAILS_UNTIL.pop(addr, None)
                    STATS_PROXY_OK += 1
                else:
                    STATS_DIRECT_USED += 1
                ra = r.headers.get("Retry-After")
                if r.status == 429:
                    if ra:
                        try:
                            ra_val = float(ra)
                        except (ValueError, TypeError):
                            ra_val = 60.0
                        if use_proxy:
                            BANNED[addr] = time.monotonic() + min(ra_val, 600.0)
                            STATS_BANNED_TOTAL += 1
                pacer.on_result(r.status, ra)
                ports = []
                if r.status == 200:
                    try:
                        data = await r.json()
                        ports = data.get("ports", [])
                    except Exception:
                        pass
                return HttpStatus(r.status, ports)
        except (asyncio.TimeoutError, aiohttp.ClientError, ConnectionError):
            if use_proxy:
                STATS_PROXY_FAIL += 1
                key = (addr, proto)
                FAILS[key] = FAILS.get(key, 0) + 1
                FAILS_UNTIL[addr] = time.monotonic() + min(60.0, 5.0 * FAILS[key])
            continue
        except Exception:
            continue
    pacer.on_result(0)
    return None"""

old_load_block = """    log(f"[pool_quality] FAST={len(fast_entries)} MED={len(med_entries)} SLOW={slow_used} total={len(pool_cands)}")

    out = [(x[0], x[1]) for x in pool_cands]"""

new_load_block = """    global PROXY_CLASS
    PROXY_CLASS = {x[0]: x[3] for x in pool_cands}

    log(f"[pool_quality] FAST={len(fast_entries)} MED={len(med_entries)} SLOW={slow_used} total={len(pool_cands)}")

    out = [(x[0], x[1]) for x in pool_cands]"""

fetch_pattern = re.compile(r"async def fetch_ip\(session, ip, pacer\):[\s\S]*?pacer\.on_result\(0\)\s*\n\s*return None")

for sf in shard_files:
    with open(sf, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(r'ENGINE_VER\s*=\s*"v98\.\d+"', 'ENGINE_VER = "v98.143"', content)

    if "PROXY_CLASS = {}" not in content:
        content = content.replace("BANNED = {}", "PROXY_CLASS = {}\nBANNED = {}")

    if old_load_block in content:
        content = content.replace(old_load_block, new_load_block)
    elif "PROXY_CLASS = {x[0]: x[3] for x in pool_cands}" not in content:
        print(f"Warning: load_block not replaced in {sf}")

    content, n = fetch_pattern.subn(new_fetch, content)
    if n != 1:
        print(f"Warning: fetch_ip pattern matched {n} times in {sf}")

    content = re.sub(
        r"CONC\s*=\s*min\(4000,\s*max\(200,\s*3\s*\*\s*len\(PROXY_POOL\)\)\)",
        "CONC = min(2000, max(120, 2 * len(PROXY_POOL)))",
        content,
    )

    with open(sf, "w", encoding="utf-8") as f:
        f.write(content)

print(f"Updated {len(shard_files)} shard files.")

# 2. Update all 10 verifier files
verifier_files = [os.path.join(ROOT, "kaggle", "cl_verify", "run.py")] + [
    os.path.join(ROOT, "kaggle", f"cl_verify_{i}", "run.py") for i in range(9)
]

old_chunk_gather = """    # 2. Gather candidates (prioritise new high-yield chunks first)
    chunk_files = sorted(glob.glob(os.path.join(REPO, "ip", "harvest", "shodan_shard_v98_*_c*.txt")))
    feed_files = [
        os.path.join(REPO, "ip", "harvest", "feeds_raw.txt"),
        os.path.join(REPO, "ip", "harvest", "net_new.txt"),
        os.path.join(REPO, "ip", "harvest", "leakix.txt"),
        os.path.join(REPO, "ip", "harvest", "hits_new_exits.txt"),
    ]
    old_v98_files = sorted([f for f in glob.glob(os.path.join(REPO, "ip", "harvest", "shodan_shard_v98_*.txt")) if "_c" not in os.path.basename(f)])
    legacy_files = sorted([f for f in glob.glob(os.path.join(REPO, "ip", "harvest", "shodan_shard_*.txt")) if "v98" not in os.path.basename(f)])
    all_candidate_files = chunk_files + [f for f in feed_files if os.path.exists(f)] + old_v98_files + legacy_files"""

new_chunk_gather = """    # 2. Gather candidates (lists_all.txt FIRST, then new high-yield chunks)
    list_files = [os.path.join(REPO, "ip", "harvest", "lists_all.txt")]
    chunk_files = sorted(glob.glob(os.path.join(REPO, "ip", "harvest", "shodan_shard_v98_*_c*.txt")))
    feed_files = [
        os.path.join(REPO, "ip", "harvest", "feeds_raw.txt"),
        os.path.join(REPO, "ip", "harvest", "net_new.txt"),
        os.path.join(REPO, "ip", "harvest", "leakix.txt"),
        os.path.join(REPO, "ip", "harvest", "hits_new_exits.txt"),
    ]
    old_v98_files = sorted([f for f in glob.glob(os.path.join(REPO, "ip", "harvest", "shodan_shard_v98_*.txt")) if "_c" not in os.path.basename(f)])
    legacy_files = sorted([f for f in glob.glob(os.path.join(REPO, "ip", "harvest", "shodan_shard_*.txt")) if "v98" not in os.path.basename(f)])
    all_candidate_files = [f for f in list_files if os.path.exists(f)] + chunk_files + [f for f in feed_files if os.path.exists(f)] + old_v98_files + legacy_files"""

for vf in verifier_files:
    with open(vf, "r", encoding="utf-8") as f:
        content = f.read()

    # Top CANDIDATES list
    if '"ip/harvest/lists_all.txt"' not in content:
        content = content.replace(
            'CANDIDATES = ["ip/harvest/feeds_raw.txt"',
            'CANDIDATES = ["ip/harvest/lists_all.txt", "ip/harvest/feeds_raw.txt"',
        )

    if old_chunk_gather in content:
        content = content.replace(old_chunk_gather, new_chunk_gather)
    elif "list_files = [os.path.join(REPO, \"ip\", \"harvest\", \"lists_all.txt\")]" not in content:
        print(f"Warning: old_chunk_gather not matched in {vf}")

    with open(vf, "w", encoding="utf-8") as f:
        f.write(content)

print(f"Updated {len(verifier_files)} verifier files.")
