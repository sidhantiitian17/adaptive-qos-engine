#!/bin/bash
IFACE="veth-gw-wan"
BANDWIDTH="${1:-100mbit}"

# Pehle check karo already CAKE lagi hai ya nahi
if sudo ip netns exec gw tc qdisc show dev $IFACE | grep -q "cake"; then
    echo "CAKE already applied, updating bandwidth to $BANDWIDTH..."
    sudo ip netns exec gw tc qdisc change dev $IFACE root cake bandwidth $BANDWIDTH diffserv4
else
    echo "Applying CAKE on $IFACE with bandwidth=$BANDWIDTH..."
    sudo ip netns exec gw tc qdisc add dev $IFACE root cake bandwidth $BANDWIDTH diffserv4
fi

echo "Done. Current qdisc:"
sudo ip netns exec gw tc qdisc show dev $IFACE
