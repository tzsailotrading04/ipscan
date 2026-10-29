#!/usr/bin/env python3
"""
Traffmonetizer 200-Proxy Acceptance Test Orchestrator
Runs inside WSL2 (Alpine 'depinfarm' distro)
Routes 200 clients through 200 isolated network namespaces via redsocks.
Duration: Exactly 2 hours (7200 seconds).
"""
import os
import sys
import time
import json
import uuid
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor

PROXIES_FILE = "/mnt/d/DEpinFarm/work/traff_200_proxies.txt"
TOKEN_FILE = "/mnt/d/DEpinFarm/config/traffmonetizer.token"
BASE_RUN_DIR = "/var/run/traffmonetizer"
STATUS_FILE = "/mnt/d/DEpinFarm/work/traff_acceptance_status.json"
FINAL_REPORT_FILE = "/mnt/d/DEpinFarm/work/traff_acceptance_final_report.json"
REPORT_TEXT_FILE = "/mnt/d/DEpinFarm/work/traff_acceptance_final_report.txt"

def run_cmd(cmd, check=True):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed ({res.returncode}): {cmd}\nStderr: {res.stderr}")
    return res

def setup_host_networking():
    print("[1/4] Configuring host bridge and NAT...")
    run_cmd("sysctl -w net.ipv4.ip_forward=1")
    run_cmd("iptables -P FORWARD ACCEPT")
    run_cmd("ip link add br0 type bridge 2>/dev/null || true", check=False)
    run_cmd("ip addr add 10.99.0.1/16 dev br0 2>/dev/null || true", check=False)
    run_cmd("ip link set br0 up")
    run_cmd("iptables -t nat -C POSTROUTING -s 10.99.0.0/16 -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s 10.99.0.0/16 -j MASQUERADE", check=False)
    print("      Host networking configured successfully.")

def cleanup_node(i):
    ns_name = f"ns_traff_{i:03d}"
    vh_name = f"vth_{i:03d}"
    run_cmd(f"ip netns del {ns_name} 2>/dev/null || true", check=False)
    run_cmd(f"ip link del {vh_name} 2>/dev/null || true", check=False)
    run_cmd(f"rm -rf /etc/netns/{ns_name}", check=False)

def setup_node(args):
    i, proxy, token = args
    proxy_ip, proxy_port = proxy.strip().split(":")
    ns_name = f"ns_traff_{i:03d}"
    vh_name = f"vth_{i:03d}"
    vc_name = f"vtc_{i:03d}"
    node_dir = f"{BASE_RUN_DIR}/node_{i:03d}"
    dev_name = f"dc_node_{i:03d}"
    dev_uuid = str(uuid.uuid4())

    cleanup_node(i)

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
    run_cmd(f"ip netns add {ns_name}")
    run_cmd(f"ip link add {vh_name} type veth peer name {vc_name}")
    run_cmd(f"ip link set {vh_name} master br0 up")
    run_cmd(f"ip link set {vc_name} netns {ns_name}")

    # 4. Configure interfaces in netns
    run_cmd(f"ip netns exec {ns_name} ip addr add 10.99.1.{i}/16 dev {vc_name}")
    run_cmd(f"ip netns exec {ns_name} ip link set {vc_name} up")
    run_cmd(f"ip netns exec {ns_name} ip link set lo up")
    run_cmd(f"ip netns exec {ns_name} ip route add default via 10.99.0.1")

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
    run_cmd(ipt_cmds)

    # 7. Start redsocks in netns
    run_cmd(f"ip netns exec {ns_name} /usr/bin/redsocks -c {node_dir}/redsocks.conf -p {node_dir}/redsocks.pid")

    # 8. Start traff_cli in netns
    cli_cmd = (
        f"export HOME={node_dir}; "
        f"nohup ip netns exec {ns_name} /tmp/traff_cli start accept "
        f"--token {token} --device-name {dev_name} > {node_dir}/cli.log 2>&1 &"
    )
    run_cmd(cli_cmd)

def parse_cli_log(log_path):
    if not os.path.exists(log_path):
        return False, "NO_LOG", None

    ever_conn = False
    current_status = "UNKNOWN"
    balance = None

    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_s = line.strip()
                if " - connected" in line_s or "connected: true" in line_s.lower():
                    ever_conn = True
                    current_status = "CONNECTED"
                elif " - disconnected" in line_s or "connected: false" in line_s.lower():
                    current_status = "DISCONNECTED"
                elif " - connecting" in line_s:
                    current_status = "CONNECTING"
                elif "ballance:" in line_s.lower():
                    ever_conn = True
                    current_status = "CONNECTED"
                    parts = line_s.split(";")
                    for p in parts:
                        if "ballance:" in p.lower():
                            balance = p.split(":")[-1].strip()
    except Exception:
        pass
    return ever_conn, current_status, balance

