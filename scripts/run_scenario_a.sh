#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# Self-exec inside unshare -rn (user namespace) if not already root
if [ "$(id -u)" -ne 0 ]; then
    if command -v unshare >/dev/null 2>&1; then
        exec unshare -rn bash "$0" "$@"
    fi
fi

# In rootless user namespace, bring up lo
ip link set dev lo up 2>/dev/null || true

PYTHON="python3"
if [ -f "./venv/bin/python3" ]; then
    PYTHON="./venv/bin/python3"
fi

echo "================================================================="
echo "   RUNNING SCENARIO A: BULK DOWNLOAD VS VIDEO CONFERENCE         "
echo "================================================================="

$PYTHON -c "
from experiments.scenario_runner import ScenarioRunner
runner = ScenarioRunner()
print('\n[1/2] Running BASELINE (Unmanaged FIFO with Bufferbloat)...')
res_base = runner.run_scenario_a(mode='BASELINE', duration_sec=4.0)
print('  Baseline Metrics:', res_base)

print('\n[2/2] Running ADAPTIVE (CAKE DiffServ4 Multi-Tin Shaping)...')
res_adapt = runner.run_scenario_a(mode='ADAPTIVE', duration_sec=4.0)
print('  Adaptive Metrics:', res_adapt)

print('\n' + '=' * 65)
print('SCENARIO A COMPARISON RESULT')
print('=' * 65)
print(f'Video Throughput:  Baseline {res_base[\"video_throughput_mbps\"]} Mbps | Adaptive {res_adapt[\"video_throughput_mbps\"]} Mbps')
print(f'Bulk Throughput:   Baseline {res_base[\"bulk_throughput_mbps\"]} Mbps | Adaptive {res_adapt[\"bulk_throughput_mbps\"]} Mbps')
print(f'Interactive Lat:   Baseline {res_base[\"latency_ms\"]} ms | Adaptive {res_adapt[\"latency_ms\"]} ms')
print(f'Interactive Jitter:Baseline {res_base[\"jitter_ms\"]} ms | Adaptive {res_adapt[\"jitter_ms\"]} ms')
print(f'Queue Backlog:     Baseline {res_base[\"queue_depth_pkts\"]} pkts | Adaptive {res_adapt[\"queue_depth_pkts\"]} pkts')
print('Evidence recorded to experiments/evidence.db.')
print('=================================================================')
"
