#!/bin/bash
IFACE="veth-gw-wan"
echo "Removing qdisc from $IFACE..."
sudo ip netns exec gw tc qdisc del dev $IFACE root 2>/dev/null
echo "Done."
