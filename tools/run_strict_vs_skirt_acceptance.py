#!/usr/bin/env python3
"""
Traffmonetizer Acceptance Test: 50 Strict (Set A) vs 50 Skirt (Set B)
Runs inside WSL2 (Alpine 'depinfarm' distro)
Routes 50 strict proxies and 50 skirt proxies through 100 isolated network namespaces.
Device prefixes:
  Set A: strict_001..strict_050
  Set B: skirt_001..skirt_050
Measures connection rate, active connection, sold traffic, and total MB over 45 minutes (2700s).
"""
import os
import sys
import time
import json
import uuid
import subprocess
from concurrent.futures import ThreadPoolExecutor

REPO_ROOT = "/mnt/d/DEpinFarm"
SET_A_FILE = os.path.join(REPO_ROOT, "work", "test_set_A.txt")
SET_B_FILE = os.path.join(REPO_ROOT, "work", "test_set_B.txt")
TOKEN_FILE = os.path.join(REPO_ROOT, "config", "traffmonetizer.token")
BASE_RUN_DIR = "/var/run/traffmonetizer_test"
STATUS_FILE = os.path.join(REPO_ROOT, "work", "test_AB_status.json")
FINAL_REPORT_FILE = os.path.join(REPO_ROOT, "work", "test_AB_final_report.json")
MORNING_FILE = os.path.join(REPO_ROOT, "work", "MORNING.txt")

TOTAL_DURATION_SEC = 45 * 60  # 45 minutes (2700s)

def run_cmd(cmd, check=True):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed ({res.returncode}): {cmd}\nStderr: {res.stderr}")
    return res

def setup_host_networking():
    print("[1/5] Configuring host bridge and NAT...")
    run_cmd("sysctl -w net.ipv4.ip_forward=1", check=False)
    run_cmd("iptables -P FORWARD ACCEPT", check=False)
    run_cmd("ip link add br0 type bridge 2>/dev/null || true", check=False)
    run_cmd("ip addr add 10.99.0.1/16 dev br0 2>/dev/null || true", check=False)
    run_cmd("ip link set br0 up", check=False)
    run_cmd("iptables -t nat -C POSTROUTING -s 10.99.0.0/16 -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s 10.99.0.0/16 -j MASQUERADE", check=False)

def cleanup_all_old():
    print("[2/5] Cleaning up existing rigs and processes...")
    run_cmd("killall -9 traff_cli redsocks 2>/dev/null || true", check=False)
    # Delete old namespaces
    ns_list = run_cmd("ip netns list", check=False).stdout.splitlines()
    for line in ns_list:
        ns = line.split()[0]
        if ns.startswith("ns_strict_") or ns.startswith("ns_skirt_") or ns.startswith("ns_traff_"):
            run_cmd(f"ip netns del {ns} 2>/dev/null || true", check=False)
            run_cmd(f"rm -rf /etc/netns/{ns}", check=False)
    run_cmd(f"rm -rf {BASE_RUN_DIR}", check=False)
    os.makedirs(BASE_RUN_DIR, exist_ok=True)

