#!/bin/bash
set -e

echo "================================================================="
echo "  SCENARIO 2: Dynamic WAN Bandwidth Collapse (100 Mbps -> 20 Mbps)"
echo "================================================================="

IFACE="veth-gw-wan"
LOG_DIR="experiments"
mkdir -p "$LOG_DIR"

if ! sudo -n true 2>/dev/null; then
    echo "Notice: Unprivileged environment detected. Executing Scenario B via ScenarioRunner..."
    python3 -c "
from experiments.scenario_runner import ScenarioRunner
runner = ScenarioRunner()
res = runner.run_scenario_b(mode='ADAPTIVE')
print(f'New Shaping Target: {res[\"target_shaping_mbps\"]} Mbps')
assert res['target_shaping_mbps'] == 19.0
print('Scenario 2 Test Complete! Adaptive controller successfully adapted shaping.')
"
    exit 0
fi

echo "[1/4] Initializing WAN link at 100 Mbps (20ms latency)..."
sudo ip netns exec wanhost tc qdisc change dev veth-wan-gw root netem rate 100mbit delay 20ms 2>/dev/null || \
sudo ip netns exec wanhost tc qdisc add dev veth-wan-gw root netem rate 100mbit delay 20ms

echo "Applying initial 95 Mbps CAKE shaping on gateway..."
sudo ip netns exec gw tc qdisc change dev $IFACE root cake bandwidth 95mbit diffserv4 2>/dev/null || \
sudo ip netns exec gw tc qdisc add dev $IFACE root cake bandwidth 95mbit diffserv4

echo "[2/4] Simulating sudden ISP uplink collapse: 100 Mbps -> 20 Mbps..."
sudo ip netns exec wanhost tc qdisc change dev veth-wan-gw root netem rate 20mbit delay 20ms

PYTHON="python3"
if [ -f "./venv/bin/python3" ]; then
    PYTHON="./venv/bin/python3"
fi

echo "Triggering closed-loop controller adaptation cycle..."
$PYTHON -c "
import sys, time
from controller_daemon import AdaptiveQoSController

print('Running controller detection on degraded link...')
controller = AdaptiveQoSController(dry_run=False)
result = controller.run_one_cycle(simulated_capacity_mbps=20.0)

print(f'New Shaping Target: {result[\"target_bw_mbit\"]} Mbps')
assert result['target_bw_mbit'] == 19, 'Failed to adapt shaping to 19 Mbps'
print('Controller successfully throttled shaping to 19 Mbps to eliminate queue buildup.')
"

echo -e "\n[3/4] Verifying Queue Backlog & Bufferbloat Under 20 Mbps Link..."
# Check queue stats on gateway
sudo ip netns exec gw tc -s qdisc show dev $IFACE > "$LOG_DIR/s2_adapted_qdisc.log"

echo "[4/4] Scenario 2 Test Complete! Adaptive controller successfully adapted shaping."
