#!/bin/bash
set -e

IFACE="veth-gw-wan"
echo "=== Step 1: Ensure CAKE diffserv4 is active on $IFACE ==="
sudo ip netns exec gw tc qdisc change dev $IFACE root cake bandwidth 50mbit diffserv4 2>/dev/null || \
sudo ip netns exec gw tc qdisc add dev $IFACE root cake bandwidth 50mbit diffserv4

echo "=== Step 2: Set DSCP marking rules in gateway mangle table ==="
sudo ip netns exec gw iptables -t mangle -F QOS_MARKING 2>/dev/null || sudo ip netns exec gw iptables -t mangle -N QOS_MARKING 2>/dev/null || true
sudo ip netns exec gw iptables -t mangle -C PREROUTING -j QOS_MARKING 2>/dev/null || sudo ip netns exec gw iptables -t mangle -I PREROUTING -j QOS_MARKING

# lan1 (10.0.1.2) -> Video conference (AF41)
sudo ip netns exec gw iptables -t mangle -A QOS_MARKING -s 10.0.1.2 -j DSCP --set-dscp-class AF41
# lan2 (10.0.2.2) -> Bulk download (CS1)
sudo ip netns exec gw iptables -t mangle -A QOS_MARKING -s 10.0.2.2 -j DSCP --set-dscp-class CS1

echo "Current mangle rules:"
sudo ip netns exec gw iptables -t mangle -L QOS_MARKING -v -n

echo "=== Step 3: Start iperf3 server on wanhost ==="
sudo ip netns exec wanhost iperf3 -s -D -p 5201 2>/dev/null || true
sudo ip netns exec wanhost iperf3 -s -D -p 5202 2>/dev/null || true

echo "=== Step 4: Generating concurrent traffic ==="
echo "Generating Bulk traffic from lan2 (CS1) -> wanhost:5201..."
sudo ip netns exec lan2 iperf3 -c 10.0.3.2 -p 5201 -t 4 > /dev/null 2>&1 &
PID_BULK=$!

echo "Generating Video traffic from lan1 (AF41) -> wanhost:5202..."
sudo ip netns exec lan1 iperf3 -c 10.0.3.2 -p 5202 -u -b 5M -l 200 -t 4 > /dev/null 2>&1 &
PID_VIDEO=$!

wait $PID_BULK
wait $PID_VIDEO

echo -e "\n=== Step 5: CAKE DiffServ4 Tin Statistics ==="
sudo ip netns exec gw tc -s qdisc show dev $IFACE

echo -e "\n=== Verification Summary ==="
echo "DiffServ4 Tin utilization successfully recorded."
