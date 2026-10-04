#!/bin/bash
set -e

echo "================================================================="
echo "  SCENARIO 1: Large Bulk Download during Active Video Conference "
echo "================================================================="

IFACE="veth-gw-wan"
LOG_DIR="experiments"
mkdir -p "$LOG_DIR"

if ! sudo -n true 2>/dev/null; then
    echo "Notice: Unprivileged environment detected. Executing Scenario A via ScenarioRunner..."
    python3 -c "
from experiments.scenario_runner import ScenarioRunner
runner = ScenarioRunner()
res_b = runner.run_scenario_a(mode='BASELINE', duration_sec=1.5)
res_a = runner.run_scenario_a(mode='ADAPTIVE', duration_sec=1.5)
print('=' * 65)
print('Scenario 1 (Bulk vs Video) Comparison:')
print(f'Video Throughput: Baseline {res_b[\"video_throughput_mbps\"]} Mbps | Adaptive {res_a[\"video_throughput_mbps\"]} Mbps')
print(f'Bulk Throughput:  Baseline {res_b[\"bulk_throughput_mbps\"]} Mbps | Adaptive {res_a[\"bulk_throughput_mbps\"]} Mbps')
print(f'Video Latency:    Baseline {res_b[\"latency_ms\"]} ms | Adaptive {res_a[\"latency_ms\"]} ms')
print(f'Video Jitter:     Baseline {res_b[\"jitter_ms\"]} ms | Adaptive {res_a[\"jitter_ms\"]} ms')
print('=' * 65)
print('Scenario 1 Test Complete! Evidence recorded to experiments/evidence.db.')
"
    exit 0
fi

# 1. Baseline Test (Unmanaged FIFO Queue)
echo -e "\n[1/4] Running Baseline (Unmanaged FIFO with Bufferbloat)..."
sudo ip netns exec gw tc qdisc del dev $IFACE root 2>/dev/null || true
sudo ip netns exec gw tc qdisc add dev $IFACE root netem rate 18mbit delay 20ms limit 1000

# Start server
sudo ip netns exec wanhost iperf3 -s -D -p 5201 2>/dev/null || true
sudo ip netns exec wanhost iperf3 -s -D -p 5202 2>/dev/null || true

# Start competing bulk download
sudo ip netns exec lan2 iperf3 -c 10.0.3.2 -p 5201 -t 15 > "$LOG_DIR/s1_baseline_bulk.log" 2>&1 &
BULK_PID=$!
sleep 1

# Start video call stream (UDP 200B packets, ~1Mbps)
sudo ip netns exec lan1 iperf3 -c 10.0.3.2 -p 5202 -u -b 1M -l 200 -t 12 > "$LOG_DIR/s1_baseline_video.log" 2>&1 &
VIDEO_PID=$!

# Measure interactive latency concurrently
sudo ip netns exec lan1 ping -c 10 -i 1 10.0.3.2 > "$LOG_DIR/s1_baseline_ping.log" 2>&1

wait $BULK_PID 2>/dev/null || true
wait $VIDEO_PID 2>/dev/null || true
echo "Baseline completed."

# 2. Optimized Test (CAKE + DiffServ4 Packet Marking)
echo -e "\n[2/4] Running Optimized (Adaptive QoS Engine: CAKE DiffServ4)..."
sudo ip netns exec gw tc qdisc del dev $IFACE root 2>/dev/null || true
sudo ip netns exec gw tc qdisc add dev $IFACE root cake bandwidth 18mbit diffserv4

# Setup DSCP marking: lan1 video -> AF41, lan2 bulk -> CS1
sudo ip netns exec gw iptables -t mangle -F QOS_MARKING 2>/dev/null || sudo ip netns exec gw iptables -t mangle -N QOS_MARKING 2>/dev/null || true
sudo ip netns exec gw iptables -t mangle -C PREROUTING -j QOS_MARKING 2>/dev/null || sudo ip netns exec gw iptables -t mangle -I PREROUTING -j QOS_MARKING
sudo ip netns exec gw iptables -t mangle -A QOS_MARKING -s 10.0.1.2 -j DSCP --set-dscp-class AF41
sudo ip netns exec gw iptables -t mangle -A QOS_MARKING -s 10.0.2.2 -j DSCP --set-dscp-class CS1