def setup_node(args):
    set_type, idx, proxy_raw, token = args
    # Parse proxy IP and port
    endpoint = proxy_raw.strip().split("\t")[0].split()[0]
    proxy_ip, proxy_port = endpoint.split(":")

    tag = f"{set_type}_{idx:03d}"
    ns_name = f"ns_{tag}"
    veth_prefix = "ts" if set_type == "strict" else "tk"
    vh_name = f"vh_{veth_prefix}{idx:03d}"
    vc_name = f"vc_{veth_prefix}{idx:03d}"
    node_dir = f"{BASE_RUN_DIR}/{tag}"
    dev_name = tag
    dev_uuid = str(uuid.uuid4())
    octet3 = 10 if set_type == "strict" else 20
    ip_addr = f"10.99.{octet3}.{idx}"

    # 1. Config directories
    os.makedirs(f"{node_dir}/.config/traffmonetizer", exist_ok=True)
    with open(f"{node_dir}/.config/traffmonetizer/cli_device_ids.json", "w") as f:
        json.dump({"": dev_uuid}, f)

    # 2. Redsocks config
    redsocks_conf = f"""base {{
    log_debug = off;
    log_info = off;
    log = "file:{node_dir}/redsocks.log";
    daemon = on;
    redirector = iptables;
}}
redsocks {{
    local_ip = 127.0.0.1;
    local_port = 12345;
    ip = {proxy_ip};
    port = {proxy_port};
    type = http-connect;
}}
"""
    with open(f"{node_dir}/redsocks.conf", "w") as f:
        f.write(redsocks_conf)

    # 3. Create network namespace and veth
    run_cmd(f"ip netns add {ns_name}", check=False)
    run_cmd(f"ip link add {vh_name} type veth peer name {vc_name}", check=False)
    run_cmd(f"ip link set {vh_name} master br0 up", check=False)
    run_cmd(f"ip link set {vc_name} netns {ns_name}", check=False)

    # 4. Configure interfaces in netns
    run_cmd(f"ip netns exec {ns_name} ip addr add {ip_addr}/16 dev {vc_name}", check=False)
    run_cmd(f"ip netns exec {ns_name} ip link set {vc_name} up", check=False)
    run_cmd(f"ip netns exec {ns_name} ip link set lo up", check=False)
    run_cmd(f"ip netns exec {ns_name} ip route add default via 10.99.0.1", check=False)

    # 5. DNS inside netns
    os.makedirs(f"/etc/netns/{ns_name}", exist_ok=True)
    with open(f"/etc/netns/{ns_name}/resolv.conf", "w") as f:
        f.write("nameserver 1.1.1.1\nnameserver 8.8.8.8\n")

    # 6. iptables transparent redirect inside netns
    ipt_cmds = f"""
    ip netns exec {ns_name} iptables -t nat -F
    ip netns exec {ns_name} iptables -t nat -X REDSOCKS 2>/dev/null || true
    ip netns exec {ns_name} iptables -t nat -N REDSOCKS
    ip netns exec {ns_name} iptables -t nat -A REDSOCKS -d 0.0.0.0/8 -j RETURN
    ip netns exec {ns_name} iptables -t nat -A REDSOCKS -d 10.0.0.0/8 -j RETURN
    ip netns exec {ns_name} iptables -t nat -A REDSOCKS -d 127.0.0.0/8 -j RETURN
    ip netns exec {ns_name} iptables -t nat -A REDSOCKS -d 169.254.0.0/16 -j RETURN
    ip netns exec {ns_name} iptables -t nat -A REDSOCKS -d 172.16.0.0/12 -j RETURN
    ip netns exec {ns_name} iptables -t nat -A REDSOCKS -d 192.168.0.0/16 -j RETURN
    ip netns exec {ns_name} iptables -t nat -A REDSOCKS -d {proxy_ip} -j RETURN
    ip netns exec {ns_name} iptables -t nat -A REDSOCKS -p tcp -j REDIRECT --to-ports 12345
    ip netns exec {ns_name} iptables -t nat -A OUTPUT -p tcp -j REDSOCKS
    """
    run_cmd(ipt_cmds, check=False)

    # 7. Start redsocks in netns
    run_cmd(f"ip netns exec {ns_name} /usr/bin/redsocks -c {node_dir}/redsocks.conf -p {node_dir}/redsocks.pid", check=False)

    # 8. Start traff_cli in netns
    cli_cmd = (
        f"export HOME={node_dir}; "
        f"nohup ip netns exec {ns_name} /tmp/traff_cli start accept "
        f"--token {token} --device-name {dev_name} > {node_dir}/cli.log 2>&1 &"
    )
    run_cmd(cli_cmd, check=False)
    return tag

def get_node_bytes(set_type, idx):
    ns_name = f"ns_{set_type}_{idx:03d}"
    veth_prefix = "ts" if set_type == "strict" else "tk"
    vc_name = f"vc_{veth_prefix}{idx:03d}"
    out = run_cmd(f"ip netns exec {ns_name} ip -s link show dev {vc_name} 2>/dev/null || true", check=False).stdout
    rx_bytes = 0
    tx_bytes = 0
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if "RX:" in line and i + 1 < len(lines):
            parts = lines[i + 1].split()
            if parts and parts[0].isdigit():
                rx_bytes = int(parts[0])
        elif "TX:" in line and i + 1 < len(lines):
            parts = lines[i + 1].split()
            if parts and parts[0].isdigit():
                tx_bytes = int(parts[0])
    return rx_bytes + tx_bytes

