#!/bin/sh
set -e

PROXY_IP="104.168.19.113"
PROXY_PORT="443"
NS="ns_traff_001"
NODE_DIR="/var/run/traffmonetizer/node_001"

echo "=== 1. Tearing down $NS and veth ==="
ip netns del $NS 2>/dev/null || true
ip link del vth_001 2>/dev/null || true
rm -rf /etc/netns/$NS $NODE_DIR
mkdir -p $NODE_DIR

echo "=== Recreating host bridge and veth ==="
ip link add br0 type bridge 2>/dev/null || true
ip addr add 10.99.0.1/16 dev br0 2>/dev/null || true
ip link set br0 up
iptables -t nat -C POSTROUTING -s 10.99.0.0/16 -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s 10.99.0.0/16 -j MASQUERADE

ip netns add $NS
ip link add vth_001 type veth peer name vtc_001
ip link set vth_001 master br0 up
ip link set vtc_001 netns $NS

ip netns exec $NS ip addr add 10.99.1.1/16 dev vtc_001
ip netns exec $NS ip link set vtc_001 up
ip netns exec $NS ip link set lo up
ip netns exec $NS ip route add default via 10.99.0.1

mkdir -p /etc/netns/$NS
printf "nameserver 1.1.1.1\nnameserver 8.8.8.8\n" > /etc/netns/$NS/resolv.conf

echo "=== 2. Writing redsocks.conf and starting redsocks ==="
cat << 'EOF' > $NODE_DIR/redsocks.conf
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
    ip = 104.168.19.113;
    port = 443;
    type = http-connect;
    splice = false;
}
EOF

killall redsocks 2>/dev/null || true
ip netns exec $NS redsocks -c $NODE_DIR/redsocks.conf -p $NODE_DIR/redsocks.pid

echo "--- Redsocks PID file: ---"
cat $NODE_DIR/redsocks.pid
PID=$(cat $NODE_DIR/redsocks.pid)
kill -0 $PID && echo "PID $PID is ALIVE and RUNNING"

echo "--- ss -tlnp inside $NS: ---"
ip netns exec $NS ss -tlnp

echo "=== 3. Configuring iptables in $NS and printing NAT table ==="
ip netns exec $NS iptables -t nat -F
ip netns exec $NS iptables -t nat -N REDSOCKS
ip netns exec $NS iptables -t nat -A REDSOCKS -d 0.0.0.0/8 -j RETURN
ip netns exec $NS iptables -t nat -A REDSOCKS -d 10.0.0.0/8 -j RETURN
ip netns exec $NS iptables -t nat -A REDSOCKS -d 127.0.0.0/8 -j RETURN
ip netns exec $NS iptables -t nat -A REDSOCKS -d 169.254.0.0/16 -j RETURN
ip netns exec $NS iptables -t nat -A REDSOCKS -d 172.16.0.0/12 -j RETURN
ip netns exec $NS iptables -t nat -A REDSOCKS -d 192.168.0.0/16 -j RETURN
ip netns exec $NS iptables -t nat -A REDSOCKS -d $PROXY_IP -j RETURN
ip netns exec $NS iptables -t nat -A REDSOCKS -p tcp -j REDIRECT --to-ports 12345
ip netns exec $NS iptables -t nat -A OUTPUT -p tcp -j REDSOCKS

echo "--- iptables -t nat -L -n inside $NS: ---"
ip netns exec $NS iptables -t nat -L -n

echo "=== 4. Running curl inside $NS ==="
ip netns exec $NS curl -s -m 10 https://api.ipify.org
echo ""
