#!/bin/bash
set -e

echo "=== Checking if testbed exists ==="
if ! ip netns list | grep -q "gw"; then
    echo "Testbed not found. Setting up..."
    cd testbed
    sudo ./setup_topo.sh
    cd ..
else
    echo "Testbed already exists, skipping setup."
fi

echo "=== Applying CAKE enforcement ==="
cd enforcement
./apply_cake.sh 100mbit
cd ..

echo "=== Setting NetEm WAN simulation (20mbit) ==="
cd testbed
python3 wan_simulator.py 20
cd ..

echo "=== All systems ready! ==="
ip netns list
sudo ip netns exec wanhost tc qdisc show dev veth-wan-gw
