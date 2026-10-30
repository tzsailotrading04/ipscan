#!/usr/bin/env python3
"""
15-minute logger for Set A (50 Strict Traffmonetizer nodes)
Appends [timestamp] set_a_connected=<count>/50 total_mb=<mb> to work/SET_A_24H.txt
Runs continuously in the background.
"""
import os
import sys
import time
import subprocess
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(REPO_ROOT, "work", "SET_A_24H.txt")

def get_stats_linux():
    total_bytes = 0
    connected_cnt = 0
    for i in range(1, 51):
        tag = f"strict_{i:03d}"
        log_file = f"/var/run/traffmonetizer_test/{tag}/cli.log"
        if os.path.exists(log_file):
            with open(log_file, "r", errors="ignore") as f:
                for line in f:
                    l = line.lower()
                    if " - connected" in l or "connected: true" in l:
                        connected_cnt += 1
                        break
        vc_name = f"vc_ts{i:03d}"
        ns_name = f"ns_{tag}"
        res = subprocess.run(f"ip netns exec {ns_name} ip -s link show dev {vc_name} 2>/dev/null", shell=True, stdout=subprocess.PIPE, text=True)
        rx_bytes, tx_bytes = 0, 0
        lines = res.stdout.splitlines()
        for j, line in enumerate(lines):
            if "RX:" in line and j + 1 < len(lines):
                p = lines[j+1].split()
                if p and p[0].isdigit(): rx_bytes = int(p[0])
            elif "TX:" in line and j + 1 < len(lines):
                p = lines[j+1].split()
                if p and p[0].isdigit(): tx_bytes = int(p[0])
        total_bytes += (rx_bytes + tx_bytes)
    return connected_cnt, round(total_bytes / (1024 * 1024), 2)

def get_stats():
    if sys.platform == "win32":
        cmd = ["wsl", "-d", "depinfarm", "-u", "root", "python3", "/mnt/d/DEpinFarm/tools/log_set_a_24h.py", "--query"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and ":" in res.stdout.strip():
            parts = res.stdout.strip().split(":")
            return int(parts[0]), float(parts[1])
        return 0, 0.0
    else:
        return get_stats_linux()

def log_entry():
    conn_cnt, mb = get_stats()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now_str}] set_a_connected={conn_cnt}/50 total_mb={mb}\n"
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
    print(line.strip(), flush=True)

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--query":
        c, m = get_stats_linux()
        print(f"{c}:{m}")
        sys.exit(0)

    print(f"Starting Set A 24h Logger -> {LOG_FILE}", flush=True)
    log_entry()
    while True:
        time.sleep(900)  # 15 minutes
        try:
            log_entry()
        except Exception as e:
            print(f"Error logging: {e}", flush=True)

if __name__ == "__main__":
    main()
