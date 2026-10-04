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
echo "   RUNNING SCENARIO C: 3 STREAMING TVS + 1 GAMING DEVICE         "
echo "================================================================="

$PYTHON -c "
from experiments.scenario_runner import ScenarioRunner
runner = ScenarioRunner()
print('\n[1/2] Running BASELINE (Unmanaged Multi-Flow Contention)...')
res_base = runner.run_scenario_c(mode='BASELINE', duration_sec=3.0)
print('  Baseline Metrics:', res_base)

print('\n[2/2] Running ADAPTIVE (CAKE DiffServ4 Fair Queuing + Gaming EF)...')
res_adapt = runner.run_scenario_c(mode='ADAPTIVE', duration_sec=3.0)
print('  Adaptive Metrics:', res_adapt)

print('\n' + '=' * 65)
print('SCENARIO C COMPARISON RESULT')
print('=' * 65)
print(f'TV Streams Fairness Index:  Baseline {res_base[\"fairness_index\"]} | Adaptive {res_adapt[\"fairness_index\"]}')
print(f'Gaming Interactive Latency: Baseline {res_base[\"gaming_latency_ms\"]} ms | Adaptive {res_adapt[\"gaming_latency_ms\"]} ms')
print(f'Gaming Jitter:              Baseline {res_base[\"gaming_jitter_ms\"]} ms | Adaptive {res_adapt[\"gaming_jitter_ms\"]} ms')
print('Evidence recorded to experiments/evidence.db.')
print('=================================================================')
"
