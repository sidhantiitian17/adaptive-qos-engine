#!/bin/bash
echo "Cleaning up testbed..."
sudo ip netns del gw 2>/dev/null
sudo ip netns del lan1 2>/dev/null
sudo ip netns del lan2 2>/dev/null
sudo ip netns del wanhost 2>/dev/null
echo "Teardown complete."
