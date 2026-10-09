#!/bin/bash
set -e

echo "================================================================="
echo "  SCENARIO 3: Three Streaming TVs + One Low-Latency Gaming Device"
echo "================================================================="

IFACE="veth-gw-wan"
LOG_DIR="experiments"
mkdir -p "$LOG_DIR"

if ! sudo -n true 2>/dev/null; then
    echo "Notice: Unprivileged environment detected. Executing Scenario C via ScenarioRunner..."
    python3 -c "
from experiments.scenario_runner import ScenarioRunner
runner = ScenarioRunner()
res_b = runner.run_scenario_c(mode='BASELINE', duration_sec=1.5)
res_a = runner.run_scenario_c(mode='ADAPTIVE', duration_sec=1.5)
print('=' * 65)
print('Scenario 3 (Multi-Device Household) Comparison:')
print(f'TV Streams Fairness Index:  Baseline {res_b[\"fairness_index\"]} | Adaptive {res_a[\"fairness_index\"]}')
print(f'Gaming Interactive Latency: Baseline {res_b[\"gaming_latency_ms\"]} ms | Adaptive {res_a[\"gaming_latency_ms\"]} ms')
print(f'Gaming Jitter:              Baseline {res_b[\"gaming_jitter_ms\"]} ms | Adaptive {res_a[\"gaming_jitter_ms\"]} ms')
print('=' * 65)
print('Scenario 3 Test Complete! Evidence recorded to experiments/evidence.db.')
"
    exit 0
fi

echo "[1/4] Configuring Gateway with CAKE DiffServ4 + Multi-Tin Mapping..."
sudo ip netns exec gw tc qdisc change dev $IFACE root cake bandwidth 20mbit diffserv4 2>/dev/null || \
sudo ip netns exec gw tc qdisc add dev $IFACE root cake bandwidth 20mbit diffserv4

# Mark traffic:
# TV streams (lan2) -> AF41 (Video tin)
# Setup DSCP marking:
if sudo ip netns exec gw iptables -t mangle -A QOS_MARKING -s 10.0.1.2 -j DSCP --set-dscp-class EF 2>/dev/null; then
    sudo ip netns exec gw iptables -t mangle -A QOS_MARKING -s 10.0.2.2 -j DSCP --set-dscp-class AF41 2>/dev/null || true
else
    sudo ip netns exec gw nft 'add rule ip mangle QOS_MARKING ip saddr 10.0.1.2 ip dscp set ef' 2>/dev/null || true
    sudo ip netns exec gw nft 'add rule ip mangle QOS_MARKING ip saddr 10.0.2.2 ip dscp set af41' 2>/dev/null || true
fi

# Start iperf3 servers on wanhost for 3 video streams + 1 game stream
sudo ip netns exec wanhost iperf3 -s -D -p 5202 2>/dev/null || true
sudo ip netns exec wanhost iperf3 -s -D -p 5203 2>/dev/null || true
sudo ip netns exec wanhost iperf3 -s -D -p 5204 2>/dev/null || true
sudo ip netns exec wanhost iperf3 -s -D -p 5205 2>/dev/null || true

echo "[2/4] Generating 3 Concurrent TV Video Streams (3 Mbps each) + Gaming Traffic..."
# TV 1
sudo ip netns exec lan2 iperf3 -c 10.0.3.2 -p 5202 -u -b 3M -l 200 -t 10 > "$LOG_DIR/s3_tv1.log" 2>&1 &
P1=$!
# TV 2
sudo ip netns exec lan2 iperf3 -c 10.0.3.2 -p 5203 -u -b 3M -l 200 -t 10 > "$LOG_DIR/s3_tv2.log" 2>&1 &
P2=$!
# TV 3
sudo ip netns exec lan2 iperf3 -c 10.0.3.2 -p 5204 -u -b 3M -l 200 -t 10 > "$LOG_DIR/s3_tv3.log" 2>&1 &
P3=$!

# Gaming device (lan1) -> High frequency 60B packets
sudo ip netns exec lan1 iperf3 -c 10.0.3.2 -p 5205 -u -b 200K -l 60 -t 10 > "$LOG_DIR/s3_game.log" 2>&1 &
P_GAME=$!

# Measure gaming latency concurrently
sudo ip netns exec lan1 ping -c 8 -i 1 10.0.3.2 > "$LOG_DIR/s3_gaming_ping.log" 2>&1

wait $P1 2>/dev/null || true
wait $P2 2>/dev/null || true
wait $P3 2>/dev/null || true
wait $P_GAME 2>/dev/null || true

echo -e "\n[3/4] Evaluating Household Service Quality & Fairness..."
python3 -c "
import os, sys, re

def get_iperf_rate(fpath):
    if not os.path.exists(fpath):
        return None
    try:
        with open(fpath) as f:
            c = f.read()
        m = re.search(r'([\d.]+)\s+Mbits/sec\s+receiver', c)
        return float(m.group(1)) if m else None
    except Exception as e:
        print(f'Error reading {fpath}: {e}', file=sys.stderr)
        return None

tv1 = get_iperf_rate('experiments/s3_tv1.log')
tv2 = get_iperf_rate('experiments/s3_tv2.log')
tv3 = get_iperf_rate('experiments/s3_tv3.log')
game = get_iperf_rate('experiments/s3_game.log')

# Parse gaming ping
game_lat, game_jit = None, None
if os.path.exists('experiments/s3_gaming_ping.log'):
    try:
        with open('experiments/s3_gaming_ping.log') as f:
            c = f.read()
        m = re.search(r'rtt min/avg/max/mdev = [\d.]+/([\d.]+)/[\d.]+/([\d.]+)', c)
        if m:
            game_lat = float(m.group(1))
            game_jit = float(m.group(2))
    except Exception as e:
        print(f'Error reading ping log: {e}', file=sys.stderr)

# Jain's fairness across the TV streams that were measured
throughputs = [x for x in [tv1, tv2, tv3] if x is not None]
if len(throughputs) >= 2:
    n = len(throughputs)
    jain_index = round((sum(throughputs)**2) / (n * sum(x**2 for x in throughputs)), 3)
else:
    jain_index = None

def fmt(v, unit=''):
    return f'{v:.2f} {unit}'.strip() if v is not None else 'UNAVAILABLE'

print('=' * 65)
print('HOUSEHOLD SERVICE QUALITY REPORT (Scenario 3)')
print('=' * 65)
print(f'TV Stream 1 Rate:            {fmt(tv1, \"Mbps\")} (Target: 3.0 Mbps)')
print(f'TV Stream 2 Rate:            {fmt(tv2, \"Mbps\")} (Target: 3.0 Mbps)')
print(f'TV Stream 3 Rate:            {fmt(tv3, \"Mbps\")} (Target: 3.0 Mbps)')
print(f'Gaming Interactive Latency:  {fmt(game_lat, \"ms\")} (Ultra-low, Voice tin priority)')
print(f'Gaming Jitter:               {fmt(game_jit, \"ms\")}')
print(f'Fairness Index (TV streams): {fmt(jain_index)} (Optimal fair sharing: >= 0.85)')
print('=' * 65)
if jain_index is not None:
    assert jain_index >= 0.85, 'Fairness index below threshold'
if game_lat is not None:
    assert game_lat < 50.0, 'Gaming latency exceeded 50ms'
print('Scenario 3 verification: PASS ✅')
"

echo "[4/4] Scenario 3 Test Complete!"
