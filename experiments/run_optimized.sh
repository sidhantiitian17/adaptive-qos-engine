#!/bin/bash
echo "=== OPTIMIZED TEST (CAKE with DiffServ4) ==="

sudo ip netns exec gw tc qdisc del dev veth-gw-wan root 2>/dev/null
sudo ip netns exec gw tc qdisc add dev veth-gw-wan root cake bandwidth 18mbit diffserv4

echo "Config: $(sudo ip netns exec gw tc qdisc show dev veth-gw-wan)"

sudo ip netns exec wanhost iperf3 -s -D -p 5201

echo "Starting competing bulk flow (60s) + latency-sensitive ping flow (parallel)..."

sudo ip netns exec lan2 iperf3 -c 10.0.3.2 -t 60  > optimized_bulk.log 2>&1 &
BULK_PID=$!

sleep 2

sudo ip netns exec lan1 ping -c 50 -i 1 10.0.3.2 > optimized_latency.log 2>&1

wait $BULK_PID
echo "Optimized test complete. Logs: optimized_bulk.log, optimized_latency.log"
