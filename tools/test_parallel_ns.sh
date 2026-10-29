#!/bin/bash
set -e

# Setup 2 test namespaces: ns_test_1 and ns_test_2
for i in 1 2; do
    NS="ns_test_$i"
    ip netns del $NS 2>/dev/null || true
    ip netns add $NS
    ip link del "vh_$i" 2>/dev/null || true
    ip link add "vh_$i" type veth peer name "vc_$i"
    ip link set "vh_$i" master br0 up
    ip link set "vc_$i" netns $NS
    ip netns exec $NS ip addr add "10.99.2.$i/16" dev "vc_$i"
    ip netns exec $NS ip link set "vc_$i" up
    ip netns exec $NS ip link set lo up
    ip netns exec $NS ip route add default via 10.99.0.1
    mkdir -p "/etc/netns/$NS"
    echo -e "nameserver 1.1.1.1\nnameserver 8.8.8.8" > "/etc/netns/$NS/resolv.conf"
done

echo "Testing parallel curl from both namespaces:"
IP1=$(ip netns exec ns_test_1 curl -s -m 5 https://api.ipify.org)
IP2=$(ip netns exec ns_test_2 curl -s -m 5 https://api.ipify.org)
echo "NS1: $IP1"
echo "NS2: $IP2"

# Clean up test namespaces
ip netns del ns_test_1
ip netns del ns_test_2
ip link del vh_1 2>/dev/null || true
ip link del vh_2 2>/dev/null || true
rm -rf /etc/netns/ns_test_1 /etc/netns/ns_test_2

echo "Parallel namespace test passed!"
