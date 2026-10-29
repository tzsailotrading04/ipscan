#!/bin/bash
set -e

# 1. Enable IP forwarding and host NAT
sysctl -w net.ipv4.ip_forward=1
ip link add br0 type bridge 2>/dev/null || true
ip addr add 10.99.0.1/16 dev br0 2>/dev/null || true
ip link set br0 up

# Host iptables masquerade for 10.99.0.0/16
iptables -t nat -C POSTROUTING -s 10.99.0.0/16 -j MASQUERADE 2>/dev/null || \
iptables -t nat -A POSTROUTING -s 10.99.0.0/16 -j MASQUERADE

# 2. Setup test namespace
ip netns del test_ns 2>/dev/null || true
ip netns add test_ns

# 3. Create veth pair
ip link del veth_h_0 2>/dev/null || true
ip link add veth_h_0 type veth peer name veth_c_0
ip link set veth_h_0 master br0 up
ip link set veth_c_0 netns test_ns

# 4. Config inside namespace
ip netns exec test_ns ip addr add 10.99.0.2/16 dev veth_c_0
ip netns exec test_ns ip link set veth_c_0 up
ip netns exec test_ns ip link set lo up
ip netns exec test_ns ip route add default via 10.99.0.1

# Configure DNS inside namespace
mkdir -p /etc/netns/test_ns
echo "nameserver 1.1.1.1" > /etc/netns/test_ns/resolv.conf
echo "nameserver 8.8.8.8" >> /etc/netns/test_ns/resolv.conf

# Test raw connectivity from namespace
echo "Testing raw namespace internet ping..."
ip netns exec test_ns ping -c 1 -W 2 1.1.1.1

echo "Namespace network setup verified successfully!"
