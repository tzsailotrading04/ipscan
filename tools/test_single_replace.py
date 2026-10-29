import os
import subprocess
import time

TOKEN = open("/mnt/d/DEpinFarm/config/traffmonetizer.token").read().strip()

def replace_node(i, new_proxy):
    proxy_ip, proxy_port = new_proxy.strip().split(":")
    ns_name = f"ns_traff_{i:03d}"
    node_dir = f"/var/run/traffmonetizer/node_{i:03d}"
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
    subprocess.run(ipt_cmds, shell=True)

    # 3. Kill old redsocks
    pid_file = f"{node_dir}/redsocks.pid"
    if os.path.exists(pid_file):
        try:
            pid = open(pid_file).read().strip()
            subprocess.run(f"kill -9 {pid} 2>/dev/null", shell=True)
        except Exception:
            pass

    # 4. Start new redsocks
    subprocess.run(f"ip netns exec {ns_name} /usr/bin/redsocks -c {node_dir}/redsocks.conf -p {node_dir}/redsocks.pid", shell=True)

    # 5. Kill old traff_cli for this node
    subprocess.run(f"pkill -9 -f '{dev_name}' 2>/dev/null", shell=True)
    time.sleep(0.5)

    # 6. Start new traff_cli
    cli_cmd = (
        f"export HOME={node_dir}; "
        f"nohup ip netns exec {ns_name} /tmp/traff_cli start accept "
        f"--token {TOKEN} --device-name {dev_name} > {node_dir}/cli.log 2>&1 &"
    )
    subprocess.run(cli_cmd, shell=True)
    print(f"Node {i:03d} replaced with {new_proxy}")

if __name__ == "__main__":
    replace_node(1, "103.91.68.1:82")
