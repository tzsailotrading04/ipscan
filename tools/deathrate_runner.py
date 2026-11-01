#!/usr/bin/env python3
"""
Death Rate Waterfall Experiment Runner
Pass 1: Tests 2,000 random unique endpoints from real_pool.txt.
Pass 2: Tests ONLY the survivors recorded in work/deathrate_pass1.txt (770 endpoints).
Pass 3: Tests ONLY the survivors of Pass 2 recorded in work/deathrate_pass2.txt.
Reporting: Survival at each stage as a percentage of the previous stage.
"""

import os
import sys
import ssl
import time
import socket
import struct
import bisect
import random
import json
import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT = r"D:\DEpinFarm"
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
QUEUE_DIR = os.path.join(REPO_ROOT, "ip", "harvest", "queue")
HOLD_DIR = os.path.join(REPO_ROOT, "work", "queue_hold")
STATUS_FILE = os.path.join(REPO_ROOT, "work", "deathrate_status.json")
REPORT_FILE = os.path.join(REPO_ROOT, "work", "deathrate_report.txt")
ASN_FILE = os.path.join(REPO_ROOT, "data", "ip2asn-v4-u32.tsv")

TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
SSL_CTX = ssl.create_default_context()
CONCURRENCY = 400
TIMEOUT = 8.0

asn_rows, asn_starts = [], []

def load_asn_table():
    global asn_rows, asn_starts
    if os.path.exists(ASN_FILE):
        rows = []
        with open(ASN_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) >= 5:
                    try:
                        rows.append((int(p[0]), int(p[1]), p[2], p[4]))
                    except ValueError:
                        pass
        rows.sort()
        asn_starts = [r[0] for r in rows]
        asn_rows = rows

def lookup_prov(ip_str):
    if not asn_starts:
        return "UNKNOWN"
    try:
        u = struct.unpack("!I", socket.inet_aton(ip_str))[0]
        i = bisect.bisect_right(asn_starts, u) - 1
        if i >= 0 and asn_rows[i][0] <= u <= asn_rows[i][1]:
            org = asn_rows[i][3].upper()
            return org.split()[0].strip(",.-")
    except Exception:
        pass
    return "UNKNOWN"

def hs(sock, target, timeout=TIMEOUT):
    try:
        sock.setblocking(True)
        sock.settimeout(timeout)
        sock.sendall(f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n".encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            ch = sock.recv(512)
            if not ch:
                return False
            resp += ch
            if len(resp) > 2048:
                return False
        first = resp.split(b"\r\n")[0]
        if not (b" 200" in first or b"HTTP/1.1 200" in first or b"HTTP/1.0 200" in first):
            return False
        ss = SSL_CTX.wrap_socket(sock, server_hostname=target)
        ss.settimeout(timeout)
        ss.do_handshake()
        c = ss.getpeercert()
        ss.close()
        return bool(c)
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        return False

def verify_single(ip, port, timeout=TIMEOUT):
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
    except Exception:
        return ip, port, False, None
    if hs(s, TARGETS[0], timeout):
        return ip, port, True, TARGETS[0]
    for t in TARGETS[1:]:
        try:
            s2 = socket.create_connection((ip, port), timeout=timeout)
            if hs(s2, t, timeout):
                return ip, port, True, t
        except Exception:
            pass
    return ip, port, False, None

def run_pass_verification(pass_num, cands):
    out_alive = os.path.join(REPO_ROOT, "work", f"deathrate_pass{pass_num}.txt")
    out_dead = os.path.join(REPO_ROOT, "work", f"deathrate_pass{pass_num}_dead.txt")
    os.makedirs(os.path.dirname(out_alive), exist_ok=True)

    open(out_alive, "w", encoding="utf-8").close()
    open(out_dead, "w", encoding="utf-8").close()

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [PASS {pass_num}] Starting verification of {len(cands)} endpoints with {CONCURRENCY} workers...")
    t0 = time.time()
    alive_count = 0
    dead_count = 0

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = {ex.submit(verify_single, ip, port): (ip, port) for ip, port in cands}
        for fu in as_completed(futs):
            ip, port, good, tgt = fu.result()
            if good:
                alive_count += 1
                prov = lookup_prov(ip)
                with open(out_alive, "a", encoding="utf-8") as af:
                    af.write(f"{ip}:{port}\t{tgt}\tDR_PASS{pass_num}\t0\t{prov}\n")
            else:
                dead_count += 1
                with open(out_dead, "a", encoding="utf-8") as df:
                    df.write(f"{ip}:{port}\tspeed.cloudflare.com\tDR_PASS{pass_num}\tREASON:FAIL_CONNECT\tRETIRED\n")

    dur = time.time() - t0
    rate = (alive_count / len(cands)) * 100 if cands else 0
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [PASS {pass_num} COMPLETE] {alive_count}/{len(cands)} alive ({rate:.2f}%) in {dur:.1f}s (dead={dead_count})")
    return alive_count, dead_count, dur

def git_release_queue(file_name):
    try:
        rel_path = f"ip/harvest/queue/{file_name}"
        subprocess.run(["git", "-C", REPO_ROOT, "add", rel_path], check=True, capture_output=True)
        c = subprocess.run(["git", "-C", REPO_ROOT, "commit", "-m", f"queue: release {file_name}"], capture_output=True, text=True)
        if c.returncode == 0 or "nothing to commit" in c.stdout:
            p = subprocess.run(["git", "-C", REPO_ROOT, "push", "origin", "main"], capture_output=True, text=True)
            if p.returncode == 0:
                print(f"[GIT] Released and pushed {rel_path} to origin/main.")
            else:
                print(f"[GIT WARNING] Push error for {rel_path}: {p.stderr or p.stdout}")
        else:
            print(f"[GIT WARNING] Commit error for {rel_path}: {c.stderr}")
    except Exception as e:
        print(f"[GIT EXCEPTION] {e}")

def update_status(status_dict):
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status_dict, f, indent=2)

