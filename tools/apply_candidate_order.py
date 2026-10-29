#!/usr/bin/env python3
r"""
Updates master kaggle/cl_shodan/run.py and all 34 shard files (00..33) with:
1) Candidate order:
   - 1) ip/harvest/queue/ (oldest first, delete file once all shards consumed it)
   - 2) data/res_subnets.txt
   - 3) data/mob_subnets.txt
   - 4) data/dc_subnets.txt
   - 5) random IPv4 as fallback
2) Stride by SHARD_IDX and NUM_SHARDS (34)
3) Version bump to v98.180
4) Verifies and compiles all 35 files
5) Prints the code block and a 34-row table
"""
import os
import re
import sys
import py_compile

REPO_ROOT = r"D:\DEpinFarm"

CANDIDATE_ORDER_BLOCK = '''# ==============================================================================
# CANDIDATE PIPELINE (v98.180 QUEUE-FIRST STRIDED ORDER)
# 1) ip/harvest/queue/ (oldest first, delete file once all shards consumed it)
# 2) data/res_subnets.txt
# 3) data/mob_subnets.txt
# 4) data/dc_subnets.txt
# 5) random IPv4 as fallback
# ==============================================================================
def load_subnet_list(filename):
    paths = [
        os.path.join(REPO, "data", filename),
        os.path.join(os.path.dirname(__file__), "..", "..", "data", filename),
        os.path.join("/kaggle/working/ipscan/data", filename)
    ]
    for p in paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                return [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return []
'''

WORKER_LOOP_CODE = '''    res_subnets_all = load_subnet_list("res_subnets.txt")
    mob_subnets_all = load_subnet_list("mob_subnets.txt")
    dc_subnets_all = load_subnet_list("dc_subnets.txt")

    # Stride across shards and workers
    res_subnets = [s for idx, s in enumerate(res_subnets_all) if idx % NUM_SHARDS == shard_idx][worker_id::total_workers]
    mob_subnets = [s for idx, s in enumerate(mob_subnets_all) if idx % NUM_SHARDS == shard_idx][worker_id::total_workers]
    dc_subnets = [s for idx, s in enumerate(dc_subnets_all) if idx % NUM_SHARDS == shard_idx][worker_id::total_workers]

    queue_dir = os.path.join(REPO, "ip", "harvest", "queue")
    os.makedirs(queue_dir, exist_ok=True)

    cur_res_idx = 0
    cur_mob_idx = 0
    cur_dc_idx = 0

    print(f"{log_pfx} Candidate Pipeline Loaded: res={len(res_subnets):,} mob={len(mob_subnets):,} dc={len(dc_subnets):,} subnets for Shard {SHARD_TAG} W{worker_id}", flush=True)

    def get_candidate_batch():
        nonlocal cur_res_idx, cur_mob_idx, cur_dc_idx
        # Tier 1: Check queue files (oldest first)
        if os.path.exists(queue_dir):
            q_files = sorted([f for f in os.listdir(queue_dir) if f.startswith("q_") and f.endswith(".txt")])
            for qf_name in q_files:
                qf_path = os.path.join(queue_dir, qf_name)
                ack_marker = qf_path + f".ack_{shard_idx}"
                if not os.path.exists(ack_marker):
                    # Read lines and stride
                    lines = []
                    try:
                        with open(qf_path, "r", encoding="utf-8", errors="ignore") as qf:
                            lines = [l.strip() for l in qf if l.strip()]
                    except Exception:
                        pass
                    shard_lines = [l for idx, l in enumerate(lines) if idx % NUM_SHARDS == shard_idx]
                    # Mark acknowledged by this shard
                    try:
                        with open(ack_marker, "w", encoding="utf-8") as af:
                            af.write("1\\n")
                    except Exception:
                        pass
                    # Check if all shards consumed it
                    all_acks = [f for f in os.listdir(queue_dir) if f.startswith(qf_name + ".ack_")]
                    if len(all_acks) >= NUM_SHARDS:
                        try:
                            os.remove(qf_path)
                            for a in all_acks:
                                os.remove(os.path.join(queue_dir, a))
                        except Exception:
                            pass
                    if shard_lines:
                        batch = []
                        for item in shard_lines:
                            parts = item.split()[0].split(":")
                            if len(parts) == 2 and parts[1].isdigit():
                                batch.append((parts[0], int(parts[1]), "QUEUE"))
                        if batch:
                            return batch, "QUEUE"

        # Tier 2: Consumer Residential Subnets
        if cur_res_idx < len(res_subnets):
            sub = res_subnets[cur_res_idx]
            cur_res_idx += 1
            batch = [(f"{sub}.{h}", p, "RES") for h in range(1, 255) for p in DIRECT_PORTS]
            return batch, "RES"

        # Tier 3: Mobile Carrier Subnets
        if cur_mob_idx < len(mob_subnets):
            sub = mob_subnets[cur_mob_idx]
            cur_mob_idx += 1
            batch = [(f"{sub}.{h}", p, "MOB") for h in range(1, 255) for p in DIRECT_PORTS]
            return batch, "MOB"

        # Tier 4: Datacenter Subnets
        if cur_dc_idx < len(dc_subnets):
            sub = dc_subnets[cur_dc_idx]
            cur_dc_idx += 1
            batch = [(f"{sub}.{h}", p, "DC") for h in range(1, 255) for p in DIRECT_PORTS]
            return batch, "DC"

        # Tier 5: Random IPv4 Fallback
        batch_ips = [rand_ipv4() for _ in range(BATCH_SIZE)]
        batch = [(ip, p, "RANDOM") for ip in batch_ips for p in DIRECT_PORTS]
        return batch, "RANDOM"

    # MAIN WORKER EXECUTION LOOP
    while True:
        task_items, current_tier = get_candidate_batch()
        tasks = []
        for ip, p, tier in task_items:
            tasks.append((ip, p, tier, check_port(ip, p)))

        results = await asyncio.gather(*[t[3] for t in tasks], return_exceptions=True)

        for (ip, port, tier, _), res in zip(tasks, results):
            if isinstance(res, tuple) and res[0] is not None:
                passed_port, target = res
                prov = lookup_prov(ip)
                part_fp.write(f"{ip}:{passed_port}\\t{target}\\t{tier}\\t0\\t{prov}\\n")
                part_fp.flush()
                cands_found += 1
                print(f"{log_pfx} [FOUND {tier}] {ip}:{passed_port} ({prov}) via {target} | cands={cands_found}", flush=True)

        offset += len(task_items)
        now = time.time()
        if now - last_stats_t >= 15:
            last_stats_t = now
            dt = max(0.1, now - start_t)
            req_s = (offset) / dt
            with open(prog_file + ".tmp", "w") as f:
                f.write(f"{offset}\\nchunk=1\\n")
            os.replace(prog_file + ".tmp", prog_file)
            with open(stats_file + ".tmp", "w") as f:
                f.write(f"offset={offset}\\ntotal=4294967296\\ncands={cands_found}\\nerrno99={STAT_ERRNO99}\\ntimeout={STAT_TIMEOUT}\\nrefused={STAT_REFUSED}\\nreq_s={req_s:.1f}\\nstage={current_tier.lower()}_loop\\n")
            os.replace(stats_file + ".tmp", stats_file)
'''

