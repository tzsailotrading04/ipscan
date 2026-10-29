#!/bin/sh
set -e

PROXY_IP="104.168.19.113"
PROXY_PORT="443"
TOKEN="EPLSQERjvyYUO2S91i1VlWYI1VA5qCckw2TC6384tuY="
NS="ns_traff_001"
DEV_UUID="single-test-$(cat /proc/sys/kernel/random/uuid)"
NODE_DIR="/var/run/traffmonetizer/node_001"

echo "=== Cleaning up any old node_001 ==="
ip netns del $NS 2>/dev/null || true
ip link del vth_001 2>/dev/null || true
rm -rf /etc/netns/$NS $NODE_DIR
mkdir -p $NODE_DIR/.config/traffmonetizer

echo "{\"\": \"$DEV_UUID\"}" > $NODE_DIR/.config/traffmonetizer/cli_device_ids.json

echo "=== Writing redsocks.conf ==="
cat <<EOF > $NODE_DIR/redsocks.conf
base {
    log_debug = off;
    log_info = off;
    log = "file:$NODE_DIR/redsocks.log";
    daemon = on;
    redirector = iptables;
}
redsocks {
    local_ip = 127.0.0.1;
    local_port = 12345;
    ip = $PROXY_IP;
    port = $PROXY_PORT;
    type = http-connect;
}
EOF

echo "=== Setting up network namespace $NS ==="
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
echo "nameserver 1.1.1.1\nnameserver 8.8.8.8" > /etc/netns/$NS/resolv.conf

echo "=== Configuring iptables redirect in $NS ==="
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

echo "=== Starting redsocks in $NS ==="
ip netns exec $NS redsocks -c $NODE_DIR/redsocks.conf -p $NODE_DIR/redsocks.pid

echo "=== Testing curl through redsocks transparent proxy ==="
echo "Testing curl to api.ipify.org..."
ip netns exec $NS curl -s -m 8 https://api.ipify.org || echo "api.ipify.org curl failed"
echo ""

echo "=== Starting traff_cli in $NS ==="
export HOME=$NODE_DIR
ip netns exec $NS /tmp/traff_cli start accept --token "$TOKEN" --device-name "test_node_001" > $NODE_DIR/cli.log 2>&1 &
CLI_PID=$!
echo "traff_cli started with PID $CLI_PID, monitoring for 15s..."

for sec in $(seq 1 15); do
    sleep 1
    if grep -q "Status: " $NODE_DIR/cli.log 2>/dev/null; then
        echo "[T+${sec}s] Found Status line in cli.log:"
        grep "Status: " $NODE_DIR/cli.log | tail -n 5
    fi
done

echo "=== Final 25 lines of cli.log ==="
tail -n 25 $NODE_DIR/cli.log

echo "=== Redsocks log ==="
cat $NODE_DIR/redsocks.log | tail -n 15

# Clean up traff_cli process
kill $CLI_PID 2>/dev/null || true