def update_report(status_dict):
    lines = [
        "===========================================================",
        "           DEATH RATE WATERFALL EXPERIMENT REPORT          ",
        "===========================================================",
        f"Initial Pool Sample: {status_dict.get('sample_size', 2000)} endpoints",
        f"Experiment Start:    {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(status_dict.get('start_ts', time.time())))}",
        "-----------------------------------------------------------"
    ]
    # Pass 1
    if "pass1" in status_dict:
        r1 = status_dict["pass1"]
        lines.append("Pass 1 (Immediate / T+0s):")
        lines.append(f"  Queue file:        {r1.get('file')}")
        lines.append(f"  Tested:            {r1.get('total')} endpoints (initial pool sample)")
        lines.append(f"  Alive (survived):  {r1.get('alive')}")
        lines.append(f"  Survival Rate:     {r1.get('survival_pct', 0):.2f}% of previous stage (initial 2,000)")
        lines.append(f"  Duration:          {r1.get('duration_s', 0):.1f}s")
        lines.append(f"  Output:            work/deathrate_pass1.txt")
    else:
        lines.append("Pass 1: PENDING")

    lines.append("-----------------------------------------------------------")

    # Pass 2
    if "pass2" in status_dict:
        r2 = status_dict["pass2"]
        lines.append(f"Pass 2 (T+{r2.get('offset_sec', 0)}s):")
        lines.append(f"  Queue file:        {r2.get('file')}")
        lines.append(f"  Tested:            {r2.get('total')} endpoints (Pass 1 survivors)")
        lines.append(f"  Alive (survived):  {r2.get('alive')}")
        lines.append(f"  Survival Rate:     {r2.get('survival_pct', 0):.2f}% of previous stage (Pass 1)")
        lines.append(f"  Duration:          {r2.get('duration_s', 0):.1f}s")
        lines.append(f"  Output:            work/deathrate_pass2.txt")
    else:
        lines.append("Pass 2: PENDING (scheduled ~1 hr after start)")

    lines.append("-----------------------------------------------------------")

    # Pass 3
    if "pass3" in status_dict:
        r3 = status_dict["pass3"]
        lines.append(f"Pass 3 (T+{r3.get('offset_sec', 0)}s):")
        lines.append(f"  Queue file:        {r3.get('file')}")
        lines.append(f"  Tested:            {r3.get('total')} endpoints (Pass 2 survivors)")
        lines.append(f"  Alive (survived):  {r3.get('alive')}")
        lines.append(f"  Survival Rate:     {r3.get('survival_pct', 0):.2f}% of previous stage (Pass 2)")
        lines.append(f"  Duration:          {r3.get('duration_s', 0):.1f}s")
        lines.append(f"  Output:            work/deathrate_pass3.txt")
    else:
        lines.append("Pass 3: PENDING (scheduled ~2 hrs after start)")

    lines.append("===========================================================")
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def read_survivor_endpoints(file_path):
    eps = []
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                raw = line.strip()
                if raw:
                    ep = raw.split("\t")[0].split()[0]
                    eps.append(ep)
    return eps

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon", action="store_true", help="Run in daemon mode")
    args = parser.parse_args()

    load_asn_table()

    os.makedirs(QUEUE_DIR, exist_ok=True)
    os.makedirs(HOLD_DIR, exist_ok=True)
    os.makedirs(os.path.join(REPO_ROOT, "work"), exist_ok=True)

    state = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as sf:
                state = json.load(sf)
        except Exception:
            state = {}

    # Verify pass 1 is recorded
    pass1_file = os.path.join(REPO_ROOT, "work", "deathrate_pass1.txt")
    if not os.path.exists(pass1_file) or "pass1" not in state:
        sys.exit("Error: work/deathrate_pass1.txt not found. Pass 1 must be completed first.")

    # Fix pass 1 survival_pct naming
    state["pass1"]["survival_pct"] = (state["pass1"]["alive"] / state["pass1"]["total"]) * 100
    update_status(state)
    update_report(state)

    # 1. Prepare Pass 2: only the 770 endpoints from deathrate_pass1.txt
    pass1_survivors = read_survivor_endpoints(pass1_file)
    print(f"Loaded {len(pass1_survivors)} Pass 1 survivors from work/deathrate_pass1.txt.")

    q_pass2 = state["files"]["pass2"]
    hold_p2 = os.path.join(HOLD_DIR, q_pass2)
    with open(hold_p2, "w", encoding="utf-8") as f2:
        for ep in pass1_survivors:
            f2.write(ep + "\n")
    print(f"Updated {hold_p2} with only the {len(pass1_survivors)} Pass 1 survivors.")

    pass2_cands = []
    for ep in pass1_survivors:
        p = ep.split(":")
        if len(p) == 2 and p[1].isdigit():
            pass2_cands.append((p[0], int(p[1])))

    # Pass 2: T+3600s
    pass2_target_ts = state["start_ts"] + 3600
    if "pass2" not in state:
        wait_s = pass2_target_ts - time.time()
        if wait_s > 0:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Holding Pass 2 until T+3600s ({wait_s:.0f}s remaining, scheduled at {time.strftime('%H:%M:%S', time.localtime(pass2_target_ts))})...", flush=True)
            time.sleep(wait_s)

        queue_p2 = os.path.join(QUEUE_DIR, q_pass2)
        if os.path.exists(hold_p2):
            os.replace(hold_p2, queue_p2)
        git_release_queue(q_pass2)

        alive2, dead2, dur2 = run_pass_verification(2, pass2_cands)
        survival_pct2 = (alive2 / len(pass2_cands)) * 100 if pass2_cands else 0
        state["pass2"] = {
            "file": q_pass2,
            "ts": time.time(),
            "offset_sec": int(time.time() - state["start_ts"]),
            "total": len(pass2_cands),
            "alive": alive2,
            "dead": dead2,
            "survival_pct": survival_pct2,
            "duration_s": dur2
        }
        update_status(state)
        update_report(state)
        print(f"Pass 2 Complete: {alive2}/{len(pass2_cands)} survived ({survival_pct2:.2f}% of Pass 1).", flush=True)

    # 2. Prepare Pass 3: only what survives Pass 2
    pass2_file = os.path.join(REPO_ROOT, "work", "deathrate_pass2.txt")
    pass2_survivors = read_survivor_endpoints(pass2_file)
    print(f"Loaded {len(pass2_survivors)} Pass 2 survivors from work/deathrate_pass2.txt.")

    q_pass3 = state["files"]["pass3"]
    hold_p3 = os.path.join(HOLD_DIR, q_pass3)
    with open(hold_p3, "w", encoding="utf-8") as f3:
        for ep in pass2_survivors:
            f3.write(ep + "\n")
    print(f"Updated {hold_p3} with only the {len(pass2_survivors)} Pass 2 survivors.")

    pass3_cands = []
    for ep in pass2_survivors:
        p = ep.split(":")
        if len(p) == 2 and p[1].isdigit():
            pass3_cands.append((p[0], int(p[1])))

    # Pass 3: T+7200s
    pass3_target_ts = state["start_ts"] + 7200
    if "pass3" not in state:
        wait_s = pass3_target_ts - time.time()
        if wait_s > 0:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Holding Pass 3 until T+7200s ({wait_s:.0f}s remaining, scheduled at {time.strftime('%H:%M:%S', time.localtime(pass3_target_ts))})...", flush=True)
            time.sleep(wait_s)

        queue_p3 = os.path.join(QUEUE_DIR, q_pass3)
        if os.path.exists(hold_p3):
            os.replace(hold_p3, queue_p3)
        git_release_queue(q_pass3)

        alive3, dead3, dur3 = run_pass_verification(3, pass3_cands)
        survival_pct3 = (alive3 / len(pass3_cands)) * 100 if pass3_cands else 0
        state["pass3"] = {
            "file": q_pass3,
            "ts": time.time(),
            "offset_sec": int(time.time() - state["start_ts"]),
            "total": len(pass3_cands),
            "alive": alive3,
            "dead": dead3,
            "survival_pct": survival_pct3,
            "duration_s": dur3
        }
        update_status(state)
        update_report(state)
        print(f"Pass 3 Complete: {alive3}/{len(pass3_cands)} survived ({survival_pct3:.2f}% of Pass 2).", flush=True)
        print("All 3 stages of Waterfall Death Rate Experiment Complete!", flush=True)

if __name__ == "__main__":
    main()