def update_file(filepath, shard_idx):
    with open(filepath, "r", encoding="utf-8") as f:
        code = f.read()

    # Update ENGINE_VER
    code = re.sub(r'ENGINE_VER\s*=\s*"[^"]*"', 'ENGINE_VER = "v98.180"', code)

    # Ensure NUM_SHARDS = 34
    code = re.sub(r'NUM_SHARDS\s*=\s*\d+', 'NUM_SHARDS = 34', code)

    # Ensure SHARD_IDX is correct
    code = re.sub(r'SHARD_IDX\s*=\s*\d+', f'SHARD_IDX = {shard_idx}', code)

    # Insert CANDIDATE_ORDER_BLOCK before rand_ipv4()
    if "# CANDIDATE PIPELINE" not in code:
        rand_marker = "# Routable Random IPv4 Generator"
        if rand_marker in code:
            code = code.replace(rand_marker, CANDIDATE_ORDER_BLOCK + "\n" + rand_marker)
        else:
            code = CANDIDATE_ORDER_BLOCK + "\n" + code

    # Replace worker execution loop
    loop_start_marker = "    # ENDLESS RANDOM IPv4 LOOP (Never Idle)\n    while True:"
    loop_end_marker = "# ==============================================================================\n# FLEET MASTER SUPERVISOR"
    if loop_start_marker in code and loop_end_marker in code:
        s_pos = code.find(loop_start_marker)
        e_pos = code.find(loop_end_marker)
        code = code[:s_pos] + WORKER_LOOP_CODE + "\n\n" + code[e_pos:]

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(code)

def main():
    print("=" * 80)
    print("  UPDATING CANDIDATE PIPELINE ACROSS MASTER & 34 SHARDS")
    print("=" * 80)

    # Master cl_shodan
    master_path = os.path.join(REPO_ROOT, "kaggle", "cl_shodan", "run.py")
    update_file(master_path, 0)
    py_compile.compile(master_path, doraise=True)
    print(f"  Master kaggle/cl_shodan/run.py updated and compiled OK.")

    # 34 Shards
    table_rows = []
    for i in range(34):
        stag = f"{i:02d}"
        shard_path = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{stag}", "run.py")
        update_file(shard_path, i)
        try:
            py_compile.compile(shard_path, doraise=True)
            comp = "OK"
        except Exception as e:
            comp = f"FAIL: {e}"

        # Verify attributes
        with open(shard_path, "r", encoding="utf-8") as f:
            c = f.read()
        s_idx_val = re.search(r'SHARD_IDX\s*=\s*(\d+)', c).group(1)
        num_s_val = re.search(r'NUM_SHARDS\s*=\s*(\d+)', c).group(1)
        has_pipeline = "CANDIDATE PIPELINE" in c
        has_queue = "get_candidate_batch" in c

        table_rows.append((stag, s_idx_val, num_s_val, "YES" if (has_pipeline and has_queue) else "NO", comp))

    print("\n" + "=" * 80)
    print(f"{'Shard File':<20} | {'SHARD_IDX':<10} | {'NUM_SHARDS':<10} | {'Pipeline Applied':<18} | {'Compile'}")
    print("-" * 80)
    all_ok = True
    for stag, s_idx, num_s, applied, comp in table_rows:
        print(f"cl_shodan_{stag}/run.py   | {s_idx:<10} | {num_s:<10} | {applied:<18} | {comp}")
        if s_idx != str(int(stag)) or num_s != "34" or applied != "YES" or comp != "OK":
            all_ok = False

    print("=" * 80)
    if all_ok:
        print("ALL 35 FILES UPDATED AND COMPILED SUCCESSFULLY!")
    else:
        print("COMPILE_FAIL")
        sys.exit(1)

if __name__ == "__main__":
    main()
