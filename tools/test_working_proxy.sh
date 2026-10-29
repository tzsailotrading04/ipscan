#!/bin/bash
set -e

PROXY_IP="104.168.19.113"
PROXY_PORT="443"
TOKEN="EPLSQERjvyYUO2S91i1VlWYI1VA5qCckw2TC6384tuY="

# 1. Host bridge & persistent netns
sysctl -w net.ipv4.ip_forward=1
iptables -P FORWARD ACCEPT
ip link add br0 type bridge 2>/dev/null || true
ip addr add 10.99.0.1/16 dev br0 2>/dev/null || true
ip link set br0 up
iptables -t nat -C POSTROUTING -s 10.99.0.0/16 -j MASQUERADE 2>/dev/null || \
iptables -t nat -A POSTROUTING -s 10.99.0.0/16 -j MASQUERADE

mkdir -p /run/netns
mountpoint -q /run/netns || mount -t tmpfs none /run/netns
mount --make-shared /run/netns 2>/dev/null || true

# 2. Re-create namespace and veth
ip netns del ns_traff_001 2>/dev/null || true
ip netns add ns_traff_001
ip link del vth_001 2>/dev/null || true
ip link add vth_001 type veth peer name vtc_001
ip link set vth_001 master br0 up
ip link set vtc_001 netns ns_traff_001

ip netns exec ns_traff_001 ip addr add 10.99.1.1/16 dev vtc_001
ip netns exec ns_traff_001 ip link set vtc_001 up
ip netns exec ns_traff_001 ip link set lo up
ip netns exec ns_traff_001 ip route add default via 10.99.0.1

mkdir -p /etc/netns/ns_traff_001
echo -e "nameserver 1.1.1.1\nnameserver 8.8.8.8" > /etc/netns/ns_traff_001/resolv.conf

# 3. Redsocks config
killall -9 redsocks 2>/dev/null || true
mkdir -p /var/run/traffmonetizer/node_001/.config/traffmonetizer
echo '{"": "00000000-0000-0000-0000-000000000001"}' > /var/run/traffmonetizer/node_001/.config/traffmonetizer/cli_device_ids.json

cat << EOF > /var/run/traffmonetizer/node_001/redsocks.conf
base {
    log_debug = on;
    log_info = on;
    log = "file:/var/run/traffmonetizer/node_001/redsocks.log";
    daemon = on;
    redirector = iptables;
}
redsocks {
    local_ip = 127.0.0.1;
    local_port = 12345;
    ip = ${PROXY_IP};
    port = ${PROXY_PORT};
    type = http-connect;
}
EOF

# 4. iptables inside namespace
ip netns exec ns_traff_001 iptables -t nat -F
ip netns exec ns_traff_001 iptables -t nat -N REDSOCKS || true
ip netns exec ns_traff_001 iptables -t nat -A REDSOCKS -d 0.0.0.0/8 -j RETURN
ip netns exec ns_traff_001 iptables -t nat -A REDSOCKS -d 10.0.0.0/8 -j RETURN
ip netns exec ns_traff_001 iptables -t nat -A REDSOCKS -d 127.0.0.0/8 -j RETURN
ip netns exec ns_traff_001 iptables -t nat -A REDSOCKS -d 169.254.0.0/16 -j RETURN
ip netns exec ns_traff_001 iptables -t nat -A REDSOCKS -d 172.16.0.0/12 -j RETURN
ip netns exec ns_traff_001 iptables -t nat -A REDSOCKS -d 192.168.0.0/16 -j RETURN
ip netns exec ns_traff_001 iptables -t nat -A REDSOCKS -d ${PROXY_IP} -j RETURN
ip netns exec ns_traff_001 iptables -t nat -A REDSOCKS -p tcp -j REDIRECT --to-ports 12345
ip netns exec ns_traff_001 iptables -t nat -A OUTPUT -p tcp -j REDSOCKS

# Start redsocks
ip netns exec ns_traff_001 redsocks -c /var/run/traffmonetizer/node_001/redsocks.conf -p /var/run/traffmonetizer/node_001/redsocks.pid
sleep 1

echo "=== TEST 1: TRANSPARENT CURL INSIDE ns_traff_001 ==="
TRANSPARENT_IP=$(ip netns exec ns_traff_001 curl -s -m 8 https://api.ipify.org)
echo "TRANSPARENT_IP_RETURNED: $TRANSPARENT_IP"

echo "=== TEST 2: RUNNING TRAFF_CLI INSIDE ns_traff_001 ==="
export HOME=/var/run/traffmonetizer/node_001
timeout 8 ip netns exec ns_traff_001 /tmp/traff_cli start accept --token "$TOKEN" --device-name "working_test_node" > /var/run/traffmonetizer/node_001/cli.log 2>&1 || true

echo "=== TRAFF_CLI LOG ==="
cat /var/run/traffmonetizer/node_001/cli.log
