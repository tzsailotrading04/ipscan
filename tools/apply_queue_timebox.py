import os, py_compile

REPO = r"D:\DEpinFarm"
master_file = os.path.join(REPO, "kaggle", "cl_shodan", "run.py")

with open(master_file, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update ENGINE_VER
content = content.replace('ENGINE_VER = "v98.184"', 'ENGINE_VER = "v98.185"')

start_marker = "    # STAGE 0: QUEUE CONSUMING STAGE (RUNS BEFORE IP SCANNING)"
end_marker = "    await consume_queue_stage()"

idx1 = content.find(start_marker)
idx2 = content.find(end_marker)

assert idx1 != -1 and idx2 != -1, "Markers not found"

new_queue_block = """    # STAGE 0: QUEUE CONSUMING STAGE (RUNS BEFORE IP SCANNING)
    # ==============================================================================
    async def consume_queue_stage():
        nonlocal cands_found, offset
        if not os.path.exists(queue_dir):
            return
        q_files = sorted([f for f in os.listdir(queue_dir) if f.startswith("q_") and f.endswith(".txt")])
        if not q_files:
            return
        print(f"{log_pfx} [QUEUE STAGE] Found {len(q_files)} queue files to consume before IP scanning", flush=True)

        queue_start_t = time.time()
        QUEUE_WALLCLOCK_LIMIT = 120.0  # Wall-clock limit of 120 seconds per cycle

        for qf_name in q_files:
            qf_path = os.path.join(queue_dir, qf_name)
            ack_file = os.path.join(queue_dir, f"{qf_name}.ack_{shard_idx}")
            if os.path.exists(ack_file):
                continue

            lines = []
            try:
                with open(qf_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [l.strip() for l in f if l.strip()]
            except Exception:
                continue

            # Each shard takes its stride slice across NUM_SHARDS (34)
            shard_slice = [l for idx, l in enumerate(lines) if idx % NUM_SHARDS == shard_idx]
            worker_slice = shard_slice[worker_id::total_workers]

            print(f"{log_pfx} [QUEUE STAGE] Consuming {qf_name}: total={len(lines)} shard_slice={len(shard_slice)} worker_slice={len(worker_slice)}", flush=True)

            timed_out = False
            for i in range(0, len(worker_slice), 500):
                # Wall-clock limit check
                if (time.time() - queue_start_t) >= QUEUE_WALLCLOCK_LIMIT:
                    print(f"{log_pfx} [QUEUE TIMEOUT] Wall-clock limit ({QUEUE_WALLCLOCK_LIMIT}s) expired ({time.time() - queue_start_t:.1f}s). Abandoning remainder of queue slice, writing ack, and falling through to scanning.", flush=True)
                    timed_out = True
                    break

                chunk = worker_slice[i:i + 500]
                tasks = []
                for item in chunk:
                    parts = item.split()[0].split(":")
                    if len(parts) == 2 and parts[1].isdigit():
                        ip = parts[0]
                        port = int(parts[1])
                        tasks.append((ip, port, check_port(ip, port)))

                if tasks:
                    results = await asyncio.gather(*[t[2] for t in tasks], return_exceptions=True)
                    for (ip, port, _), res in zip(tasks, results):
                        if isinstance(res, tuple) and res[0] is not None:
                            passed_port, target = res
                            prov = lookup_prov(ip)
                            part_fp.write(f"{ip}:{passed_port}\\t{target}\\tQUEUE\\t0\\t{prov}\\n")
                            part_fp.flush()
                            cands_found += 1
                            print(f"{log_pfx} [FOUND QUEUE] {ip}:{passed_port} ({prov}) via {target} | cands={cands_found}", flush=True)
                    offset += len(tasks)

                # Check limit after batch completion
                if (time.time() - queue_start_t) >= QUEUE_WALLCLOCK_LIMIT:
                    print(f"{log_pfx} [QUEUE TIMEOUT] Wall-clock limit ({QUEUE_WALLCLOCK_LIMIT}s) expired ({time.time() - queue_start_t:.1f}s). Abandoning remainder of queue slice, writing ack, and falling through to scanning.", flush=True)
                    timed_out = True
                    break

            # Mark acknowledged by this shard (always written, including on expiry)
            try:
                with open(ack_file, "w", encoding="utf-8") as af:
                    af.write("1\\n")
            except Exception:
                pass

            # Check if all 34 shards have passed it, then delete
            acks = [f for f in os.listdir(queue_dir) if f.startswith(f"{qf_name}.ack_") and not f.endswith(".tmp")]
            if len(acks) >= NUM_SHARDS:
                try:
                    os.remove(qf_path)
                    for a in acks:
                        os.remove(os.path.join(queue_dir, a))
                    print(f"{log_pfx} [QUEUE STAGE] {qf_name} consumed by all {NUM_SHARDS} shards and removed.", flush=True)
                except Exception:
                    pass

            # If timed out, break out of queue files loop and fall through to scanning
            if timed_out:
                break
\n"""

content = content[:idx1] + new_queue_block + content[idx2:]

with open(master_file, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated master template kaggle/cl_shodan/run.py successfully.")

# Propagate to all 34 shards
for i in range(34):
    shard_tag = f"{i:02d}"
    shard_file = os.path.join(REPO, "kaggle", f"cl_shodan_{shard_tag}", "run.py")
    shard_code = content.replace("SHARD_IDX = 0\n", f"SHARD_IDX = {i}\n").replace("SHARD_IDX = 0\r\n", f"SHARD_IDX = {i}\r\n")
    with open(shard_file, "w", encoding="utf-8") as sf:
        sf.write(shard_code)

print("Propagated to all 34 shards.")

# Update work/VERSION to v98.185
with open(os.path.join(REPO, "work", "VERSION"), "w", encoding="utf-8") as vf:
    vf.write("v98.185\n")
print("Updated work/VERSION to v98.185.")
