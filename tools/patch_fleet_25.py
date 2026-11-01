import os
import re
import glob

REPO_ROOT = r"D:\DEpinFarm"

NEW_CONSUME_QUEUE_STAGE = '''    async def consume_queue_stage():
        nonlocal cands_found, offset
        write_stage_file("queue:check_dir", offset)
        if not os.path.exists(queue_dir):
            write_stage_file("queue:no_dir_skip", offset)
            return 0
        write_stage_file("queue:list_files", offset)
        q_files = sorted([f for f in os.listdir(queue_dir) if f.startswith("q_") and f.endswith(".txt")])
        if not q_files:
            write_stage_file("queue:no_files_skip", offset)
            return 0
        write_stage_file(f"queue:found_{len(q_files)}_files", offset)
        shard_log(f"[QUEUE STAGE] Found {len(q_files)} queue files to consume before IP scanning", flush=True)

        write_stage_file("queue_consuming", offset)
        queue_start_t = time.time()
        QUEUE_WALLCLOCK_LIMIT = 120.0  # Wall-clock limit of 120 seconds per cycle
        failed_file = os.path.join(REPO, "ip", "harvest", f"queue_failed_part_{SHARD_TAG}.txt")
        SLICE_SIZE = 2000  # Per-shard slice ceiling: 2,000 lines per slice

        for qf_name in q_files:
            qf_path = os.path.join(queue_dir, qf_name)
            ack_file = os.path.join(acks_dir, f"{qf_name}.ack_{shard_idx}")
            qcur_dir = os.path.join(REPO, "cache", "qcursor")
            os.makedirs(qcur_dir, exist_ok=True)
            qcur_file = os.path.join(qcur_dir, f"{qf_name}.cur_{shard_idx}")
            _qc = "0"
            try:
                if os.path.exists(qcur_file):
                    with open(qcur_file, "r", encoding="utf-8") as _qcf:
                        _qc = _qcf.read().strip() or "0"
            except Exception:
                _qc = "0"
            if _qc == "DONE":
                continue

            lines = []
            try:
                with open(qf_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [l.strip() for l in f if l.strip()]
            except Exception:
                continue

            shard_slice = [l for idx, l in enumerate(lines) if idx % NUM_SHARDS == shard_idx]
            worker_slice = shard_slice[worker_id::total_workers]
            try:
                _start = int(_qc)
            except Exception:
                _start = 0
            if _start >= len(worker_slice):
                try:
                    with open(qcur_file, "w", encoding="utf-8") as _qcw:
                        _qcw.write("DONE\\n")
                except Exception:
                    pass
                continue

            # Stagger: Before each queue slice, sleep a random 0 to 30 seconds
            stagger_sleep = random.uniform(0.0, 30.0)
            shard_log(f"[STAGGER] Sleeping {stagger_sleep:.1f}s before consuming slice of {qf_name}...", flush=True)
            await asyncio.sleep(stagger_sleep)

            shard_log(f"[QUEUE STAGE] Consuming {qf_name}: total={len(lines)} shard_slice={len(shard_slice)} worker_slice={len(worker_slice)} resume={_start}", flush=True)
            timed_out = False
            write_stage_file(f"queue_file_{qf_name}", offset)

            for i in range(_start, len(worker_slice), SLICE_SIZE):
                slice_start_t = time.time()
                write_stage_file(f"queue_slice_{qf_name}_{i}", offset)

                # Wall-clock limit check
                if (time.time() - queue_start_t) >= QUEUE_WALLCLOCK_LIMIT:
                    shard_log(f"[QUEUE TIMEOUT] Wall-clock limit ({QUEUE_WALLCLOCK_LIMIT}s) expired ({time.time() - queue_start_t:.1f}s). Abandoning remainder of queue slice, writing ack, and falling through to scanning.", flush=True)
                    timed_out = True
                    break

                chunk = worker_slice[i:i + SLICE_SIZE]
                tasks = []
                batch_start_t = time.time()
                for item in chunk:
                    parts = item.split()[0].split(":")
                    if len(parts) == 2 and parts[1].isdigit():
                        ip = parts[0]
                        port = int(parts[1])
                        tasks.append((ip, port, check_port(ip, port)))

                if tasks:
                    results = await asyncio.gather(*[t[2] for t in tasks], return_exceptions=True)
                    failed_items = []
                    for (ip, port, _), res in zip(tasks, results):
                        if isinstance(res, tuple) and res[0] is not None:
                            passed_port, target = res
                            prov = lookup_prov(ip)
                            part_fp.write(f"{ip}:{passed_port}\\t{target}\\tQUEUE\\t0\\t{prov}\\n")
                            part_fp.flush()
                            cands_found += 1
                            shard_log(f"[FOUND QUEUE] {ip}:{passed_port} ({prov}) via {target} | cands={cands_found}", flush=True)
                        else:
                            failed_items.append(f"{ip}:{port}\\n")
                    if failed_items:
                        try:
                            with open(failed_file, "a", encoding="utf-8") as ffp:
                                ffp.writelines(failed_items)
                        except Exception:
                            pass
                    offset += len(tasks)

                # Rate Pacer: cap at PACER_HI (150 ips/sec)
                p_dt = time.time() - batch_start_t
                p_min = len(tasks) / PACER_HI if PACER_HI > 0 else 0
                if p_dt < p_min:
                    await asyncio.sleep(p_min - p_dt)

                try:
                    with open(qcur_file, "w", encoding="utf-8") as _qcw2:
                        _qcw2.write(f"{min(i + SLICE_SIZE, len(worker_slice))}\\n")
                except Exception:
                    pass

                # Hourly per-shard reporting: record running stats after every slice
                last_slice_seconds = round(time.time() - slice_start_t, 2)
                queue_lines_left = len(worker_slice) - min(i + SLICE_SIZE, len(worker_slice))
                for remaining_qf in q_files[q_files.index(qf_name) + 1:]:
                    try:
                        with open(os.path.join(queue_dir, remaining_qf), "r", encoding="utf-8", errors="ignore") as _rf:
                            r_lines = [1 for _ in _rf if _.strip()]
                            queue_lines_left += len([l for idx, l in enumerate(r_lines) if idx % NUM_SHARDS == shard_idx][worker_id::total_workers])
                    except Exception:
                        pass

                shard_counters["scanned"] = offset
                shard_counters["genuine"] = cands_found
                shard_counters["errno99"] = STAT_ERRNO99
                shard_counters["other"] = STAT_OTHER
                shard_counters["queue_lines_left"] = queue_lines_left
                shard_counters["last_slice_seconds"] = last_slice_seconds

                per1000 = f"{(shard_counters['genuine'] / max(1, shard_counters['scanned']) * 1000):.2f}"
                iso_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                stats_line = f"{iso_time} {shard_counters['scanned']} {shard_counters['genuine']} {per1000} {shard_counters['errno99']} {shard_counters['other']} {shard_counters['queue_lines_left']} {shard_counters['last_slice_seconds']}\\n"

                work_dir = os.path.join(REPO, "work")
                os.makedirs(work_dir, exist_ok=True)
                sh_stats_file = os.path.join(work_dir, f"sh{SHARD_TAG}_stats.txt")
                try:
                    with open(sh_stats_file + ".tmp", "w", encoding="utf-8") as sf:
                        sf.write(stats_line)
                    os.replace(sh_stats_file + ".tmp", sh_stats_file)
                except Exception:
                    pass

                # Check limit after batch completion
                if (time.time() - queue_start_t) >= QUEUE_WALLCLOCK_LIMIT:
                    shard_log(f"[QUEUE TIMEOUT] Wall-clock limit ({QUEUE_WALLCLOCK_LIMIT}s) expired ({time.time() - queue_start_t:.1f}s). Abandoning remainder of queue slice, writing ack, and falling through to scanning.", flush=True)
                    timed_out = True
                    break

            # Mark acknowledged only when this shard's whole slice is finished
            try:
                if (not timed_out) and ((i + SLICE_SIZE) >= len(worker_slice)):
                    with open(qcur_file, "w", encoding="utf-8") as _qcw3:
                        _qcw3.write("DONE\\n")
                    with open(ack_file, "w", encoding="utf-8") as af:
                        af.write("1\\n")
            except Exception:
                pass

            # Check if all shards have passed it, then delete
            acks = [f for f in os.listdir(acks_dir) if f.startswith(f"{qf_name}.ack_") and not f.endswith(".tmp")]
            if len(acks) >= NUM_SHARDS:
                try:
                    os.remove(qf_path)
                    for a in acks:
                        os.remove(os.path.join(acks_dir, a))
                    print(f"{log_pfx} [QUEUE STAGE] {qf_name} consumed by all {NUM_SHARDS} shards and removed.", flush=True)
                except Exception:
                    pass

            # If timed out, break out of queue files loop and fall through to scanning
            if timed_out:
                break

        _rem = 0
        for _f in q_files:
            _p = os.path.join(REPO, "cache", "qcursor", f"{_f}.cur_{shard_idx}")
            try:
                if not (os.path.exists(_p) and open(_p, "r", encoding="utf-8").read().strip() == "DONE"):
                    _rem += 1
            except Exception:
                _rem += 1
        return _rem
'''

