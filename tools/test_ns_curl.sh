#!/bin/bash
set -e

# Docker defaults FORWARD to DROP! Must accept forward on br0:
iptables -P FORWARD ACCEPT

echo "Testing curl from namespace..."
ip netns exec test_ns curl -s -m 5 https://api.ipify.org || ip netns exec test_ns curl -s -m 5 http://checkip.amazonaws.com
