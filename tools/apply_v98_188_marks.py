#!/usr/bin/env python3
import os
import re

REPO_ROOT = r"D:\DEpinFarm"
MASTER = os.path.join(REPO_ROOT, "kaggle", "cl_shodan", "run.py")

with open(MASTER, "r", encoding="utf-8") as f:
    text = f.read()

# 1. Update ENGINE_VER
text = re.sub(r'ENGINE_VER = "[^"]+"', 'ENGINE_VER = "v98.188"', text)

# 2. Fix shard_log signature to accept any kwargs (including flush=True)
old_shard_log = """    def shard_log(msg):
        ts_str = time.strftime('%Y-%m-%d %H:%M:%S')
        formatted = f"[{ts_str}] [SHARD {SHARD_TAG} W{worker_id}] {msg}"
        recent_logs.append(formatted)
        print(formatted, flush=True)"""

new_shard_log = """    def shard_log(msg, *args, **kwargs):
        ts_str = time.strftime('%Y-%m-%d %H:%M:%S')
        formatted = f"[{ts_str}] [SHARD {SHARD_TAG} W{worker_id}] {msg}"
        recent_logs.append(formatted)
        print(formatted, flush=True)"""

assert old_shard_log in text, "old_shard_log not found!"
text = text.replace(old_shard_log, new_shard_log, 1)

# 3. Add stage marks between init and queue
target_init_block = """    shard_log(f"Random IPv4 Looping: Resume offset={offset:,} cands={cands_found:,}")
    write_stage_file("init", offset)
    part_fp = open(part_file, "a", encoding="utf-8")

    start_t = time.time()
    last_stats_t = time.time()

    res_subnets_all = load_subnet_list("res_subnets.txt")
    mob_subnets_all = load_subnet_list("mob_subnets.txt")
    dc_subnets_all = load_subnet_list("dc_subnets.txt")

    # Stride across shards and workers
    res_subnets = [s for idx, s in enumerate(res_subnets_all) if idx % NUM_SHARDS == shard_idx][worker_id::total_workers]
    mob_subnets = [s for idx, s in enumerate(mob_subnets_all) if idx % NUM_SHARDS == shard_idx][worker_id::total_workers]
    dc_subnets = [s for idx, s in enumerate(dc_subnets_all) if idx % NUM_SHARDS == shard_idx][worker_id::total_workers]

    queue_dir = os.path.join(REPO, "ip", "harvest", "queue")
    acks_dir = os.path.join(REPO, "ip", "harvest", "acks")
    os.makedirs(queue_dir, exist_ok=True)
    os.makedirs(acks_dir, exist_ok=True)

    cur_res_idx = 0
    cur_mob_idx = 0
    cur_dc_idx = 0

    print(f"{log_pfx} Candidate Pipeline Loaded: res={len(res_subnets):,} mob={len(mob_subnets):,} dc={len(dc_subnets):,} subnets for Shard {SHARD_TAG} W{worker_id}", flush=True)"""

new_init_block = """    shard_log(f"Random IPv4 Looping: Resume offset={offset:,} cands={cands_found:,}")
    write_stage_file("init", offset)
    write_stage_file("init:open_part_fp", offset)
    part_fp = open(part_file, "a", encoding="utf-8")

    start_t = time.time()
    last_stats_t = time.time()

    write_stage_file("init:load_subnets", offset)
    res_subnets_all = load_subnet_list("res_subnets.txt")
    mob_subnets_all = load_subnet_list("mob_subnets.txt")
    dc_subnets_all = load_subnet_list("dc_subnets.txt")

    write_stage_file("init:stride_subnets", offset)
    # Stride across shards and workers
    res_subnets = [s for idx, s in enumerate(res_subnets_all) if idx % NUM_SHARDS == shard_idx][worker_id::total_workers]
    mob_subnets = [s for idx, s in enumerate(mob_subnets_all) if idx % NUM_SHARDS == shard_idx][worker_id::total_workers]
    dc_subnets = [s for idx, s in enumerate(dc_subnets_all) if idx % NUM_SHARDS == shard_idx][worker_id::total_workers]

    write_stage_file("init:setup_dirs", offset)
    queue_dir = os.path.join(REPO, "ip", "harvest", "queue")
    acks_dir = os.path.join(REPO, "ip", "harvest", "acks")
    os.makedirs(queue_dir, exist_ok=True)
    os.makedirs(acks_dir, exist_ok=True)

    cur_res_idx = 0
    cur_mob_idx = 0
    cur_dc_idx = 0

    write_stage_file("init:pipeline_loaded", offset)
    print(f"{log_pfx} Candidate Pipeline Loaded: res={len(res_subnets):,} mob={len(mob_subnets):,} dc={len(dc_subnets):,} subnets for Shard {SHARD_TAG} W{worker_id}", flush=True)"""

assert target_init_block in text, "target_init_block not found!"
text = text.replace(target_init_block, new_init_block, 1)

# 4. Add stage marks inside consume_queue_stage
target_cqs_top = """    async def consume_queue_stage():
        nonlocal cands_found, offset
        if not os.path.exists(queue_dir):
            return
        q_files = sorted([f for f in os.listdir(queue_dir) if f.startswith("q_") and f.endswith(".txt")])
        if not q_files:
            return
        shard_log(f"[QUEUE STAGE] Found {len(q_files)} queue files to consume before IP scanning", flush=True)

        write_stage_file("queue_consuming", offset)"""

new_cqs_top = """    async def consume_queue_stage():
        nonlocal cands_found, offset
        write_stage_file("queue:check_dir", offset)
        if not os.path.exists(queue_dir):
            write_stage_file("queue:no_dir_skip", offset)
            return
        write_stage_file("queue:list_files", offset)
        q_files = sorted([f for f in os.listdir(queue_dir) if f.startswith("q_") and f.endswith(".txt")])
        if not q_files:
            write_stage_file("queue:no_files_skip", offset)
            return
        write_stage_file(f"queue:found_{len(q_files)}_files", offset)
        shard_log(f"[QUEUE STAGE] Found {len(q_files)} queue files to consume before IP scanning", flush=True)

        write_stage_file("queue_consuming", offset)"""

assert target_cqs_top in text, "target_cqs_top not found!"
text = text.replace(target_cqs_top, new_cqs_top, 1)

# Call before awaiting consume_queue_stage
target_await = """    write_stage_file("init:enter_consume_queue_stage", offset)
    await consume_queue_stage()"""

if "await consume_queue_stage()" in text and "write_stage_file(\"init:enter_consume_queue_stage\", offset)" not in text:
    text = text.replace("    await consume_queue_stage()", "    write_stage_file(\"init:enter_consume_queue_stage\", offset)\n    await consume_queue_stage()", 1)

with open(MASTER, "w", encoding="utf-8") as f:
    f.write(text)

print("Master kaggle/cl_shodan/run.py successfully updated to v98.188.")

# Propagate to all 34 shards
for s in range(34):
    stag = f"{s:02d}"
    shard_run = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{stag}", "run.py")
    shard_content = text
    shard_content = re.sub(r'SHARD_TAG = "[^"]+"', f'SHARD_TAG = "{stag}"', shard_content)
    shard_content = re.sub(r'shard_idx = \d+', f'shard_idx = {s}', shard_content)
    with open(shard_run, "w", encoding="utf-8") as sf:
        sf.write(shard_content)

print("Propagated to all 34 shards (00..33).")

with open(os.path.join(REPO_ROOT, "work", "VERSION"), "w", encoding="utf-8") as vf:
    vf.write("v98.188\n")
print("Updated work/VERSION to v98.188.")