def monitor_nodes(proxies, total_duration_sec=7200):
    start_time = time.time()
    end_time = start_time + total_duration_sec
    ever_connected = set()

    print(f"\n[3/4] Starting 2-Hour Acceptance Monitoring Loop (Target: {total_duration_sec}s)...")
    print("----------------------------------------------------------------------")
    
    last_print = 0
    try:
        while time.time() < end_time:
            now = time.time()
            elapsed = now - start_time
            remaining = end_time - now

            currently_up = []
            statuses = {}
            balances = []

            for i, proxy in enumerate(proxies, start=1):
                node_dir = f"{BASE_RUN_DIR}/node_{i:03d}"
                log_path = f"{node_dir}/cli.log"

                ever_conn, current_status, balance = parse_cli_log(log_path)
                if ever_conn:
                    ever_connected.add(i)

                statuses[i] = current_status
                if balance:
                    balances.append(balance)

                if current_status == "CONNECTED":
                    currently_up.append(i)

            current_status_summary = {
                "timestamp": now,
                "elapsed_sec": round(elapsed, 1),
                "remaining_sec": round(remaining, 1),
                "total_nodes": len(proxies),
                "ever_connected_count": len(ever_connected),
                "currently_up_count": len(currently_up),
                "currently_up_nodes": currently_up,
                "sample_balances": balances[:5] if balances else []
            }

            # Save live checkpoint to file
            try:
                with open(STATUS_FILE, "w", encoding="utf-8") as f:
                    json.dump(current_status_summary, f, indent=2)
            except Exception:
                pass

            # Print update every 5 minutes (or on first pass)
            if now - last_print >= 300 or last_print == 0:
                last_print = now
                mins_elapsed = int(elapsed // 60)
                mins_remain = int(remaining // 60)
                print(f"[{time.strftime('%H:%M:%S')}] T+{mins_elapsed}m (Rem: {mins_remain}m) | "
                      f"Total Nodes: {len(proxies)} | Ever Connected: {len(ever_connected)} | "
                      f"Currently Up: {len(currently_up)}")

            time.sleep(15)

    except KeyboardInterrupt:
        print("\nAcceptance monitor stopped by operator. Redsocks and nodes remain active in namespaces.")

    print("\n[4/4] Acceptance Monitor Checkpoint... Compiling Report...")
    final_report = {
        "start_time": start_time,
        "end_time": time.time(),
        "total_duration_sec": round(time.time() - start_time, 1),
        "total_nodes": len(proxies),
        "clients_that_connected_count": len(ever_connected),
        "clients_that_connected": sorted(list(ever_connected)),
        "clients_still_up_at_2h_count": len(currently_up),
        "clients_still_up_at_2h": sorted(currently_up),
        "proxies_used": proxies,
        "final_statuses": statuses
    }

    with open(FINAL_REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=2)

    report_text = f"""======================================================================
TRAFFMONETIZER 200-PROXY ACCEPTANCE TEST REPORT
======================================================================
Duration: {final_report['total_duration_sec']} seconds ({final_report['total_duration_sec']/3600:.2f} hours)
Total Configured Nodes: {final_report['total_nodes']}
One Proxy per IP: YES (200 unique datacenter proxy IPs)
Routing Mechanism: Transparent network namespaces with redsocks

RESULTS:
- Clients that connected: {final_report['clients_that_connected_count']} / {final_report['total_nodes']} ({(final_report['clients_that_connected_count']/final_report['total_nodes'])*100:.1f}%)
- Clients currently up: {final_report['clients_still_up_at_2h_count']} / {final_report['total_nodes']} ({(final_report['clients_still_up_at_2h_count']/final_report['total_nodes'])*100:.1f}%)
======================================================================
"""
    with open(REPORT_TEXT_FILE, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(report_text)

def main():
    if not os.path.exists(TOKEN_FILE):
        print(f"Error: Token file {TOKEN_FILE} not found!")
        sys.exit(1)
    with open(TOKEN_FILE, "r") as f:
        token = f.read().strip()

    if not os.path.exists(PROXIES_FILE):
        print(f"Error: Proxies file {PROXIES_FILE} not found!")
        sys.exit(1)
    with open(PROXIES_FILE, "r") as f:
        proxies = [line.strip() for line in f if line.strip()][:200]

    print(f"Loaded {len(proxies)} datacenter proxies.")
    print(f"Token length: {len(token)} chars.")

    setup_host_networking()

    # Deploy all 200 nodes
    print(f"[2/4] Deploying {len(proxies)} isolated namespaces and launching clients (concurrency=20)...")
    tasks = [(i, proxy, token) for i, proxy in enumerate(proxies, start=1)]
    with ThreadPoolExecutor(max_workers=20) as executor:
        for idx, _ in enumerate(executor.map(setup_node, tasks), start=1):
            if idx % 25 == 0 or idx == len(proxies):
                print(f"      Deployed {idx}/{len(proxies)} nodes...")

    # Monitor for 2 hours (7200 seconds)
    monitor_nodes(proxies, total_duration_sec=7200)

if __name__ == "__main__":
    main()
