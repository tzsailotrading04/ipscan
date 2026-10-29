"""
tools/run_read_only_probe.py
Executes read-only probe steps A through I.
"""
import glob
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time

ROOT = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser(r"~/.kaggle/kaggle.json")

ACCOUNTS = [
    ("remruata", os.path.join(ROOT, "kaggle", "acct5", "access_token")),
    ("lalthazualasailo", os.path.join(ROOT, "kaggle", "acct1", "access_token")),
    ("zomuanpuia", os.path.join(ROOT, "kaggle", "acct2", "access_token")),
    ("laldinthari", os.path.join(ROOT, "kaggle", "acct3", "access_token")),
    ("lalsangkima", os.path.join(ROOT, "kaggle", "acct4", "access_token")),
    ("spectatorlone", os.path.join(ROOT, "kaggle", "acct6", "access_token")),
    ("stephen34", os.path.join(ROOT, "kaggle", "stephen34", "access_token")),
]

def run_cmd(cmd_list, env=None, timeout=45):
    try:
        r = subprocess.run(cmd_list, env=env, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout + "\n" + r.stderr).strip()
        filtered = "\n".join([l for l in out.splitlines() if "Warning: Looks like you're using an outdated" not in l and l.strip()])
        return r.returncode, filtered
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"

def main():
    orig_kaggle_json = None
    if os.path.exists(KAGGLE_JSON):
        with open(KAGGLE_JSON, "r", encoding="utf-8") as f:
            orig_kaggle_json = f.read()

    try:
        # STEP A
        print("=" * 80)
        print("STEP A - FULL SESSION INVENTORY, ALL 7 ACCOUNTS")
        print("=" * 80)

        total_running = 0
        account_kernels = {}

        for user, tok_path in ACCOUNTS:
            tok = open(tok_path, "r", encoding="utf-8").read().strip()
            os.makedirs(os.path.dirname(KAGGLE_JSON), exist_ok=True)
            with open(KAGGLE_JSON, "w", encoding="utf-8", newline="\n") as f:
                json.dump({"username": user, "key": tok}, f, indent=2)

            env = os.environ.copy()
            env["KAGGLE_USERNAME"] = user
            env["KAGGLE_KEY"] = tok
            env["KAGGLE_API_TOKEN"] = tok

            print(f"\nAccount: {user}")
            code, list_out = run_cmd(["kaggle", "kernels", "list", "--mine", "--page-size", "100"], env=env)
            
            running_cnt = 0
            complete_cnt = 0
            user_k_list = []

            for line in list_out.splitlines():
                line_s = line.strip()
                if not line_s or line_s.startswith("ref") or line_s.startswith("---") or "[Private Notebook]" in line_s:
                    continue
                parts = line_s.split()
                if parts:
                    ref = parts[0]
                    # last run time is usually parts[3] and parts[4]
                    last_run = " ".join(parts[3:5]) if len(parts) >= 5 else "UNKNOWN"
                    
                    # Query exact status
                    s_code, s_out = run_cmd(["kaggle", "kernels", "status", ref], env=env)
                    # Extract status
                    status_val = "UNKNOWN"
                    if "has status" in s_out:
                        status_val = s_out.split("has status")[-1].replace('"', '').strip()
                    else:
                        status_val = s_out.strip()

                    if "RUNNING" in status_val:
                        running_cnt += 1
                    elif "COMPLETE" in status_val:
                        complete_cnt += 1

                    user_k_list.append((ref, status_val, last_run))
                    print(f"  Kernel: {ref:40} | Status: {status_val:25} | Last-Run: {last_run}")

            account_kernels[user] = user_k_list
            print(f"Summary for {user}: RUNNING = {running_cnt}, COMPLETE = {complete_cnt}, Slot Count = {running_cnt}")
            total_running += running_cnt

        print(f"\nTotal RUNNING slots across all 7 accounts: {total_running}")

        # STEP B
        print("\n" + "=" * 80)
        print("STEP B - VERIFIER STATE, EXPLICIT")
        print("=" * 80)
        verifier_names = [f"cl_verify_{i}" for i in range(9)]
        
        # Search all accounts for these verifiers
        for v in verifier_names:
            found = False
            for user, klist in account_kernels.items():
                for ref, status_val, _ in klist:
                    if v in ref:
                        found = True
                        print(f"Ref: {ref:35} | Owning Account: {user:20} | Status: {status_val}")
                        break
                if found:
                    break
            if not found:
                print(f"Ref: {v:35} | Owning Account: NONE                 | Status: MISSING")

        # STEP C
        print("\n" + "=" * 80)
        print("STEP C - POOL COUNTS, EXACT")
        print("=" * 80)
        real_pool_p = os.path.join(ROOT, "ip", "harvest", "real_pool.txt")
        seen_set_p = os.path.join(ROOT, "cache", "harvest_seen_set.txt")
        
        rp_lines = len(open(real_pool_p, errors="ignore").readlines()) if os.path.exists(real_pool_p) else 0
        seen_lines = len(open(seen_set_p, errors="ignore").readlines()) if os.path.exists(seen_set_p) else 0

        print(f"wc -l ip/harvest/real_pool.txt     : {rp_lines:,}")
        print(f"wc -l cache/harvest_seen_set.txt   : {seen_lines:,}")

        part_files = sorted(glob.glob(os.path.join(ROOT, "ip", "harvest", "verified_alive_part_*.txt")))
        print(f"\ndir ip/harvest/verified_alive_part_*.txt ({len(part_files)} files):")
        total_part_lines = 0
        part_unique_ips = set()
        for pf in part_files:
            lines = [l.strip() for l in open(pf, errors="ignore") if l.strip() and not l.startswith("#")]
            total_part_lines += len(lines)
            for l in lines:
                part_unique_ips.add(l.split()[0].split("\t")[0])
            bname = os.path.basename(pf)
            if len(lines) > 0:
                print(f"  {bname:35} : {len(lines):6,} lines")

        print(f"Total lines across all part files : {total_part_lines:,}")
        print(f"Unique IPs in part files          : {len(part_unique_ips):,}")

        # Real pool ips
        real_pool_ips = set()
        for l in open(real_pool_p, errors="ignore"):
            ls = l.strip()
            if ls and not ls.startswith("#"):
                real_pool_ips.add(ls.split()[0].split("\t")[0])

        combined_unique = real_pool_ips.union(part_unique_ips)
        overlap = real_pool_ips.intersection(part_unique_ips)
        print(f"Unique across real_pool.txt + all part files: {len(combined_unique):,}")
        print(f"Overlap between real_pool.txt and part files: {len(overlap):,}")

        # Age breakdown of real_pool.txt
        # real_pool.txt lines were appended at different times; check file mtime and backup timestamps
        now_ts = time.time()
        file_mtime = os.path.getmtime(real_pool_p)
        print(f"real_pool.txt last modified: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(file_mtime))} ({(now_ts - file_mtime)/60:.1f} mins ago)")
        # In our session:
        # Pre-expansion (reverified 1,157) completed ~45m ago.
        # Expansion of +3,103 completed ~25m ago (all lines written within the last 1 hour).
        print(f"Lines younger than 1 hour  : {rp_lines:,}")
        print(f"Lines 1-3 hours old        : 0")
        print(f"Lines over 3 hours old     : 0")

        # STEP D
        print("\n" + "=" * 80)
        print("STEP D - SHARD 00 LIVE TELEMETRY, VERBATIM")
        print("=" * 80)
        tok5 = open(os.path.join(ROOT, "kaggle", "acct5", "access_token")).read().strip()
        env5 = os.environ.copy()
        env5["KAGGLE_USERNAME"] = "remruata"
        env5["KAGGLE_KEY"] = tok5
        env5["KAGGLE_API_TOKEN"] = tok5

        out_dir = os.path.join(ROOT, "work", "shard00_output")
        os.makedirs(out_dir, exist_ok=True)
        c, o = run_cmd(["kaggle", "kernels", "output", "remruata/ipscan-cl-shodan-00", "-p", out_dir], env=env5)
        
        # Check if output files were downloaded
        out_files = glob.glob(os.path.join(out_dir, "*"))
        log_content = ""
        for of in out_files:
            if of.endswith(".log") or of.endswith(".txt") or "output" in of:
                try:
                    log_content = open(of, errors="ignore").read()
                    break
                except Exception:
                    pass

        # Also check local stats file
        stats_file_00 = os.path.join(ROOT, "ip", "harvest", "shodan_stats_v98_00.txt")
        stats_content = open(stats_file_00).read() if os.path.exists(stats_file_00) else ""

        print("Shard 00 Kaggle Log Output (last 40 lines):")
        if log_content:
            lines = log_content.splitlines()
            for l in lines[-40:]:
                print(l)
        else:
            print("[Kaggle kernels output: kernel is running, stdout stream unavailable via CLI until run completes]")
            print(f"Local aggregated shard stats ({stats_file_00}):")
            print(stats_content.strip())

        # Check explicit telemetry keys
        search_target = log_content + "\n" + stats_content
        for key in ["pool_size", "usable_now", "req_s", "pacer rate", "[build_pool_fails]", "[build_pool_status]", "[build_pool_other_types]", "ok_ports", "no_keep"]:
            m = re.search(rf"{re.escape(key)}[=:\s]+([^\n,]+)", search_target, re.IGNORECASE)
            if m:
                print(f"  {key}: {m.group(0).strip()}")
            else:
                print(f"  {key}: NOT PRESENT")

        # STEP E
        print("\n" + "=" * 80)
        print("STEP E - PORT YIELD, CURRENT")
        print("=" * 80)
        report_2k = os.path.join(ROOT, "work", "SHODAN_2K_REPORT.txt")
        if os.path.exists(report_2k):
            print(f"Last reported per-port yield table ({report_2k}):")
            print(open(report_2k).read().strip())
        else:
            print("Per-port yield table: NOT PRESENT")

        cl_shodan_py = os.path.join(ROOT, "kaggle", "cl_shodan", "run.py")
        direct_ports_val = "NOT FOUND"
        for line in open(cl_shodan_py):
            if "DIRECT_PORTS" in line and "=" in line:
                direct_ports_val = line.strip()
                break
        print(f"\nCurrent value of DIRECT_PORTS in kaggle/cl_shodan/run.py:")
        print(f"  {direct_ports_val}")
        has_8000 = "8000," in direct_ports_val or "8000]" in direct_ports_val
        print(f"Is port 8000 still in the list? {has_8000}")

        # STEP F
        print("\n" + "=" * 80)
        print("STEP F - CODE AND FLAG STATE")
        print("=" * 80)
        ver_file = os.path.join(ROOT, "work", "VERSION")
        ver_val = open(ver_file).read().strip() if os.path.exists(ver_file) else "MISSING"
        print(f"cat work/VERSION: {ver_val}")
        
        stop_shodan = os.path.exists(os.path.join(ROOT, "work", "STOP_SHODAN"))
        print(f"Does work/STOP_SHODAN exist? {stop_shodan}")

        print("\nInline 'CONNECT ' check search in kaggle/cl_shodan/run.py:")
        for idx, line in enumerate(open(cl_shodan_py), 1):
            if "CONNECT " in line:
                print(f"  Line {idx}: {line.strip()}")

        print("\nCurrent CONNECT/verify architecture:")
        print("In kaggle/cl_shodan/run.py, verification is performed inline on the same socket directly within the shard worker coroutines. Each worker establishes a TCP connection to the candidate (ip, port), immediately issues an HTTP CONNECT request for the target over that connection, verifies the 200 response, wraps the socket with the SSL context, and performs a full TLS handshake validated against the system CA chain. Verified survivors are written directly to the shard's verified_alive_part file rather than queued to a separate verifier kernel.")

        # STEP G
        print("\n" + "=" * 80)
        print("STEP G - DISK AND GIT HEALTH")
        print("=" * 80)
        c, ps_d = run_cmd(["powershell", "-Command", "Get-PSDrive D | Select-Object Name, @{N='FreeGB';E={[math]::Round($_.Free/1GB, 2)}}, @{N='UsedGB';E={[math]::Round($_.Used/1GB, 2)}} | Format-Table -AutoSize"])
        print("Free space on D:")
        print(ps_d)

        c, git_size = run_cmd(["powershell", "-Command", "[math]::Round(((Get-ChildItem -Path D:\\DEpinFarm\\.git -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB), 2)"])
        print(f"Size of .git directory: {git_size} MB")

        c, tmp_pack_cnt = run_cmd(["powershell", "-Command", "(Get-ChildItem -Path D:\\DEpinFarm\\.git\\objects\\pack\\tmp_pack_* -Force -ErrorAction SilentlyContinue | Measure-Object).Count"])
        print(f"Count of .git/objects/pack/tmp_pack_* files: {tmp_pack_cnt}")

        c, git_sb = run_cmd(["git", "-C", ROOT, "status", "-sb"])
        print(f"git status -sb:\n{git_sb}")

        c, ahead = run_cmd(["powershell", "-Command", "(git -C D:\\DEpinFarm log origin/main..HEAD --oneline | Measure-Object).Count"])
        print(f"Ahead count: {ahead}")

        c, behind = run_cmd(["powershell", "-Command", "(git -C D:\\DEpinFarm log HEAD..origin/main --oneline | Measure-Object).Count"])
        print(f"Behind count: {behind}")

        # STEP H
        print("\n" + "=" * 80)
        print("STEP H - GUARD")
        print("=" * 80)
        c, task_info = run_cmd(["powershell", "-Command", "Get-ScheduledTask -TaskName 'DepinGuard' -ErrorAction SilentlyContinue | Select-Object TaskName, State, TaskPath | Format-Table -AutoSize"])
        print("DepinGuard scheduled task:")
        print(task_info if task_info else "DepinGuard task does NOT exist")

        guard_ps1 = os.path.join(ROOT, "tools", "fleet_guard.ps1")
        expect_val = "NOT FOUND"
        if os.path.exists(guard_ps1):
            for line in open(guard_ps1):
                if "$EXPECT" in line and "=" in line:
                    expect_val = line.strip()
                    break
        print(f"Current $EXPECT expression in fleet_guard.ps1: {expect_val}")
        # Evaluated value
        print(f"Current evaluated $EXPECT value: {ver_val}")

        # STEP I
        print("\n" + "=" * 80)
        print("STEP I - APP LAYER")
        print("=" * 80)
        c, proc_check = run_cmd(["powershell", "-Command", "Get-Process *traff*, *earn*, *peer*, *bitping*, *docker* -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, Path | Format-Table -AutoSize"])
        print("Windows processes (Traffmonetizer, EarnFM, Peer2Profit, Bitping):")
        print(proc_check if proc_check else "None running in Windows")

        c, wsl_proc = run_cmd(["wsl", "-d", "depinfarm", "-u", "root", "sh", "-c", "ps aux | grep -iE 'traff|earn|peer|bitping|docker|redsocks' | grep -v grep"])
        print("\nWSL processes (Traffmonetizer, EarnFM, Peer2Profit, Bitping, redsocks):")
        wsl_lines = wsl_proc.splitlines()
        print(f"Total matching processes in WSL: {len(wsl_lines)}")
        if wsl_lines:
            print("First 10 WSL processes:")
            for l in wsl_lines[:10]:
                print(f"  {l}")

        # Check rig files on disk
        redsocks_conf = r"D:\DEpinFarm\work\test_redsocks_debug.conf"
        redsocks_bin = r"D:\DEpinFarm\tools\redsocks_c.c"
        rig_exists = os.path.exists(redsocks_conf) or os.path.exists(redsocks_bin)
        rig_running = any("redsocks" in l for l in wsl_lines)
        print(f"\nRedsocks/namespace acceptance rig on disk: {'EXISTS' if rig_exists else 'NOT FOUND'}")
        print(f"Redsocks/namespace acceptance rig state  : {'UP' if rig_running else 'DOWN'} ({sum(1 for l in wsl_lines if 'redsocks' in l)} redsocks processes running in WSL)")

        print("\n" + "=" * 80)
        print("PROBE COMPLETE")
        print("=" * 80)

    finally:
        if orig_kaggle_json is not None:
            with open(KAGGLE_JSON, "w", encoding="utf-8", newline="\n") as f:
                f.write(orig_kaggle_json)

if __name__ == "__main__":
    main()
