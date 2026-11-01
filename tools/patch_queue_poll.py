#!/usr/bin/env python3
"""
Patch all kaggle/cl_shodan_*/run.py files to:
1. Bump ENGINE_VER to v98.189.
2. Add check_unconsumed_queue() to inspect ip/harvest/queue for files this shard hasn't consumed (using cache/qcursor).
3. Inside the scanning loop, every 120s (2 minutes), fetch origin/main and checkout ip/harvest/queue.
4. If unconsumed queue files exist, pause scan loop and re-enter consume_queue_stage() until drained.
5. Compile-check every patched file.
"""

import os
import sys
import glob
import py_compile

REPO_ROOT = r"D:\DEpinFarm"

def patch_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update ENGINE_VER
    content = content.replace('ENGINE_VER = "v98.188"', 'ENGINE_VER = "v98.189"')

    # 2. Add check_unconsumed_queue function
    target_q = """        return _rem

    write_stage_file("init:enter_consume_queue_stage", offset)"""

    replacement_q = """        return _rem

    def check_unconsumed_queue():
        if not os.path.exists(queue_dir):
            return False
        q_files = sorted([f for f in os.listdir(queue_dir) if f.startswith("q_") and f.endswith(".txt")])
        qcur_dir = os.path.join(REPO, "cache", "qcursor")
        for _f in q_files:
            _p = os.path.join(qcur_dir, f"{_f}.cur_{shard_idx}")
            try:
                if not (os.path.exists(_p) and open(_p, "r", encoding="utf-8").read().strip() == "DONE"):
                    return True
            except Exception:
                return True
        return False

    write_stage_file("init:enter_consume_queue_stage", offset)"""

    # 3. Add periodic fetch & check inside scanning loop
    target_scan = """    # MAIN WORKER EXECUTION LOOP
    write_stage_file("scanning_start", offset)
    while True:
        task_items, current_tier = get_candidate_batch()"""

    replacement_scan = """    # MAIN WORKER EXECUTION LOOP
    write_stage_file("scanning_start", offset)
    last_queue_poll_t = time.time()
    QUEUE_POLL_INTERVAL = 120  # Poll origin/main every 2 minutes

    while True:
        now_poll = time.time()
        if (now_poll - last_queue_poll_t) >= QUEUE_POLL_INTERVAL:
            last_queue_poll_t = now_poll
            try:
                subprocess.run(["git", "fetch", "--depth", "1", "origin", "main"], cwd=REPO, capture_output=True, timeout=90)
                subprocess.run(["git", "checkout", "FETCH_HEAD", "--", "ip/harvest/queue"], cwd=REPO, capture_output=True, timeout=90)
            except Exception:
                pass
            if check_unconsumed_queue():
                shard_log(f"[QUEUE DETECTED] Unconsumed queue file(s) found in ip/harvest/queue/. Pausing scan loop to process queue.", flush=True)
                write_stage_file("queue_interrupt", offset)
                while True:
                    _left = await consume_queue_stage()
                    if not _left:
                        break
                    await asyncio.sleep(1)
                write_stage_file("scanning_resume", offset)

        task_items, current_tier = get_candidate_batch()"""

    # Check for CRLF vs LF
    if target_q not in content:
        target_q_crlf = target_q.replace("\n", "\r\n")
        replacement_q_crlf = replacement_q.replace("\n", "\r\n")
        if target_q_crlf in content:
            content = content.replace(target_q_crlf, replacement_q_crlf, 1)
        else:
            print(f"Warning: target_q not found in {file_path}")
    else:
        content = content.replace(target_q, replacement_q, 1)

    if target_scan not in content:
        target_scan_crlf = target_scan.replace("\n", "\r\n")
        replacement_scan_crlf = replacement_scan.replace("\n", "\r\n")
        if target_scan_crlf in content:
            content = content.replace(target_scan_crlf, replacement_scan_crlf, 1)
        else:
            print(f"Warning: target_scan not found in {file_path}")
    else:
        content = content.replace(target_scan, replacement_scan, 1)

    with open(file_path, "w", encoding="utf-8", newline="") as f:
        f.write(content)

def main():
    shard_files = sorted(glob.glob(os.path.join(REPO_ROOT, "kaggle", "cl_shodan_*", "run.py")))
    print(f"Found {len(shard_files)} shard files to patch.")

    # Patch files
    for sf in shard_files:
        patch_file(sf)

    # Compile check all 30 active shards (and any others)
    print("\n--- Compile-checking all shard run.py files ---")
    compiled_ok = 0
    compiled_err = 0
    for sf in shard_files:
        try:
            py_compile.compile(sf, doraise=True)
            compiled_ok += 1
        except Exception as e:
            print(f"COMPILE ERROR in {sf}: {e}")
            compiled_err += 1

    print(f"Result: {compiled_ok}/{len(shard_files)} compiled successfully. Errors: {compiled_err}")
    if compiled_err > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
