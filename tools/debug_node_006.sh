#!/bin/bash
set -e

# Update node_006 redsocks.conf to enable debug
cat << 'EOF' > /var/run/traffmonetizer/node_006/redsocks.conf
base {
    log_debug = on;
    log_info = on;
    log = "file:/var/run/traffmonetizer/node_006/redsocks.log";
    daemon = on;
    redirector = iptables;
}
redsocks {
    local_ip = 127.0.0.1;
    local_port = 12345;
    ip = 34.228.226.117;
    port = 8080;
    type = http-connect;
}
EOF

# Restart redsocks in ns_traff_006
PID=$(cat /var/run/traffmonetizer/node_006/redsocks.pid 2>/dev/null || true)
[ -n "$PID" ] && kill $PID 2>/dev/null || true
ip netns exec ns_traff_006 redsocks -c /var/run/traffmonetizer/node_006/redsocks.conf -p /var/run/traffmonetizer/node_006/redsocks.pid
sleep 1

# Truncate cli.log and wait 8 seconds
> /var/run/traffmonetizer/node_006/cli.log
sleep 8

echo "=== CLI LOG ==="
cat /var/run/traffmonetizer/node_006/cli.log
echo "=== REDSOCKS LOG ==="
cat /var/run/traffmonetizer/node_006/redsocks.log
