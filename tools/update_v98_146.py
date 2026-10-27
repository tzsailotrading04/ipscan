import os
import re

ROOT = r"D:\DEpinFarm"

shard_files = [os.path.join(ROOT, "kaggle", "cl_shodan", "run.py")] + [
    os.path.join(ROOT, "kaggle", f"cl_shodan_{i:02d}", "run.py") for i in range(20)
]

new_refill_block = """    async def pool_refill():
        nonlocal pacer
        global PROXY_POOL, POOL_MIN, current_chunk, chunk_handle
        while not STOPPING and (time.time() - START_TIME < HARD_STOP):
            await asyncio.sleep(300)
            if STOPPING:
                break
            try:
                # Sync latest verified files from remote
                try:
                    await asyncio.to_thread(subprocess.run, ["git", "-C", REPO, "pull", "--quiet", "origin", "main"], capture_output=True)
                except Exception:
                    pass

                # Step 1: Re-read pool files fresh each cycle & sample 400
                fresh_cands = load_candidates()
                mine_fresh = fresh_cands[SHARD_IDX::NUM_SHARDS][:20000]
                sample_batch = random.sample(mine_fresh, min(400, len(mine_fresh))) if mine_fresh else []

                shard_cands = []
                cur_chunk_file = os.path.join(REPO, "ip", "harvest", f"shodan_shard_{OUT_PREFIX}{SHARD_TAG}_c{current_chunk:03d}.txt")
                if os.path.exists(cur_chunk_file):
                    try:
                        if chunk_handle:
                            chunk_handle.flush()
                        with open(cur_chunk_file, "r", encoding="utf-8", errors="ignore") as sf:
                            lines = sf.readlines()
                            for l in lines[-500:]:
                                l = l.strip()
                                if l and ":" in l and not l.startswith(("<", "=", ">")):
                                    addr = l.split()[0].split("\\t")[0]
                                    shard_cands.append((addr, "http"))
                    except Exception:
                        pass

                combined = sample_batch + [item for item in shard_cands if item not in sample_batch]
                if not combined:
                    continue

                fresh = await build_pool(combined)
                curr_set = set(PROXY_POOL)
                added = 0
                for item in fresh:
                    # Step 3: Re-add recovered proxies & reset fails/cooldowns
                    FAILS[item] = 0
                    FAILS_UNTIL.pop(item[0], None)
                    BANNED.pop(item[0], None)
                    if item not in curr_set:
                        PROXY_POOL.append(item)
                        curr_set.add(item)
                        added += 1

                if PROXY_POOL:
                    PACER_HI = min(30000.0, max(3000.0, 15.0 * len(PROXY_POOL)))
                    pacer.hi = PACER_HI
                    pacer.lo = max(200.0, PACER_HI * 0.1)
                    pacer.rate = max(pacer.lo, min(pacer.hi, pacer.rate))
                log(f"[refill] tested={len(combined)} (fresh_pool={len(sample_batch)} shard={len(shard_cands)}) live={len(fresh)} added={added} pool={len(PROXY_POOL)} pacer.hi={pacer.hi:.1f}")
            except Exception as e:
                log(f"[refill] error: {e}")"""

old_refill_pattern = re.compile(
    r"    async def pool_refill\(\):[\s\S]*?log\(f\"\[refill\] tested=\{len\(combined\)\}[^\"]+\"\)\s*\n\s*except Exception as e:\s*\n\s*log\(f\"\[refill\] error: \{e\}\"\)"
)

# Cap FAILS multiplier so proxies recover quickly after cooldown
old_fails_calc = "FAILS_UNTIL[addr] = time.monotonic() + min(60.0, 5.0 * FAILS[key])"
new_fails_calc = "FAILS[key] = min(10, FAILS.get(key, 0) + 1)\n                FAILS_UNTIL[addr] = time.monotonic() + min(60.0, 5.0 * FAILS[key])"

for sf in shard_files:
    with open(sf, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(r'ENGINE_VER\s*=\s*"v98\.\d+"', 'ENGINE_VER = "v98.146"', content)

    content, n = old_refill_pattern.subn(new_refill_block, content)
    if n != 1:
        print(f"Warning: pool_refill replaced {n} times in {sf}")

    with open(sf, "w", encoding="utf-8") as f:
        f.write(content)

print(f"Updated {len(shard_files)} shard files to v98.146.")