def parse_cli_log(node_dir):
    log_path = f"{node_dir}/cli.log"
    if not os.path.exists(log_path):
        return False, False
    ever_conn = False
    curr_conn = False
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                ls = line.strip().lower()
                if " - connected" in ls or "connected: true" in ls:
                    ever_conn = True
                    curr_conn = True
                elif " - disconnected" in ls or "connected: false" in ls:
                    curr_conn = False
    except Exception:
        pass
    return ever_conn, curr_conn

def monitor_sets(set_a_nodes, set_b_nodes, duration_sec):
    start_time = time.time()
    end_time = start_time + duration_sec
    last_print = 0

    # Capture baseline bytes
    baseline_bytes = {}
    for set_type, idx in set_a_nodes + set_b_nodes:
        baseline_bytes[(set_type, idx)] = get_node_bytes(set_type, idx)

    print(f"\n[4/5] Monitoring 100 Nodes (50 Strict vs 50 Skirt) for {duration_sec//60} minutes...")
    print("=" * 80)

    while True:  # Removed 45-minute stop so set A keeps running indefinitely
        now = time.time()
        elapsed = now - start_time
        remaining = end_time - now

        stats = {
            "strict": {"assigned": len(set_a_nodes), "connected": 0, "currently_up": 0, "sold_traffic": 0, "total_bytes": 0},
            "skirt":  {"assigned": len(set_b_nodes), "connected": 0, "currently_up": 0, "sold_traffic": 0, "total_bytes": 0}
        }

        for set_type, idx in set_a_nodes:
            tag = f"{set_type}_{idx:03d}"
            node_dir = f"{BASE_RUN_DIR}/{tag}"
            ever_conn, curr_conn = parse_cli_log(node_dir)
            if ever_conn:
                stats["strict"]["connected"] += 1
            if curr_conn:
                stats["strict"]["currently_up"] += 1

            cur_b = get_node_bytes(set_type, idx)
            delta_b = max(0, cur_b - baseline_bytes.get((set_type, idx), 0))
            stats["strict"]["total_bytes"] += delta_b
            if ever_conn and delta_b > 50000:  # > 50KB exchanged
                stats["strict"]["sold_traffic"] += 1

        for set_type, idx in set_b_nodes:
            tag = f"{set_type}_{idx:03d}"
            node_dir = f"{BASE_RUN_DIR}/{tag}"
            ever_conn, curr_conn = parse_cli_log(node_dir)
            if ever_conn:
                stats["skirt"]["connected"] += 1
            if curr_conn:
                stats["skirt"]["currently_up"] += 1

            cur_b = get_node_bytes(set_type, idx)
            delta_b = max(0, cur_b - baseline_bytes.get((set_type, idx), 0))
            stats["skirt"]["total_bytes"] += delta_b
            if ever_conn and delta_b > 50000:
                stats["skirt"]["sold_traffic"] += 1

        stats["strict"]["total_mb"] = round(stats["strict"]["total_bytes"] / (1024 * 1024), 2)
        stats["skirt"]["total_mb"] = round(stats["skirt"]["total_bytes"] / (1024 * 1024), 2)

        status_record = {
            "timestamp": now,
            "elapsed_sec": round(elapsed, 1),
            "remaining_sec": round(remaining, 1),
            "stats": stats
        }
        with open(STATUS_FILE, "w", encoding="utf-8") as sf:
            json.dump(status_record, sf, indent=2)

        if now - last_print >= 300 or last_print == 0:  # Every 5 minutes
            last_print = now
            m_el = int(elapsed // 60)
            m_rem = int(remaining // 60)
            print(f"[{time.strftime('%H:%M:%S')}] T+{m_el}m (Rem: {m_rem}m) | "
                  f"STRICT: {stats['strict']['connected']}/50 conn, {stats['strict']['sold_traffic']} sold, {stats['strict']['total_mb']} MB | "
                  f"SKIRT: {stats['skirt']['connected']}/50 conn, {stats['skirt']['sold_traffic']} sold, {stats['skirt']['total_mb']} MB", flush=True)

        time.sleep(15)

    return stats

def main():
    print("=" * 80)
    print("  APP ACCEPTANCE TEST - 50 STRICT vs 50 SKIRT")
    print("=" * 80)

    if not os.path.exists(TOKEN_FILE):
        print(f"Error: Token file {TOKEN_FILE} not found!")
        sys.exit(1)
    with open(TOKEN_FILE, "r") as f:
        token = f.read().strip()

    with open(SET_A_FILE, "r") as f:
        set_A = [line.strip() for line in f if line.strip()][:50]
    with open(SET_B_FILE, "r") as f:
        set_B = [line.strip() for line in f if line.strip()][:50]

    print(f"Loaded Set A (Strict): {len(set_A)} proxies from {SET_A_FILE}")
    print(f"Loaded Set B (Skirt):  {len(set_B)} proxies from {SET_B_FILE}")

    setup_host_networking()
    cleanup_all_old()

    print("[3/5] Deploying 100 isolated network namespaces and launching Traffmonetizer...")
    tasks = []
    set_a_nodes = []
    set_b_nodes = []

    for i, p in enumerate(set_A, start=1):
        tasks.append(("strict", i, p, token))
        set_a_nodes.append(("strict", i))

    for i, p in enumerate(set_B, start=1):
        tasks.append(("skirt", i, p, token))
        set_b_nodes.append(("skirt", i))

    with ThreadPoolExecutor(max_workers=20) as executor:
        for idx, tag in enumerate(executor.map(setup_node, tasks), start=1):
            if idx % 20 == 0 or idx == len(tasks):
                print(f"      Deployed {idx}/{len(tasks)} nodes...")

    print("-" * 80)
    print(f"ASSIGNMENTS COMPLETE:")
    print(f"  Set A (Strict): {len(set_a_nodes)} assigned (strict_001..strict_{len(set_a_nodes):03d})")
    print(f"  Set B (Skirt):  {len(set_b_nodes)} assigned (skirt_001..skirt_{len(set_b_nodes):03d})")
    print("-" * 80)

    # Monitor for 45 minutes
    final_stats = monitor_sets(set_a_nodes, set_b_nodes, TOTAL_DURATION_SEC)

    # Compile Final Assessment
    a_conn = final_stats["strict"]["connected"]
    b_conn = final_stats["skirt"]["connected"]
    a_mb = final_stats["strict"]["total_mb"]
    b_mb = final_stats["skirt"]["total_mb"]

    ratio_conn = (b_conn / a_conn) if a_conn > 0 else 0.0
    ratio_bytes = (b_mb / a_mb) if a_mb > 0 else 0.0

    verdict = "SKIRT_VIABLE" if b_conn > (0.5 * a_conn) else "SKIRT_DEAD"

    report_lines = [
        "=" * 80,
        f"APP ACCEPTANCE TEST REPORT (45 MINUTES) - {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 80,
        f"SET A (STRICT):",
        f"  Assigned:          {final_stats['strict']['assigned']}",
        f"  Connected:         {final_stats['strict']['connected']} / 50 ({final_stats['strict']['connected']/50*100:.1f}%)",
        f"  Sold Any Traffic:  {final_stats['strict']['sold_traffic']} / 50",
        f"  Total MB Sold:     {final_stats['strict']['total_mb']} MB",
        "- " * 40,
        f"SET B (SKIRT):",
        f"  Assigned:          {final_stats['skirt']['assigned']}",
        f"  Connected:         {final_stats['skirt']['connected']} / 50 ({final_stats['skirt']['connected']/50*100:.1f}%)",
        f"  Sold Any Traffic:  {final_stats['skirt']['sold_traffic']} / 50",
        f"  Total MB Sold:     {final_stats['skirt']['total_mb']} MB",
        "=" * 80,
        f"COMPARATIVE RATIOS (B / A):",
        f"  Connection Rate Ratio: {ratio_conn:.2f} ({b_conn} / {a_conn})",
        f"  Bytes Sold Ratio:      {ratio_bytes:.2f} ({b_mb} MB / {a_mb} MB)",
        f"DECISION: {verdict}",
        "=" * 80
    ]
    report_text = "\n".join(report_lines)
    print("\n" + report_text)

    with open(FINAL_REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.time(),
            "final_stats": final_stats,
            "ratio_conn": ratio_conn,
            "ratio_bytes": ratio_bytes,
            "verdict": verdict
        }, f, indent=2)

    with open(MORNING_FILE, "a", encoding="utf-8") as mf:
        mf.write("\n" + report_text + "\n")

    print("\nAppended report to work/MORNING.txt")

if __name__ == "__main__":
    main()
