#!/bin/bash
set -e

echo "[1/6] Creating network namespaces..."
sudo ip netns add gw
sudo ip netns add lan1
sudo ip netns add lan2
sudo ip netns add wanhost

echo "[2/6] Creating veth pairs (virtual cables)..."
sudo ip link add veth-lan1 type veth peer name veth-lan1-gw
sudo ip link add veth-lan2 type veth peer name veth-lan2-gw
sudo ip link add veth-gw-wan type veth peer name veth-wan-gw

echo "[3/6] Moving veth ends into their namespaces..."
sudo ip link set veth-lan1 netns lan1
sudo ip link set veth-lan1-gw netns gw
sudo ip link set veth-lan2 netns lan2
sudo ip link set veth-lan2-gw netns gw
sudo ip link set veth-gw-wan netns gw
sudo ip link set veth-wan-gw netns wanhost

echo "[4/6] Assigning IP addresses (IPv4 + IPv6)..."
sudo ip netns exec lan1 ip addr add 10.0.1.2/24 dev veth-lan1
sudo ip netns exec lan1 ip addr add fd00:1::2/64 dev veth-lan1
sudo ip netns exec gw   ip addr add 10.0.1.1/24 dev veth-lan1-gw
sudo ip netns exec gw   ip addr add fd00:1::1/64 dev veth-lan1-gw

sudo ip netns exec lan2 ip addr add 10.0.2.2/24 dev veth-lan2
sudo ip netns exec lan2 ip addr add fd00:2::2/64 dev veth-lan2
sudo ip netns exec gw   ip addr add 10.0.2.1/24 dev veth-lan2-gw
sudo ip netns exec gw   ip addr add fd00:2::1/64 dev veth-lan2-gw

sudo ip netns exec gw      ip addr add 10.0.3.1/24 dev veth-gw-wan
sudo ip netns exec gw      ip addr add fd00:3::1/64 dev veth-gw-wan
sudo ip netns exec wanhost ip addr add 10.0.3.2/24 dev veth-wan-gw
sudo ip netns exec wanhost ip addr add fd00:3::2/64 dev veth-wan-gw

echo "[5/6] Bringing interfaces up + setting routes..."
sudo ip netns exec lan1 ip link set veth-lan1 up
sudo ip netns exec lan1 ip link set lo up
sudo ip netns exec lan2 ip link set veth-lan2 up
sudo ip netns exec lan2 ip link set lo up
sudo ip netns exec gw ip link set veth-lan1-gw up
sudo ip netns exec gw ip link set veth-lan2-gw up
sudo ip netns exec gw ip link set veth-gw-wan up
sudo ip netns exec gw ip link set lo up
sudo ip netns exec wanhost ip link set veth-wan-gw up
sudo ip netns exec wanhost ip link set lo up

sudo ip netns exec gw sysctl -w net.ipv4.ip_forward=1
sudo ip netns exec gw sysctl -w net.ipv6.conf.all.forwarding=1

sudo ip netns exec lan1 ip route add default via 10.0.1.1
sudo ip netns exec lan1 ip -6 route add default via fd00:1::1
sudo ip netns exec lan2 ip route add default via 10.0.2.1
sudo ip netns exec lan2 ip -6 route add default via fd00:2::1

sudo ip netns exec wanhost ip route add 10.0.1.0/24 via 10.0.3.1
sudo ip netns exec wanhost ip route add 10.0.2.0/24 via 10.0.3.1
sudo ip netns exec wanhost ip -6 route add fd00:1::/64 via fd00:3::1
sudo ip netns exec wanhost ip -6 route add fd00:2::/64 via fd00:3::1

echo "[6/6] Setup complete!"
