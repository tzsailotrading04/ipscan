#!/usr/bin/env python3
import os
import re
import glob

REPO_ROOT = r"D:\DEpinFarm"
MASTER = os.path.join(REPO_ROOT, "kaggle", "cl_shodan", "run.py")

with open(MASTER, "r", encoding="utf-8") as f:
    text = f.read()

# 1. Bump version
text = re.sub(r'ENGINE_VER = "[^"]+"', 'ENGINE_VER = "v98.187"', text)

# 2. Add recent_logs, shard_log, write_stage_file definition in run_worker
target_anchor = '    print(f"{log_pfx} Random IPv4 Looping: Resume offset={offset:,} cands={cands_found:,}", flush=True)'

replacement_anchor = '''    recent_logs = collections.deque(maxlen=10)

    def shard_log(msg):
        ts_str = time.strftime('%Y-%m-%d %H:%M:%S')
        formatted = f"[{ts_str}] [SHARD {SHARD_TAG} W{worker_id}] {msg}"
        recent_logs.append(formatted)
        print(formatted, flush=True)

    def write_stage_file(stage, cur_offset):
        if worker_id != 0:
            return
        stage_file = os.path.join(REPO, "ip", "harvest", f"stage_{SHARD_TAG}.txt")
        now_ts = int(time.time())
        last_5 = list(recent_logs)[-5:]
        lines = [
            f"stage={stage}",
            f"ts={now_ts}",
            f"offset={cur_offset}",
            "--- LAST 5 LOG LINES ---"
        ]
        for l in last_5:
            lines.append(l)
        content = "\\n".join(lines) + "\\n"
        try:
            with open(stage_file + ".tmp", "w", encoding="utf-8") as sf:
                sf.write(content)
            os.replace(stage_file + ".tmp", stage_file)
        except Exception:
            pass

    shard_log(f"Random IPv4 Looping: Resume offset={offset:,} cands={cands_found:,}")
    write_stage_file("init", offset)'''

if target_anchor in text:
    text = text.replace(target_anchor, replacement_anchor, 1)
else:
    print("Warning: target_anchor not found!")

# 3. Replace print with shard_log in consume_queue_stage and scanning
text = text.replace('print(f"{log_pfx} [QUEUE STAGE] Found', 'shard_log(f"[QUEUE STAGE] Found')
text = text.replace('print(f"{log_pfx} [QUEUE STAGE] Consuming', 'shard_log(f"[QUEUE STAGE] Consuming')
text = text.replace('print(f"{log_pfx} [QUEUE TIMEOUT]', 'shard_log(f"[QUEUE TIMEOUT]')
text = text.replace('print(f"{log_pfx} [FOUND QUEUE]', 'shard_log(f"[FOUND QUEUE]')
text = text.replace('print(f"{log_pfx} [FOUND {tier}]', 'shard_log(f"[FOUND {tier}]')

# 4. Insert write_stage_file at top of consume_queue_stage
target_q_top = '        queue_start_t = time.time()'
replacement_q_top = '''        write_stage_file("queue_consuming", offset)
        queue_start_t = time.time()'''
if target_q_top in text:
    text = text.replace(target_q_top, replacement_q_top, 1)

# Inside queue stage loop iterations
target_q_chunk = '            for i in range(0, len(worker_slice), 500):'
replacement_q_chunk = '''            write_stage_file(f"queue_file_{qf_name}", offset)
            for i in range(0, len(worker_slice), 500):
                write_stage_file(f"queue_slice_{qf_name}_{i}", offset)'''
if target_q_chunk in text:
    text = text.replace(target_q_chunk, replacement_q_chunk, 1)

# After queue stage
target_q_done = '    await consume_queue_stage()'
replacement_q_done = '''    await consume_queue_stage()
    write_stage_file("queue_done", offset)'''
if target_q_done in text:
    text = text.replace(target_q_done, replacement_q_done, 1)

# Top of scanning loop and inside iteration
target_loop_top = '''    # MAIN WORKER EXECUTION LOOP
    while True:
        task_items, current_tier = get_candidate_batch()'''

replacement_loop_top = '''    # MAIN WORKER EXECUTION LOOP
    write_stage_file("scanning_start", offset)
    while True:
        task_items, current_tier = get_candidate_batch()
        write_stage_file(f"{current_tier.lower()}_loop", offset)'''

if target_loop_top in text:
    text = text.replace(target_loop_top, replacement_loop_top, 1)

target_loop_iter = '''        offset += len(task_items)
        now = time.time()'''

replacement_loop_iter = '''        offset += len(task_items)
        write_stage_file(f"{current_tier.lower()}_loop", offset)
        now = time.time()'''

if target_loop_iter in text:
    text = text.replace(target_loop_iter, replacement_loop_iter, 1)

# 5. In master supervisor: ensure commit message reflects v98.187 stage heartbeat
text = text.replace('random_loop"', 'stage_heartbeat"')

with open(MASTER, "w", encoding="utf-8") as f:
    f.write(text)

print("Master kaggle/cl_shodan/run.py successfully updated to v98.187.")

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

# Update work/VERSION
with open(os.path.join(REPO_ROOT, "work", "VERSION"), "w", encoding="utf-8") as vf:
    vf.write("v98.187\n")
print("Updated work/VERSION to v98.187.")
