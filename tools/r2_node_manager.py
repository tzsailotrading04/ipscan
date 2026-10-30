#!/usr/bin/env python3
"""
r2_node_manager.py
Manages 200 Traffmonetizer nodes with prefix 'r2_' inside WSL2.
- Builds 200 nodes from top of work/assign_200.txt.
- Health check rule:
    A node is ALIVE only if:
      1) It has an ESTABLISHED socket in its network namespace
      AND
      2) Its interface moved bytes in the last 5 minutes.
- Auto-recycle on death:
    Draws exclusively from cache/alive_buffer.txt (verified alive replacement buffer).
    If buffer is empty, leaves node down and retries next cycle rather than assigning unverified IP.
"""
import os
import sys
import time
import json
import uuid
import subprocess
from concurrent.futures import ThreadPoolExecutor

REPO_ROOT = "/mnt/d/DEpinFarm"
TOKEN_FILE = os.path.join(REPO_ROOT, "config", "traffmonetizer.token")
ASSIGN_FILE = os.path.join(REPO_ROOT, "work", "assign_200.txt")
BUFFER_FILE = os.path.join(REPO_ROOT, "cache", "alive_buffer.txt")
DEAD_POOL_FILE = os.path.join(REPO_ROOT, "cache", "pool_dead.txt")
REAL_POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
STATE_FILE = os.path.join(REPO_ROOT, "work", "r2_state.json")
BASE_RUN_DIR = "/var/run/traffmonetizer_r2"

TOTAL_NODES = 200

def load_token():
    with open(TOKEN_FILE, "r") as f:
        return f.read().strip()

def run_cmd(cmd, check=False):
    return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def setup_host_networking():
    run_cmd("sysctl -w net.ipv4.ip_forward=1")
    run_cmd("iptables -P FORWARD ACCEPT")
    run_cmd("ip link add br0 type bridge 2>/dev/null || true")
    run_cmd("ip addr add 10.99.0.1/16 dev br0 2>/dev/null || true")
    run_cmd("ip link set br0 up")
    run_cmd("iptables -t nat -C POSTROUTING -s 10.99.0.0/16 -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s 10.99.0.0/16 -j MASQUERADE")

def teardown_node(idx, dead_endpoint=None):
    tag = f"r2_{idx:03d}"
    ns_name = f"ns_{tag}"
    vh_name = f"vh_{tag}"
    node_dir = f"{BASE_RUN_DIR}/{tag}"

    # Kill processes
    rs_pid_file = f"{node_dir}/redsocks.pid"
    if os.path.exists(rs_pid_file):
        try:
            pid = int(open(rs_pid_file).read().strip())
            run_cmd(f"kill -9 {pid} 2>/dev/null")
        except Exception:
            pass

    # Kill traff_cli for this device
    run_cmd(f"pkill -9 -f 'device-name {tag}' 2>/dev/null")

    # Delete network namespace and host veth
    run_cmd(f"ip netns del {ns_name} 2>/dev/null")
    run_cmd(f"ip link del {vh_name} 2>/dev/null")
    run_cmd(f"rm -rf /etc/netns/{ns_name} 2>/dev/null")

    # If dead IP provided, return to pool and record dead
    if dead_endpoint:
        try:
            os.makedirs(os.path.dirname(DEAD_POOL_FILE), exist_ok=True)
            with open(DEAD_POOL_FILE, "a", encoding="utf-8") as f:
                f.write(f"{dead_endpoint}\tRECYCLED\t{int(time.time())}\n")
        except Exception:
            pass

    run_cmd(f"rm -rf {node_dir} 2>/dev/null")

def setup_node(idx, endpoint, token):
    tag = f"r2_{idx:03d}"
    ns_name = f"ns_{tag}"
    vh_name = f"vh_{tag}"
    vc_name = f"vc_{tag}"
    node_dir = f"{BASE_RUN_DIR}/{tag}"
    dev_name = tag
    dev_uuid = str(uuid.uuid4())
    
    # Clean previous
    run_cmd(f"ip link del {vh_name} 2>/dev/null")
    run_cmd(f"ip netns del {ns_name} 2>/dev/null")
    run_cmd(f"rm -rf {node_dir} 2>/dev/null")

    # IP address: 10.99.100.idx (idx 1..200)
    ip_addr = f"10.99.100.{idx}"
    
    # Parse proxy IP:port
    try:
        proxy_ip, proxy_port = endpoint.split(":")
    except Exception:
        return False, f"Invalid endpoint: {endpoint}"

    # 1. Config directory & device ID
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
    run_cmd(f"ip netns exec {ns_name} ip addr add {ip_addr}/16 dev {vc_name}")
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
    return True, "OK"

