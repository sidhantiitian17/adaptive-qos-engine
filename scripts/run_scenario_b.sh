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
echo "   RUNNING SCENARIO B: WAN COLLAPSE (100 Mbps -> 20 Mbps)        "
echo "================================================================="

$PYTHON -c "
from experiments.scenario_runner import ScenarioRunner
runner = ScenarioRunner()
print('\n[1/2] Executing Baseline WAN Collapse (Static Unmanaged FIFO)...')
res_base = runner.run_scenario_b(mode='BASELINE', duration_sec=2.0)
print('  Baseline Exp ID:         ', res_base['experiment_id'])
print(f'  Target Shaping:          {res_base[\"target_shaping_mbps\"]} Mbps (Unadapted)')
print(f'  Adaptation Time:         {res_base[\"adaptation_time_sec\"]} s (Timed out / no adaptation)')

print('\n[2/2] Executing Adaptive WAN Collapse (AQE CAKE Adaptation)...')
res_adapt = runner.run_scenario_b(mode='ADAPTIVE', duration_sec=2.0)
print('  Adaptive Exp ID:         ', res_adapt['experiment_id'])
print(f'  Initial WAN Capacity:    {res_adapt[\"initial_capacity_mbps\"]} Mbps')
print(f'  Collapsed WAN Capacity:  {res_adapt[\"collapsed_capacity_mbps\"]} Mbps')
print(f'  Adapted CAKE Shaping:    {res_adapt[\"target_shaping_mbps\"]} Mbps (0.95x link rate)')
print(f'  Detection & Adapt Time:  {res_adapt[\"adaptation_time_sec\"]} s')
print(f'  Recovery Time to 100M:   {res_adapt[\"recovery_time_sec\"]} s')
print('\nEvidence recorded to experiments/evidence.db.')
print('=================================================================')
"
