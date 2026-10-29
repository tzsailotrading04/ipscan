#!/bin/bash
set -e

PROXY_IP="101.132.249.207"
PROXY_PORT="9080"

# Kill any prior redsocks
killall redsocks 2>/dev/null || true

cat << EOF > /tmp/test_redsocks.conf
base {
    log_debug = off;
    log_info = off;
    log = stderr;
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

# Start redsocks inside netns
ip netns exec test_ns redsocks -c /tmp/test_redsocks.conf
sleep 1

# Setup iptables redirect
ip netns exec test_ns iptables -t nat -F
ip netns exec test_ns iptables -t nat -N REDSOCKS || true
ip netns exec test_ns iptables -t nat -A REDSOCKS -d 0.0.0.0/8 -j RETURN
ip netns exec test_ns iptables -t nat -A REDSOCKS -d 10.0.0.0/8 -j RETURN
ip netns exec test_ns iptables -t nat -A REDSOCKS -d 127.0.0.0/8 -j RETURN
ip netns exec test_ns iptables -t nat -A REDSOCKS -d 169.254.0.0/16 -j RETURN
ip netns exec test_ns iptables -t nat -A REDSOCKS -d 172.16.0.0/12 -j RETURN
ip netns exec test_ns iptables -t nat -A REDSOCKS -d 192.168.0.0/16 -j RETURN
ip netns exec test_ns iptables -t nat -A REDSOCKS -d ${PROXY_IP} -j RETURN
ip netns exec test_ns iptables -t nat -A REDSOCKS -p tcp -j REDIRECT --to-ports 12345
ip netns exec test_ns iptables -t nat -A OUTPUT -p tcp -j REDSOCKS

echo "Testing TRANSPARENT curl without proxy flag from inside namespace..."
OUT_IP=$(ip netns exec test_ns curl -s -m 8 http://api.ipify.org)
echo "RESULT_TRANSPARENT_IP: $OUT_IP"

if [ "$OUT_IP" == "$PROXY_IP" ]; then
    echo "SUCCESS: Transparent redirection through redsocks confirmed!"
else
    echo "MISMATCH: Got $OUT_IP, expected $PROXY_IP"
fi
