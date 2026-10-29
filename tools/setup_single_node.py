import os
import subprocess

def run(cmd):
    print(f"+ {cmd}")
    res = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.stdout:
        print(res.stdout, end="")
    if res.stderr:
        print(res.stderr, end="")
    return res

def main():
    proxy_ip = "104.168.19.113"
    proxy_port = "443"
    ns_name = "ns_traff_001"
    vh_name = "vth_001"
    vc_name = "vtc_001"
    node_dir = "/var/run/traffmonetizer/node_001"

    with open("/mnt/d/DEpinFarm/config/traffmonetizer.token") as f:
        token = f.read().strip()

    # Teardown
    run(f"ip netns del {ns_name} 2>/dev/null || true")
    run(f"ip link del {vh_name} 2>/dev/null || true")
    run(f"rm -rf /etc/netns/{ns_name} {node_dir}")
    os.makedirs(f"/etc/netns/{ns_name}", exist_ok=True)
    os.makedirs(node_dir, exist_ok=True)
    os.makedirs(f"{node_dir}/.config/traffmonetizer", exist_ok=True)

    with open(f"{node_dir}/.config/traffmonetizer/cli_device_ids.json", "w") as f:
        f.write('{"": "dc000000-0000-0000-0000-000000000001"}\n')

    # Recreate netns and veth
    run(f"ip netns add {ns_name}")
    run(f"ip link add {vh_name} type veth peer name {vc_name}")
    run(f"ip link set {vh_name} master br0 up")
    run(f"ip link set {vc_name} netns {ns_name}")

    run(f"ip netns exec {ns_name} ip addr add 10.99.1.1/16 dev {vc_name}")
    run(f"ip netns exec {ns_name} ip link set {vc_name} up")
    run(f"ip netns exec {ns_name} ip link set lo up")
    run(f"ip netns exec {ns_name} ip route add default via 10.99.0.1")

    with open(f"/etc/netns/{ns_name}/resolv.conf", "w") as f:
        f.write("nameserver 1.1.1.1\nnameserver 8.8.8.8\n")

    conf_content = f"""base {{
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
        f.write(conf_content)

    ipt = f"""
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
    run(ipt)

    # Start redsocks
    run(f"ip netns exec {ns_name} /usr/bin/redsocks -c {node_dir}/redsocks.conf -p {node_dir}/redsocks.pid")

    # Start traff_cli
    cli_cmd = (
        f"export HOME={node_dir}; "
        f"nohup ip netns exec {ns_name} /tmp/traff_cli start accept "
        f"--token {token} --device-name dc_node_001 > {node_dir}/cli.log 2>&1 &"
    )
    run(cli_cmd)

if __name__ == "__main__":
    main()
