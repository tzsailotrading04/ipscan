#!/bin/bash
set -e

PROXY_IP="123.121.132.234"
PROXY_PORT="8888"

killall -9 redsocks 2>/dev/null || true

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

# Update iptables bypass for this proxy IP
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

echo "Testing curl -x http://127.0.0.1:12345 https://api.ipify.org..."
ip netns exec ns_traff_001 curl -s -m 8 -x http://127.0.0.1:12345 https://api.ipify.org || echo "curl failed"

echo "Testing TRANSPARENT curl https://api.ipify.org..."
ip netns exec ns_traff_001 curl -s -m 8 https://api.ipify.org || echo "transparent curl failed"
