import pathlib, sys

P = pathlib.Path("kaggle")
R = []

OLD7 = "import glob"
NEW7 = "import glob\nimport subprocess"

OLD6A = 'write_stage_file("queue:no_dir_skip", offset)\n            return'
NEW6A = 'write_stage_file("queue:no_dir_skip", offset)\n            return 0'
OLD6B = 'write_stage_file("queue:no_files_skip", offset)\n            return'
NEW6B = 'write_stage_file("queue:no_files_skip", offset)\n            return 0'

OLD1 = '''            ack_file = os.path.join(acks_dir, f"{qf_name}.ack_{shard_idx}")
            if os.path.exists(ack_file):
                continue'''
NEW1 = '''            ack_file = os.path.join(acks_dir, f"{qf_name}.ack_{shard_idx}")
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
                continue'''

OLD2 = '''            worker_slice = shard_slice[worker_id::total_workers]

            shard_log(f"[QUEUE STAGE] Consuming {qf_name}: total={len(lines)} shard_slice={len(shard_slice)} worker_slice={len(worker_slice)}", flush=True)

            timed_out = False
            write_stage_file(f"queue_file_{qf_name}", offset)
            for i in range(0, len(worker_slice), 500):'''
NEW2 = '''            worker_slice = shard_slice[worker_id::total_workers]
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
            shard_log(f"[QUEUE STAGE] Consuming {qf_name}: total={len(lines)} shard_slice={len(shard_slice)} worker_slice={len(worker_slice)} resume={_start}", flush=True)
            timed_out = False
            write_stage_file(f"queue_file_{qf_name}", offset)
            for i in range(_start, len(worker_slice), 500):'''

OLD3 = "                    offset += len(tasks)"
NEW3 = '''                    offset += len(tasks)
                try:
                    with open(qcur_file, "w", encoding="utf-8") as _qcw2:
                        _qcw2.write(f"{min(i + 500, len(worker_slice))}\\n")
                except Exception:
                    pass'''

OLD4 = '''            # Mark acknowledged by this shard (always written, including on expiry)
            try:
                with open(ack_file, "w", encoding="utf-8") as af:
                    af.write("1\\n")
            except Exception:
                pass'''
NEW4 = '''            # Mark acknowledged only when this shard's whole slice is finished
            try:
                if (not timed_out) and ((i + 500) >= len(worker_slice)):
                    with open(qcur_file, "w", encoding="utf-8") as _qcw3:
                        _qcw3.write("DONE\\n")
                    with open(ack_file, "w", encoding="utf-8") as af:
                        af.write("1\\n")
            except Exception:
                pass'''

OLD5 = '''            # If timed out, break out of queue files loop and fall through to scanning
            if timed_out:
                break'''
NEW5 = '''            # If timed out, break out of queue files loop and fall through to scanning
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
        return _rem'''

OLD8 = '''    await consume_queue_stage()
    write_stage_file("queue_done", offset)'''
NEW8 = '''    for _pass in range(60):
        try:
            subprocess.run(["git", "fetch", "--depth", "1", "origin", "main"], cwd=REPO, capture_output=True, timeout=90)
            subprocess.run(["git", "checkout", "FETCH_HEAD", "--", "ip/harvest/queue"], cwd=REPO, capture_output=True, timeout=90)
        except Exception:
            pass
        _left = await consume_queue_stage()
        if not _left:
            break
        await asyncio.sleep(1)
    write_stage_file("queue_done", offset)'''

for d in sorted(P.glob("cl_shodan_*")):
    f = d / "run.py"
    s = f.read_text(encoding="utf-8")
    if "qcursor" in s:
        R.append(f"{d.name}: ALREADY PATCHED"); continue
    for old, new, n in ((OLD7,NEW7,1),(OLD6A,NEW6A,1),(OLD6B,NEW6B,1),(OLD1,NEW1,1),(OLD2,NEW2,1),(OLD3,NEW3,1),(OLD4,NEW4,1),(OLD5,NEW5,1),(OLD8,NEW8,1)):
        if s.count(old) < n:
            R.append(f"{d.name}: MISS {old[:40]!r}"); break
        s = s.replace(old, new, n)
    else:
        f.write_text(s, encoding="utf-8")
        R.append(f"{d.name}: OK")
print("\n".join(R))
print("FAILED:", sum(1 for r in R if "OK" not in r))