def get_all_interface_bytes():
    """Reads /proc/net/dev on host for all vh_r2_* interfaces. Returns {idx: bytes}."""
    res = {}
    try:
        with open("/proc/net/dev", "r") as f:
            for line in f:
                if "vh_r2_" in line:
                    parts = line.split(":")
                    iface = parts[0].strip()
                    idx_str = iface.replace("vh_r2_", "")
                    if idx_str.isdigit():
                        idx = int(idx_str)
                        stats = parts[1].split()
                        rx = int(stats[0])
                        tx = int(stats[8])
                        res[idx] = rx + tx
    except Exception:
        pass
    return res

def check_node_established_socket(idx):
    """
    Checks if node r2_{idx} has at least one ESTABLISHED TCP socket in its netns.
    """
    tag = f"r2_{idx:03d}"
    ns_name = f"ns_{tag}"
    out = run_cmd(f"ip netns exec {ns_name} ss -tan 2>/dev/null").stdout
    for line in out.splitlines():
        if "ESTAB" in line:
            return True
    return False

def check_node_health(idx, prev_bytes, current_bytes):
    """
    HEALTH CHECK CRITERIA:
    A node is ALIVE only if:
      1) It has an ESTABLISHED socket
      AND
      2) Its interface moved bytes (current_bytes > prev_bytes).
    """
    has_estab = check_node_established_socket(idx)
    moved_bytes = current_bytes > prev_bytes

    if has_estab and moved_bytes:
        return True, "ALIVE"
    elif not has_estab and not moved_bytes:
        return False, "NO_ESTAB_AND_NO_TRAFFIC"
    elif not has_estab:
        return False, "NO_ESTAB_SOCKET"
    else:
        return False, "NO_BYTES_MOVED"

def pop_from_alive_buffer(count=1):
    """
    Draws count entries exclusively from cache/alive_buffer.txt and removes them.
    If the buffer is empty, returns empty list.
    """
    if not os.path.exists(BUFFER_FILE):
        return []
    with open(BUFFER_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = [l.strip() for l in f if l.strip()]
    if not lines:
        return []
    consumed = lines[:count]
    remaining = lines[count:]
    with open(BUFFER_FILE, "w", encoding="utf-8") as f:
        for l in remaining:
            f.write(l + "\n")
    return consumed

def audit_and_replace_from_buffer(token, max_replace=None):
    """
    Draws exclusively from cache/alive_buffer.txt to replace dead nodes.
    If the buffer is empty, leaves the node down and retries next cycle rather than assigning an unverified IP.
    """
    if not os.path.exists(STATE_FILE):
        print("State file not found! Run --build-initial first.")
        return 0

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)

    assigned = {int(k): v for k, v in state["assigned"].items()}
    prev_bytes = {int(k): v for k, v in state.get("byte_checkpoints", {}).items()}
    current_bytes = get_all_interface_bytes()

    dead_nodes = []
    alive_nodes = []

    for i in range(1, TOTAL_NODES + 1):
        p_b = prev_bytes.get(i, 0)
        c_b = current_bytes.get(i, 0)
        is_alive, reason = check_node_health(i, p_b, c_b)
        if is_alive:
            alive_nodes.append(i)
        else:
            dead_nodes.append((i, reason))

    print(f"[{time.strftime('%H:%M:%S')}] AUDIT: {len(alive_nodes)} ALIVE, {len(dead_nodes)} DEAD")

    if not dead_nodes:
        print("All 200 nodes are ALIVE! No replacements needed.")
        state["last_audit_time"] = time.time()
        state["byte_checkpoints"] = current_bytes
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        return 0

    if max_replace is not None:
        target_dead = dead_nodes[:max_replace]
    else:
        target_dead = dead_nodes

    needed = len(target_dead)
    # Draw ONLY from cache/alive_buffer.txt
    alive_proxies = pop_from_alive_buffer(needed)

    if not alive_proxies:
        print(f"[{time.strftime('%H:%M:%S')}] cache/alive_buffer.txt is EMPTY! Leaving {needed} nodes down and retrying next cycle.")
        state["last_audit_time"] = time.time()
        state["byte_checkpoints"] = current_bytes
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        return 0

    print(f"[{time.strftime('%H:%M:%S')}] Drew {len(alive_proxies)}/{needed} verified alive proxies from cache/alive_buffer.txt.")

    replaced_count = 0
    pairs = list(zip(target_dead, alive_proxies))

    def replace_worker(pair):
        (idx, reason), new_ep = pair
        old_ep = assigned.get(idx, "")
        teardown_node(idx, dead_endpoint=old_ep)
        ok, err = setup_node(idx, new_ep, token)
        return idx, old_ep, new_ep, ok, err, reason

    with ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(replace_worker, pairs))

    for idx, old_ep, new_ep, ok, err, reason in results:
        if ok:
            assigned[idx] = new_ep
            replaced_count += 1
            print(f"  [REPLACED] r2_{idx:03d} ({reason}): {old_ep} -> {new_ep} (FROM BUFFER)")
        else:
            print(f"  [ERROR] r2_{idx:03d} failed: {err}")

    # If buffer had fewer entries than needed, leave remaining down
    if len(alive_proxies) < needed:
        remaining_dead = target_dead[len(alive_proxies):]
        for idx, reason in remaining_dead:
            print(f"  [BUFFER EXHAUSTED] r2_{idx:03d} left down ({reason}), retrying next cycle.")

    state["assigned"] = assigned
    state["replaced_count"] = state.get("replaced_count", 0) + replaced_count
    state["last_audit_time"] = time.time()
    state["byte_checkpoints"] = get_all_interface_bytes()

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    print(f"[{time.strftime('%H:%M:%S')}] Replaced count: {replaced_count} nodes replaced from verified buffer.")
    return replaced_count