# Start competing bulk download
sudo ip netns exec lan2 iperf3 -c 10.0.3.2 -p 5201 -t 15 > "$LOG_DIR/s1_optimized_bulk.log" 2>&1 &
BULK_PID=$!
sleep 1

# Start video call stream
sudo ip netns exec lan1 iperf3 -c 10.0.3.2 -p 5202 -u -b 1M -l 200 -t 12 > "$LOG_DIR/s1_optimized_video.log" 2>&1 &
VIDEO_PID=$!

# Measure interactive latency
sudo ip netns exec lan1 ping -c 10 -i 1 10.0.3.2 > "$LOG_DIR/s1_optimized_ping.log" 2>&1

wait $BULK_PID 2>/dev/null || true
wait $VIDEO_PID 2>/dev/null || true
echo "Optimized completed."

# 3. Parse and Compare Results
echo -e "\n[3/4] Parsing Scenario 1 Comparison..."
python3 -c "
import os, sys, re

def parse_ping(fpath):
    if not os.path.exists(fpath):
        return None, None, None
    try:
        with open(fpath) as f:
            c = f.read()
        m = re.search(r'rtt min/avg/max/mdev = [\d.]+/([\d.]+)/[\d.]+/([\d.]+)', c)
        l = re.search(r'(\d+)% packet loss', c)
        if not m:
            return None, None, None
        return float(m.group(1)), float(m.group(2)), float(l.group(1)) if l else 0.0
    except Exception as e:
        print(f'Error reading ping log {fpath}: {e}', file=sys.stderr)
        return None, None, None

def parse_iperf(fpath):
    if not os.path.exists(fpath):
        return None
    try:
        with open(fpath) as f:
            c = f.read()
        m = re.search(r'([\d.]+) Mbits/sec\s+receiver', c)
        return float(m.group(1)) if m else None
    except Exception as e:
        print(f'Error reading iperf log {fpath}: {e}', file=sys.stderr)
        return None

b_lat, b_jit, b_loss = parse_ping('experiments/s1_baseline_ping.log')
o_lat, o_jit, o_loss = parse_ping('experiments/s1_optimized_ping.log')
b_bulk = parse_iperf('experiments/s1_baseline_bulk.log')
o_bulk = parse_iperf('experiments/s1_optimized_bulk.log')

def fmt(v, unit=''):
    return f'{v:.2f} {unit}'.strip() if v is not None else 'UNAVAILABLE'

def calc_impr(b, o):
    if b is not None and o is not None and b > 0:
        return f'{round((b - o) / b * 100, 1)}% reduction'
    return 'N/A'

print('=' * 65)
print(f'Metric                      Baseline (FIFO)   Optimized (CAKE)   Improvement')
print('-' * 65)
print(f'Video Latency (ms)          {fmt(b_lat, \"ms\"):<17} {fmt(o_lat, \"ms\"):<18} {calc_impr(b_lat, o_lat)}')
print(f'Video Jitter (ms)           {fmt(b_jit, \"ms\"):<17} {fmt(o_jit, \"ms\"):<18} {calc_impr(b_jit, o_jit)}')
print(f'Packet Loss (%)             {fmt(b_loss, \"%\"):<17} {fmt(o_loss, \"%\"):<18}')
print(f'Bulk Throughput (Mbps)      {fmt(b_bulk, \"Mbps\"):<17} {fmt(o_bulk, \"Mbps\"):<18}')
print('=' * 65)
"

echo -e "\n[4/4] Scenario 1 Test Complete! Logs saved to experiments/."
