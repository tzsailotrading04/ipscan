import os
import re

ROOT = r"D:\DEpinFarm"

shard_files = [os.path.join(ROOT, "kaggle", "cl_shodan", "run.py")] + [
    os.path.join(ROOT, "kaggle", f"cl_shodan_{i:02d}", "run.py") for i in range(20)
]

new_load_candidates = '''def load_candidates():
    """Newest-first verified entries, cycle-filtered and latency-filtered:
    1. Read cycle field (last column).
    2. Discard entries more than 5 cycles behind the highest seen.
    3. Sort candidates descending by cycle (newest first).
    4. Apply FAST/MED latency filter.
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

    # Cutoff: discard entries whose cycle is more than 5 cycles behind highest seen
    cutoff = max(0, max_cycle - 5)
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

    # Filter FAST and MED
    fast_entries = []
    med_entries = []
    slow_entries = []
    for addr, proto, ms, cls, cycle in candidates:
        if cls == "FAST" or ms < 1000:
            fast_entries.append((addr, proto, ms, "FAST", cycle))
        elif cls == "MED" or ms < 3000:
            med_entries.append((addr, proto, ms, "MED", cycle))
        else:
            slow_entries.append((addr, proto, ms, "SLOW", cycle))

    pool_cands = fast_entries + med_entries
    slow_used = 0
    if len(pool_cands) < 200 and slow_entries:
        slow_entries.sort(key=lambda x: x[2])
        needed = 200 - len(pool_cands)
        fill_slow = slow_entries[:needed]
        pool_cands += fill_slow
        slow_used = len(fill_slow)

    global PROXY_CLASS
    PROXY_CLASS = {x[0]: x[3] for x in pool_cands}

    # STEP 4: Log pool_pass_rate as kept/parsed
    log(f"pool_pass_rate={len(pool_cands)}/{total_parsed} ({100.0 * len(pool_cands) / max(1, total_parsed):.1f}%) | FAST={len(fast_entries)} MED={len(med_entries)} SLOW={slow_used}")

    out = [(x[0], x[1]) for x in pool_cands]
    return out'''

old_load_pattern = re.compile(r'def load_candidates\(\):[\s\S]*?return out')

for sf in shard_files:
    with open(sf, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(r'ENGINE_VER\s*=\s*"v98\.\d+"', 'ENGINE_VER = "v98.144"', content)

    content, n = old_load_pattern.subn(new_load_candidates, content)
    if n != 1:
        print(f"Warning: load_candidates replaced {n} times in {sf}")

    # Keep newest-first slice order
    content = content.replace(
        "mine = random.Random(777).sample(mine, min(20000, len(mine)))",
        "mine = mine[:20000]",
    )

    with open(sf, "w", encoding="utf-8") as f:
        f.write(content)

print(f"Updated all {len(shard_files)} shard files to v98.144.")
