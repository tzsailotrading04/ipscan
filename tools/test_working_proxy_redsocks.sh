#!/bin/bash
set -e

PROXY_IP="13.126.23.133"
PROXY_PORT="80"
TOKEN="EPLSQERjvyYUO2S91i1VlWYI1VA5qCckw2TC6384tuY="

ip netns del test_test 2>/dev/null || true
ip netns add test_test
ip link del vh_t 2>/dev/null || true
ip link add vh_t type veth peer name vc_t
ip link set vh_t master br0 up
ip link set vc_t netns test_test

ip netns exec test_test ip addr add 10.99.5.5/16 dev vc_t
ip netns exec test_test ip link set vc_t up
ip netns exec test_test ip link set lo up
ip netns exec test_test ip route add default via 10.99.0.1

mkdir -p /etc/netns/test_test
echo -e "nameserver 1.1.1.1\nnameserver 8.8.8.8" > /etc/netns/test_test/resolv.conf

mkdir -p /tmp/node_test/.config/traffmonetizer
echo '{"": "11111111-2222-3333-4444-555555555555"}' > /tmp/node_test/.config/traffmonetizer/cli_device_ids.json

cat << EOF > /tmp/node_test/redsocks.conf
base {
    log_debug = on;
    log_info = on;
    log = "file:/tmp/node_test/redsocks.log";
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

# iptables inside netns
ip netns exec test_test iptables -t nat -F
ip netns exec test_test iptables -t nat -N REDSOCKS
ip netns exec test_test iptables -t nat -A REDSOCKS -d 0.0.0.0/8 -j RETURN
ip netns exec test_test iptables -t nat -A REDSOCKS -d 10.0.0.0/8 -j RETURN
ip netns exec test_test iptables -t nat -A REDSOCKS -d 127.0.0.0/8 -j RETURN
ip netns exec test_test iptables -t nat -A REDSOCKS -d 169.254.0.0/16 -j RETURN
ip netns exec test_test iptables -t nat -A REDSOCKS -d 172.16.0.0/12 -j RETURN
ip netns exec test_test iptables -t nat -A REDSOCKS -d 192.168.0.0/16 -j RETURN
ip netns exec test_test iptables -t nat -A REDSOCKS -d ${PROXY_IP} -j RETURN
ip netns exec test_test iptables -t nat -A REDSOCKS -p tcp -j REDIRECT --to-ports 12345
ip netns exec test_test iptables -t nat -A OUTPUT -p tcp -j REDSOCKS

# Start redsocks
ip netns exec test_test redsocks -c /tmp/node_test/redsocks.conf
sleep 1

echo "Testing curl through redsocks in test_test..."
ip netns exec test_test curl -s -m 6 https://speed.cloudflare.com/__down?bytes=100 || echo "curl failed"

echo "Testing traff_cli through redsocks..."
export HOME=/tmp/node_test
timeout 10 ip netns exec test_test /tmp/traff_cli start accept --token "$TOKEN" --device-name "test_working_proxy" --verbose-logging || true

echo "--- Redsocks log: ---"
cat /tmp/node_test/redsocks.log
