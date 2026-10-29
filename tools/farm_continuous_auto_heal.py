#!/usr/bin/env python3
"""
Depin Farm Continuous Auto-Heal & Proxy Replacer
Continuously audits all 200 Traffmonetizer nodes in WSL.
Detects dead, disconnected, or failing proxies.
Replaces them with fresh, ultra-fast verified proxies tested against the Traffmonetizer balancer (88.99.65.143:443).
Runs continuously.
"""
import os
import sys
import time
import glob
import json
import asyncio
import subprocess
from concurrent.futures import ThreadPoolExecutor

TOKEN_FILE = "/mnt/d/DEpinFarm/config/traffmonetizer.token"
PROXIES_FILE = "/mnt/d/DEpinFarm/work/traff_200_proxies.txt"
BASE_RUN_DIR = "/var/run/traffmonetizer"
STATUS_FILE = "/mnt/d/DEpinFarm/work/farm_auto_heal_status.json"
TARGET_HOST = "88.99.65.143"
TARGET_PORT = 443

try:
    with open(TOKEN_FILE, "r") as f:
        TOKEN = f.read().strip()
except Exception as e:
    TOKEN = ""

def load_assigned_proxies():
    if not os.path.exists(PROXIES_FILE):
        return {}
    with open(PROXIES_FILE, "r") as f:
        lines = [l.strip() for l in f if l.strip()]
    return {i + 1: p for i, p in enumerate(lines)}

def save_assigned_proxies(assigned):
    max_idx = max(assigned.keys()) if assigned else 200
    lines = [assigned.get(i, "") for i in range(1, max_idx + 1)]
    with open(PROXIES_FILE, "w") as f:
        for l in lines:
            f.write(l + "\n")

async def probe_candidate(proxy, sem, timeout=2.5):
    async with sem:
        try:
            ip, port = proxy.strip().split(":")
            port = int(port)
        except Exception:
            return proxy, False, 9999

        t0 = time.time()
        try:
            r, w = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
            connect_req = f"CONNECT {TARGET_HOST}:{TARGET_PORT} HTTP/1.1\r\nHost: {TARGET_HOST}:{TARGET_PORT}\r\n\r\n".encode()
            w.write(connect_req)
            await asyncio.wait_for(w.drain(), timeout=timeout)
            resp = await asyncio.wait_for(r.read(512), timeout=timeout)
            w.close()
            await w.wait_closed()
            dt = round((time.time() - t0) * 1000, 1)
            if b" 200" in resp or b"HTTP/1.1 200" in resp or b"HTTP/1.0 200" in resp:
                return proxy, True, dt
        except Exception:
            pass
        return proxy, False, 9999

async def scan_and_rank_candidates(candidate_list, active_proxies, max_needed=100):
    candidates = []
    seen = set(active_proxies.values())
    for c in candidate_list:
        c = c.strip().split("\t")[0].strip()
        if not c or ":" not in c:
            continue
        # Skip port 80 - rarely supports HTTP CONNECT for TLS targets
        if c.endswith(":80"):
            continue
        if c not in seen:
            seen.add(c)
            candidates.append(c)

    # Test in batches
    sem = asyncio.Semaphore(60)
    tasks = [probe_candidate(p, sem) for p in candidates[:400]]
    results = await asyncio.gather(*tasks)

    alive = [(p, lat) for p, ok, lat in results if ok]
    alive.sort(key=lambda x: x[1])
    return alive

