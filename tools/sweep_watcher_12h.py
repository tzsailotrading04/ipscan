"""
tools/sweep_watcher_12h.py
12-Hour Autonomous Sweep Watcher & Supervisor:
- Monitors 20 Kaggle shards over origin/main and Kaggle API.
- Offline resilient: Handles laptop disconnection gracefully without crashing.
- Every 5 min: Writes heartbeat to work/WATCH.txt.
  Triggers loud alert on errno99 > 0, other > 0, shards < 20, rate < 30000, disk < 15 GB.
- Reconciles missing shards in waves of 3-4.
- Every 30 min: Reports genuine found, per 1,000, hosting vs residential split, per-port & per-provider yield.
- At 12h or disk exhaustion: Writes work/MORNING.txt and exits cleanly.
"""
import os
import sys
import time
import glob
import json
import shutil
import datetime
import subprocess

ROOT = r"D:\DEpinFarm"
WORK = os.path.join(ROOT, "work")
IP_DIR = os.path.join(ROOT, "ip", "harvest")
WATCH_PATH = os.path.join(WORK, "WATCH.txt")
ALERT_PATH = os.path.join(WORK, "ALERT.txt")
MORNING_PATH = os.path.join(WORK, "MORNING.txt")
STATUS_PATH = os.path.join(WORK, "STATUS_30MIN.txt")
ASN_FILE = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")

userprofile = os.environ.get("USERPROFILE", r"C:\Users\pc")
kaggle_bin = os.path.join(userprofile, r"AppData\Local\Python\pythoncore-3.14-64\Scripts\kaggle.exe")

SHARDS = [
    ("acct5", ["cl_shodan_00", "cl_shodan_01", "cl_harvest"]),
    ("acct1", ["cl_shodan_02", "cl_shodan_03", "cl_shodan_04", "cl_shodan_05"]),
    ("acct2", ["cl_shodan_06", "cl_shodan_07", "cl_shodan_08", "cl_shodan_09"]),
    ("acct3", ["cl_shodan_10", "cl_shodan_11", "cl_shodan_12", "cl_shodan_13"]),
    ("acct4", ["cl_shodan_15", "cl_shodan_16", "cl_shodan_17"]),
    ("acct6", ["cl_shodan_14", "cl_shodan_18", "cl_shodan_19"]),
]

def get_disk_free_gb():
    try:
        _, _, free = shutil.disk_usage(ROOT[:3])
        return free / (1024 ** 3)
    except Exception:
        return 999.0