def patch_shard(shard_num):
    fpath = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{shard_num:02d}", "run.py")
    if not os.path.exists(fpath):
        print(f"File not found: {fpath}")
        return False

    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update NUM_SHARDS, CONC, PACER_HI
    content = re.sub(r'NUM_SHARDS\s*=\s*\d+', 'NUM_SHARDS = 25', content)
    
    # Replace PROBE_CONCURRENCY block
    if 'CONC =' in content:
        content = re.sub(r'CONC\s*=\s*\d+', 'CONC = 600', content)
        content = re.sub(r'PACER_HI\s*=\s*[\d\.]+', 'PACER_HI = 150.0', content)
        content = re.sub(r'PROBE_CONCURRENCY\s*=\s*\S+', 'PROBE_CONCURRENCY = CONC', content)
    else:
        content = re.sub(
            r'PROBE_CONCURRENCY\s*=\s*\d+',
            'CONC = 600\nPACER_HI = 150.0\nPROBE_CONCURRENCY = CONC',
            content
        )

    # 2. Add shard_counters dict initialization in run_worker
    if 'shard_counters = {' not in content:
        target_str = 'STAT_OTHER = 0\n'
        replacement = target_str + '\n    shard_counters = {\n        "scanned": 0,\n        "genuine": 0,\n        "errno99": 0,\n        "other": 0,\n        "queue_lines_left": 0,\n        "last_slice_seconds": 0.0\n    }\n'
        if target_str in content:
            content = content.replace(target_str, replacement, 1)

    # 3. Replace consume_queue_stage
    start_str = "    async def consume_queue_stage():"
    end_str = "    def check_unconsumed_queue():"
    s_idx = content.find(start_str)
    e_idx = content.find(end_str)
    if s_idx != -1 and e_idx != -1:
        content = content[:s_idx] + NEW_CONSUME_QUEUE_STAGE + "\n" + content[e_idx:]
    else:
        print(f"Warning: Could not replace consume_queue_stage in shard {shard_num}")

    # 4. Add work/shNN_stats.txt to git_sync_and_push patterns
    if 'f"work/sh{SHARD_TAG}_stats.txt"' not in content:
        content = content.replace(
            'f"ip/harvest/queue_failed_part_{SHARD_TAG}*.txt",',
            'f"ip/harvest/queue_failed_part_{SHARD_TAG}*.txt",\n            f"work/sh{SHARD_TAG}_stats.txt",'
        )

    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)

    return True

if __name__ == "__main__":
    # Patch all shards 00 through 28 (including all 25 active shards)
    count = 0
    for s in range(29):
        if patch_shard(s):
            count += 1
    print(f"Successfully patched {count} run.py files.")
