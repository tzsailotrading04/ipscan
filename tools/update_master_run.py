import os

master_path = r'D:\DEpinFarm\kaggle\cl_shodan\run.py'
with open(master_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update ports and engine version
old_ports = 'DIRECT_PORTS = [443, 3128, 8080, 80, 8888, 4145, 6588, 3129, 8001, 8081, 1081, 8889, 8119, 8123, 8008, 8128, 9999, 10000, 7000, 7001]'
new_ports = 'DIRECT_PORTS = [443, 3128, 8080, 8888, 1080, 8118, 80, 4145]'
assert old_ports in content, 'old_ports not found'
content = content.replace(old_ports, new_ports)
content = content.replace('ENGINE_VER = "v98.180"', 'ENGINE_VER = "v98.182"')

# 2. Add consume_queue_stage before while True:
queue_stage_code = '''
    # ==============================================================================
    # STAGE 0: QUEUE CONSUMING STAGE (RUNS BEFORE IP SCANNING)
    # ==============================================================================
    async def consume_queue_stage():
        nonlocal cands_found, offset
        if not os.path.exists(queue_dir):
            return
        q_files = sorted([f for f in os.listdir(queue_dir) if f.startswith("q_") and f.endswith(".txt")])
        if not q_files:
            return
        print(f"{log_pfx} [QUEUE STAGE] Found {len(q_files)} queue files to consume before IP scanning", flush=True)

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

            for i in range(0, len(worker_slice), 500):
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

            # Mark acknowledged by this shard
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

    await consume_queue_stage()
'''

target_anchor = '    # MAIN WORKER EXECUTION LOOP\n    while True:'
assert target_anchor in content, 'target_anchor not found'
content = content.replace(target_anchor, queue_stage_code + '\n' + target_anchor)

with open(master_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('kaggle/cl_shodan/run.py updated successfully!')