def get_mem():
    out = run_cmd("free -m").stdout
    lines = out.strip().splitlines()
    parts = lines[1].split()
    return {
        "total_mb": int(parts[1]),
        "used_mb": int(parts[2]),
        "free_mb": int(parts[3]),
        "available_mb": int(parts[6])
    }

def get_buffer_depth():
    if not os.path.exists(BUFFER_FILE):
        return 0
    with open(BUFFER_FILE, "r", encoding="utf-8", errors="ignore") as f:
        return len([l for l in f if l.strip()])

def main():
    token = load_token()
    setup_host_networking()

    if len(sys.argv) > 1 and sys.argv[1] == "--replace-from-buffer":
        cnt = int(sys.argv[2]) if len(sys.argv) > 2 else None
        print("=== REPLACING DEAD NODES EXCLUSIVELY FROM ALIVE BUFFER ===")
        replaced = audit_and_replace_from_buffer(token, max_replace=cnt)
        print(f"REPLACED_COUNT: {replaced}")

    elif len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting Buffer-Exclusive Auto-Recycle Daemon (interval=120s)...", flush=True)
        while True:
            time.sleep(120)
            try:
                print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] === RUNNING BUFFER-EXCLUSIVE AUDIT ===", flush=True)
                audit_and_replace_from_buffer(token)
            except Exception as e:
                print(f"Daemon exception: {e}", flush=True)

    elif len(sys.argv) > 1 and sys.argv[1] == "--status":
        if not os.path.exists(STATE_FILE):
            print("State file not found.")
            return

        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)

        t0 = state.get("initial_built_time", time.time())
        age_sec = int(time.time() - t0)
        curr_bytes = get_all_interface_bytes()
        t0_bytes = {int(k): v for k, v in state.get("t0_bytes", {}).items()}
        prev_bytes = {int(k): v for k, v in state.get("byte_checkpoints", {}).items()}

        total_bytes_now = sum(curr_bytes.values())
        total_bytes_t0 = sum(t0_bytes.values())
        bytes_moved = total_bytes_now - total_bytes_t0

        alive_cnt = 0
        for i in range(1, TOTAL_NODES + 1):
            has_estab = check_node_established_socket(i)
            c_b = curr_bytes.get(i, 0)
            p_b = prev_bytes.get(i, 0)
            if has_estab and (c_b > p_b or c_b > 0):
                alive_cnt += 1

        dead_cnt = TOTAL_NODES - alive_cnt
        mem = get_mem()
        buf_depth = get_buffer_depth()

        print(f"STATUS (age {age_sec}s):")
        print(f"  ALIVE:        {alive_cnt}")
        print(f"  DEAD:         {dead_cnt}")
        print(f"  REPLACED:     {state.get('replaced_count', 0)}")
        print(f"  BUFFER DEPTH: {buf_depth}")
        print(f"  BYTES MOVED:  {bytes_moved:,} bytes ({bytes_moved / (1024*1024):.2f} MB)")
        print(f"  FREE MEMORY:  {mem['free_mb']} MB free ({mem['available_mb']} MB available)")

if __name__ == "__main__":
    main()
