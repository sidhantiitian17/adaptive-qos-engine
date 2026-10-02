#!/bin/bash
set -e

echo "============================================================"
echo "  ENVIRONMENT RESET — Restore Known-Safe State"
echo "============================================================"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "[1/5] Clearing any QoS marking rules..."
if sudo -n true 2>/dev/null; then
    sudo ip netns exec gw iptables -t mangle -F QOS_MARKING 2>/dev/null || true
    sudo ip netns exec gw ip6tables -t mangle -F QOS_MARKING 2>/dev/null || true
    echo "  iptables/ip6tables QOS_MARKING chain flushed."
else
    echo "  (skipped — no passwordless sudo; DSCP rules unchanged)"
fi

echo "[2/5] Resetting CAKE qdisc to default 100 Mbps..."
if sudo -n true 2>/dev/null; then
    sudo ip netns exec gw tc qdisc change dev veth-gw-wan root cake bandwidth 100mbit diffserv4 2>/dev/null || \
    sudo ip netns exec gw tc qdisc add dev veth-gw-wan root cake bandwidth 100mbit diffserv4 2>/dev/null || true
    echo "  CAKE reset to 100mbit diffserv4."
else
    echo "  (skipped — no passwordless sudo; qdisc unchanged)"
fi

echo "[3/5] Resetting WAN emulation to 100 Mbps / 20ms..."
if sudo -n true 2>/dev/null; then
    sudo ip netns exec wanhost tc qdisc change dev veth-wan-gw root netem rate 100mbit delay 20ms 2>/dev/null || \
    sudo ip netns exec wanhost tc qdisc add dev veth-wan-gw root netem rate 100mbit delay 20ms 2>/dev/null || true
    echo "  NetEm reset to 100mbit / 20ms."
else
    echo "  (skipped — no passwordless sudo; WAN emulation unchanged)"
fi

echo "[4/5] Clearing metrics log..."
> dashboard/metrics_log.jsonl 2>/dev/null || true
echo "  metrics_log.jsonl cleared."

echo "[5/5] Killing stale iperf3 servers..."
if sudo -n true 2>/dev/null; then
    sudo ip netns exec wanhost pkill -f iperf3 2>/dev/null || true
    sudo ip netns exec lan1 pkill -f iperf3 2>/dev/null || true
    sudo ip netns exec lan2 pkill -f iperf3 2>/dev/null || true
    echo "  Stale iperf3 processes cleaned."
else
    echo "  (skipped — no passwordless sudo)"
fi

echo ""
echo "============================================================"
echo "  Environment reset complete. Ready for next experiment."
echo "============================================================"
