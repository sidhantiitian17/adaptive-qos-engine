#!/bin/bash
echo "=== BASELINE TEST (No QoS, plain FIFO queue) ==="

# CAKE hatao, default FIFO use karo
sudo ip netns exec gw tc qdisc del dev veth-gw-wan root 2>/dev/null
sudo ip netns exec gw tc qdisc add dev veth-gw-wan root netem rate 18mbit delay 1ms limit 1000

echo "Config: $(sudo ip netns exec gw tc qdisc show dev veth-gw-wan)"

# Server start
sudo ip netns exec wanhost iperf3 -s -D -p 5201

echo "Starting competing bulk flow (60s) + latency-sensitive ping flow (parallel)..."

# Bulk download competing traffic (background)
sudo ip netns exec lan2 iperf3 -c 10.0.3.2 -t 60 > baseline_bulk.log 2>&1 &
BULK_PID=$!

sleep 2

# Latency-sensitive flow (foreground, measured)
sudo ip netns exec lan1 ping -c 50 -i 1 10.0.3.2 > baseline_latency.log 2>&1

wait $BULK_PID
echo "Baseline test complete. Logs: baseline_bulk.log, baseline_latency.log"
