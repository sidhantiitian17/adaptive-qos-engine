#!/bin/bash
echo "=== Test 1: lan1 -> wanhost (IPv4) ==="
sudo ip netns exec lan1 ping -c 3 10.0.3.2

echo "=== Test 2: lan1 -> wanhost (IPv6) ==="
sudo ip netns exec lan1 ping6 -c 3 fd00:3::2

echo "=== Test 3: lan2 -> wanhost (IPv4) ==="
sudo ip netns exec lan2 ping -c 3 10.0.3.2

echo "=== Test 4: lan1 -> lan2 ==="
sudo ip netns exec lan1 ping -c 3 10.0.2.2