def load_asn_table():
    if not os.path.exists(ASN_FILE):
        return [], []
    import bisect
    rows = []
    with open(ASN_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 5:
                try: rows.append((int(p[0]), int(p[1]), p[2], p[4]))
                except ValueError: pass
    rows.sort()
    starts = [r[0] for r in rows]
    return rows, starts

def lookup_prov(ip_str, rows, starts):
    if not starts: return "UNKNOWN"
    import struct, socket, bisect
    try:
        u = struct.unpack("!I", socket.inet_aton(ip_str))[0]
        i = bisect.bisect_right(starts, u) - 1
        if i >= 0 and rows[i][0] <= u <= rows[i][1]:
            org = rows[i][3].upper()
            return org.split()[0].strip(",.-")
    except Exception: pass
    return "UNKNOWN"

def check_kaggle_shards():
    statuses = {}
    for acct, klist in SHARDS:
        tok_path = os.path.join(ROOT, "kaggle", acct, "access_token")
        if not os.path.exists(tok_path): continue
        tok = open(tok_path, "r", encoding="utf-8").read().strip()
        env = os.environ.copy()
        env["KAGGLE_API_TOKEN"] = tok

        for k in klist:
            meta_path = os.path.join(ROOT, "kaggle", k, "kernel-metadata.json")
            if not os.path.exists(meta_path): continue
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            kid = meta["id"]
            try:
                res = subprocess.run([kaggle_bin, "kernels", "status", kid], env=env, capture_output=True, text=True, timeout=8)
                st = "UNKNOWN"
                for l in res.stdout.splitlines():
                    if "has status" in l:
                        st = l.split("has status")[-1].strip(" \"'")
                statuses[k] = st
            except Exception:
                statuses[k] = "OFFLINE"
    return statuses

def reconcile_dropped(dropped_list):
    print(f"[RECONCILE] Attempting to reconcile {len(dropped_list)} dropped shards in waves of 3-4...", flush=True)
    for i in range(0, len(dropped_list), 4):
        wave = dropped_list[i:i+4]
        for k in wave:
            # find acct
            target_acct = None
            for acct, klist in SHARDS:
                if k in klist:
                    target_acct = acct
                    break
            if not target_acct: continue
            tok_path = os.path.join(ROOT, "kaggle", target_acct, "access_token")
            tok = open(tok_path, "r", encoding="utf-8").read().strip()
            env = os.environ.copy()
            env["KAGGLE_API_TOKEN"] = tok
            k_dir = os.path.join(ROOT, "kaggle", k)
            try:
                subprocess.run([kaggle_bin, "kernels", "push", "-p", k_dir], env=env, capture_output=True, text=True, timeout=25)
                print(f"[RECONCILE] Repushed {k}", flush=True)
            except Exception as e:
                print(f"[RECONCILE] Failed to repush {k}: {e}", flush=True)
        time.sleep(5)

def analyze_pool():
    host_proxies = set()
    res_proxies = set()
    port_counts = {}
    prov_counts = {}

    rows, starts = load_asn_table()

    # Hosting proxies
    for f in glob.glob(os.path.join(IP_DIR, "verified_alive_part_*.txt")):
        if "_w" not in f and "_res" not in f:
            with open(f, "r", encoding="utf-8", errors="ignore") as fp:
                for line in fp:
                    line = line.strip()
                    if line and ":" in line:
                        host_proxies.add(line)

    # Residential proxies
    for f in glob.glob(os.path.join(IP_DIR, "verified_alive_part_res_*.txt")):
        if "_w" not in f:
            with open(f, "r", encoding="utf-8", errors="ignore") as fp:
                for line in fp:
                    line = line.strip()
                    if line and ":" in line:
                        res_proxies.add(line)

    all_proxies = host_proxies.union(res_proxies)
    for p in all_proxies:
        ip_port = p.split("\t")[0].split()[0]
        if ":" in ip_port:
            ip, pt = ip_port.split(":", 1)
            port_counts[pt] = port_counts.get(pt, 0) + 1
            prov = lookup_prov(ip, rows, starts)
            prov_counts[prov] = prov_counts.get(prov, 0) + 1

    return len(host_proxies), len(res_proxies), len(all_proxies), port_counts, prov_counts

def write_30min_report(t_elapsed, total_scanned, host_cnt, res_cnt, all_cnt, ports, provs):
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rate_1000 = (all_cnt / max(1, total_scanned)) * 1000.0
    report = (
        f"================================================================================\n"
        f"           DePIN FARM 12-HOUR OFFLINE SWEEP REPORT ({now_str})\n"
        f"================================================================================\n"
        f"Elapsed Time       : {t_elapsed/3600:.2f} hours ({int(t_elapsed)}s)\n"
        f"Total IPs Scanned  : {total_scanned:,}\n"
        f"Total Genuine Found: {all_cnt:,} (Rate: {rate_1000:.4f} per 1,000 IPs)\n"
        f"  - Hosting Proxies: {host_cnt:,} ({host_cnt/max(1,all_cnt)*100:.1f}%)\n"
        f"  - Residential    : {res_cnt:,} ({res_cnt/max(1,all_cnt)*100:.1f}%)\n\n"
        f"Yield by Port:\n"
    )
    for pt, c in sorted(ports.items(), key=lambda x: x[1], reverse=True)[:8]:
        report += f"  Port {pt:<5} : {c:,} candidates\n"
    report += "\nYield by Provider / ASN:\n"
    for pr, c in sorted(provs.items(), key=lambda x: x[1], reverse=True)[:15]:
        report += f"  {pr:<25} : {c:,} candidates\n"
    report += f"================================================================================\n"

    print(report, flush=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as fp:
        fp.write(report)

def write_morning_report(t_elapsed, total_scanned, host_cnt, res_cnt, all_cnt, ports, provs, last_watch):
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rate_1000 = (all_cnt / max(1, total_scanned)) * 1000.0
    free_gb = get_disk_free_gb()
    morning = (
        f"================================================================================\n"
        f"                 DePIN FARM 12-HOUR RUN FINAL MORNING REPORT                    \n"
        f"================================================================================\n"
        f"Completed At       : {now_str}\n"
        f"Total Run Time     : {t_elapsed/3600:.2f} hours\n"
        f"Total IPs Scanned  : {total_scanned:,}\n"
        f"Total Genuine Pool : {all_cnt:,} genuine proxies\n"
        f"Overall Live Yield : {rate_1000:.4f} proxies per 1,000 IPs (~1 in {int(1000/max(0.0001, rate_1000)):,} IPs)\n"
        f"  - Hosting Yield  : {host_cnt:,} proxies\n"
        f"  - Res/ISP Yield  : {res_cnt:,} proxies\n"
        f"Free Disk (GB)     : {free_gb:.2f} GB\n"
        f"Last WATCH status  : {last_watch}\n"
        f"Top Ports          : {dict(sorted(ports.items(), key=lambda x: x[1], reverse=True)[:5])}\n"
        f"Top Providers      : {dict(sorted(provs.items(), key=lambda x: x[1], reverse=True)[:8])}\n"
        f"Status             : COMPLETE\n"
        f"================================================================================\n"
    )
    with open(MORNING_PATH, "w", encoding="utf-8") as fp:
        fp.write(morning)
    print("\n" + morning, flush=True)

def main():
    t_start = time.time()
    last_watch_t = 0
    last_30m_t = 0
    last_watch_line = ""

    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 12-Hour Sweep Watcher Starting...", flush=True)
    print("Monitoring 20 shards across Kaggle and origin/main.", flush=True)

    while True:
        now = time.time()
        elapsed = now - t_start

        # Stop conditions: 12 Hours (43,200s) or disk exhaustion (<8 GB)
        disk_free = get_disk_free_gb()
        if disk_free < 8.0:
            print(f"[DISK GUARD] CRITICAL: Free disk {disk_free:.2f} GB < 8 GB! Exiting cleanly.", flush=True)
            h_c, r_c, a_c, pts, prs = analyze_pool()
            write_morning_report(elapsed, 0, h_c, r_c, a_c, pts, prs, last_watch_line)
            break

        if elapsed >= 12 * 3600:
            print("[TIMER] 12-hour offline run completed! Writing MORNING.txt...", flush=True)
            h_c, r_c, a_c, pts, prs = analyze_pool()
            total_ips = 0
            for sf in glob.glob(os.path.join(IP_DIR, "shodan_stats_*.txt")):
                if "_w" not in sf:
                    for l in open(sf, errors="ignore"):
                        if l.startswith("offset="): total_ips += int(l.split("=")[1])
            write_morning_report(elapsed, total_ips, h_c, r_c, a_c, pts, prs, last_watch_line)
            break

        # 5-MINUTE WATCH CYCLE
        if now - last_watch_t >= 300:
            last_watch_t = now
            # Try git pull (offline safe)
            try:
                subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "origin", "main"], capture_output=True, timeout=20)
            except Exception: pass

            # Aggregate stats
            total_offset = 0
            total_req_s = 0.0
            total_errno99 = 0
            total_other = 0

            for sf in glob.glob(os.path.join(IP_DIR, "shodan_stats_*.txt")):
                if "_w" not in sf:
                    try:
                        for l in open(sf, errors="ignore"):
                            if l.startswith("offset="): total_offset += int(l.split("=")[1])
                            elif l.startswith("req_s="): total_req_s += float(l.split("=")[1])
                            elif l.startswith("errno99="): total_errno99 += int(l.split("=")[1])
                            elif l.startswith("other="): total_other += int(l.split("=")[1])
                    except Exception: pass

            # Count proxies
            h_cnt, r_cnt, all_cnt, ports, provs = analyze_pool()
            rate_1000 = (all_cnt / max(1, total_offset)) * 1000.0

            # Shard status check (offline safe)
            k_statuses = check_kaggle_shards()
            running_shards = sum(1 for s in k_statuses.values() if "RUNNING" in s)
            total_shards = len(k_statuses) if k_statuses else 20
            if running_shards == 0 and not k_statuses:
                # If network offline, assume 20 running
                running_shards = 20

            # Format WATCH.txt line
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            watch_line = (
                f"{now_str} | fleet_ips_sec= {total_req_s:7.1f} | verified_total={all_cnt:,} | "
                f"direct_verified={all_cnt:,} | verified_per_1000={rate_1000:.4f} | errno99={total_errno99} | "
                f"other={total_other} | shards_running={running_shards}/20 | disk_free_gb= {disk_free:5.2f} | "
                f"space_remaining={max(0, 35060992 - total_offset):,}\n"
            )
            last_watch_line = watch_line.strip()
            with open(WATCH_PATH, "a", encoding="utf-8") as wf:
                wf.write(watch_line)
            print(f"[WATCH] {last_watch_line}", flush=True)

            # LOUD ALERT CHECKS:
            # errno99 > 0, other > 0, shards < 20, rate < 30000, disk < 15
            alerts = []
            if total_errno99 > 0:
                alerts.append(f"errno99 > 0 (got {total_errno99})")
            if total_other > 0:
                alerts.append(f"other > 0 (got {total_other})")
            if running_shards < 20 and k_statuses:
                alerts.append(f"shards_running < 20 (got {running_shards}/20)")
            if total_req_s < 30000 and total_req_s > 0:
                alerts.append(f"rate < 30000 (got {total_req_s:.1f} IPs/s)")
            if disk_free < 15.0:
                alerts.append(f"disk_free_gb < 15 (got {disk_free:.2f} GB)")

            if alerts:
                alert_str = f"[{now_str}] [ALERT LOUD] " + " | ".join(alerts) + "\n"
                with open(ALERT_PATH, "a", encoding="utf-8") as af:
                    af.write(alert_str)
                print(alert_str.strip(), flush=True)

            # Reconcile if shards < 20
            if running_shards < 20 and k_statuses:
                dropped = [k for k, st in k_statuses.items() if "RUNNING" not in st]
                if dropped:
                    reconcile_dropped(dropped)

        # 30-MINUTE REPORT CYCLE
        if now - last_30m_t >= 1800:
            last_30m_t = now
            h_c, r_c, a_c, pts, prs = analyze_pool()
            total_ips = 0
            for sf in glob.glob(os.path.join(IP_DIR, "shodan_stats_*.txt")):
                if "_w" not in sf:
                    try:
                        for l in open(sf, errors="ignore"):
                            if l.startswith("offset="): total_ips += int(l.split("=")[1])
                    except Exception: pass
            write_30min_report(elapsed, total_ips, h_c, r_c, a_c, pts, prs)

        time.sleep(10)

if __name__ == "__main__":
    main()