def get_candidate_proxies_from_disk():
    candidates = []
    # Sources in priority
    sources = [
        "/mnt/d/DEpinFarm/ip/harvest/real_pool.txt",
        "/mnt/d/DEpinFarm/ip/public_residential.txt",
        "/mnt/d/DEpinFarm/ip/public_dc.txt",
    ]
    # Also include latest verified parts
    parts = glob.glob("/mnt/d/DEpinFarm/ip/harvest/verified_alive_part_*.txt")
    sources.extend(sorted(parts, reverse=True)[:5])

    for s in sources:
        if os.path.exists(s):
            try:
                with open(s, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            candidates.append(line.split("\t")[0].strip())
            except Exception:
                pass
    return candidates

def replace_node_proxy(i, new_proxy):
    try:
        proxy_ip, proxy_port = new_proxy.strip().split(":")
    except Exception:
        return False

    ns_name = f"ns_traff_{i:03d}"
    node_dir = f"{BASE_RUN_DIR}/node_{i:03d}"
    dev_name = f"dc_node_{i:03d}"

    # 1. Update redsocks config
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

    # 2. Update iptables in namespace
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
    subprocess.run(ipt_cmds, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3. Kill old redsocks
    pid_file = f"{node_dir}/redsocks.pid"
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as pf:
                pid = pf.read().strip()
            if pid:
                subprocess.run(f"kill -9 {pid} 2>/dev/null", shell=True)
        except Exception:
            pass

    # 4. Start new redsocks
    subprocess.run(
        f"ip netns exec {ns_name} /usr/bin/redsocks -c {node_dir}/redsocks.conf -p {node_dir}/redsocks.pid",
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    # 5. Kill old traff_cli for this node
    subprocess.run(f"pkill -9 -f '{dev_name}' 2>/dev/null", shell=True)
    time.sleep(0.3)

    # 6. Start new traff_cli
    cli_cmd = (
        f"export HOME={node_dir}; "
        f"nohup ip netns exec {ns_name} /tmp/traff_cli start accept "
        f"--token {TOKEN} --device-name {dev_name} > {node_dir}/cli.log 2>&1 &"
    )
    subprocess.run(cli_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True

def audit_node_status(i):
    node_dir = f"{BASE_RUN_DIR}/node_{i:03d}"
    log_path = f"{node_dir}/cli.log"

    if not os.path.exists(log_path):
        return i, "DEAD", "NO_LOG"

    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return i, "DEAD", "READ_ERROR"

    if not lines:
        return i, "DEAD", "EMPTY_LOG"

    recent = "".join(lines[-15:])
    
    # Check for active connected status or balance line
    if " - connected" in recent or "ballance:" in recent.lower():
        # Check if the last status was disconnected after connected
        last_lines = [l.strip() for l in lines[-4:] if "Status:" in l]
        if last_lines and "disconnected" in last_lines[-1]:
            return i, "DEAD", "DISCONNECTED"
        return i, "CONNECTED", "OK"
    elif " - disconnected" in recent:
        return i, "DEAD", "DISCONNECTED"
    elif " - connecting" in recent:
        # Check if stuck in connecting loop
        connecting_count = recent.count(" - connecting")
        if connecting_count >= 3:
            return i, "DEAD", "CONNECTING_LOOP"
        return i, "CONNECTING", "IN_PROGRESS"
    else:
        return i, "DEAD", "UNKNOWN"

def run_heal_cycle(pool_buffer):
    assigned = load_assigned_proxies()
    total_nodes = 200

    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] --- Starting Farm Health Audit (200 nodes) ---")

    # 1. Audit all 200 nodes
    node_statuses = {}
    with ThreadPoolExecutor(max_workers=30) as ex:
        results = list(ex.map(audit_node_status, range(1, total_nodes + 1)))

    connected_nodes = []
    dead_nodes = []
    connecting_nodes = []

    for i, status, reason in results:
        node_statuses[i] = (status, reason)
        if status == "CONNECTED":
            connected_nodes.append(i)
        elif status == "DEAD":
            dead_nodes.append((i, reason))
        else:
            connecting_nodes.append(i)

    print(f"Nodes Status -> CONNECTED: {len(connected_nodes)} | CONNECTING: {len(connecting_nodes)} | DEAD/FAILING: {len(dead_nodes)}")

    # 2. If pool buffer is low, replenish it
    if len(pool_buffer) < (len(dead_nodes) + 30):
        print(f"Replenishing fast proxy pool buffer (current size: {len(pool_buffer)})...")
        candidates = get_candidate_proxies_from_disk()
        fresh_alive = asyncio.run(scan_and_rank_candidates(candidates, assigned, max_needed=100))
        for p, lat in fresh_alive:
            if p not in [x[0] for x in pool_buffer]:
                pool_buffer.append((p, lat))
        pool_buffer.sort(key=lambda x: x[1])
        print(f"Fast proxy pool buffer now contains: {len(pool_buffer)} proxies (top latency: {pool_buffer[0][1] if pool_buffer else 'N/A'}ms)")

    # 3. Replace dead nodes
    replaced_count = 0
    if dead_nodes:
        print(f"Replacing {len(dead_nodes)} dead/failing nodes...")
        for i, reason in dead_nodes:
            if not pool_buffer:
                print("Warning: Pool buffer exhausted! Cannot replace more nodes this cycle.")
                break
            new_proxy, lat = pool_buffer.pop(0)
            old_proxy = assigned.get(i, "UNKNOWN")
            success = replace_node_proxy(i, new_proxy)
            if success:
                assigned[i] = new_proxy
                replaced_count += 1
                print(f"  [Node {i:03d}] REPLACED {old_proxy} -> {new_proxy} ({lat}ms) [was: {reason}]")

        save_assigned_proxies(assigned)
        print(f"Replaced {replaced_count} dead nodes with fresh fast proxies.")

    # 4. Save status summary
    status_summary = {
        "timestamp": time.time(),
        "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_nodes": total_nodes,
        "connected": len(connected_nodes),
        "connecting": len(connecting_nodes),
        "dead": len(dead_nodes),
        "replaced_this_cycle": replaced_count,
        "pool_buffer_remaining": len(pool_buffer),
    }
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(status_summary, f, indent=2)
    except Exception:
        pass

    return status_summary

def main():
    print("=================================================================")
    print("  DEPIN FARM CONTINUOUS AUTO-HEAL & PROXY REPLACER STARTED")
    print("=================================================================")
    pool_buffer = []

    # Initial run
    while True:
        try:
            summary = run_heal_cycle(pool_buffer)
            # Sleep 60s between full audits
            time.sleep(60)
        except KeyboardInterrupt:
            print("Stopping Auto-Healer.")
            break
        except Exception as e:
            print(f"Error in heal cycle: {e}")
            time.sleep(15)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        buf = []
        run_heal_cycle(buf)
    else:
        main()
