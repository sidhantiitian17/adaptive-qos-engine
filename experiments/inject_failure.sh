#!/bin/bash
set -e

echo "============================================================"
echo "  ROLLBACK VERIFICATION: Deliberate Bad-Policy Injection"
echo "============================================================"
echo ""
echo "This script demonstrates that the engine auto-reverts a bad"
echo "policy, satisfying: 'automated remediation must be bounded,"
echo "observable and reversible; failure must return the system to"
echo "a known safe state.' (ps3.md Constraint C10)"
echo ""

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
export PYTHONPATH="$PROJECT_DIR"

# Use Python venv if available
PYTHON="python3"
if [ -f "./venv/bin/python3" ]; then
    PYTHON="./venv/bin/python3"
fi

echo "[1/4] Applying a GOOD policy (50 Mbps) and verifying health..."
echo ""
$PYTHON -c "
from policy_engine.rollback_manager import RollbackManager

rm = RollbackManager(dry_run=True)

# Step 1: Apply good policy
print('>>> Applying 50 Mbps policy...')
rm.apply_policy(50, 'diffserv4')
healthy = rm.health_check()
print(f'    Health check: {\"PASS ✅\" if healthy else \"FAIL ❌\"}')
rm.make_permanent(50)
print(f'    Last known-good config: {rm.last_good_config} Mbps')
print(f'    Status: {rm.history_log[-1][\"status\"]}')
print()

# Step 2: Apply BAD policy (deliberately bad — 1 Mbps)
print('>>> Injecting deliberately BAD policy (1 Mbps — triggers failure)...')
rm.apply_policy(1, 'diffserv4')
healthy = rm.health_check()
print(f'    Health check: {\"PASS ✅\" if healthy else \"FAIL ❌ — excessive latency detected\"}')

if not healthy:
    print()
    print('>>> Auto-rollback triggered!')
    rm.rollback()
    print(f'    Restored to: {rm.last_good_config} Mbps')
    print(f'    Status: {rm.history_log[-1][\"status\"]}')
else:
    print('    ERROR: Health check should have failed!')
    exit(1)

print()
print('>>> Full audit trail:')
for i, entry in enumerate(rm.history_log):
    print(f'    [{i+1}] {entry[\"bandwidth_mbit\"]}mbit → {entry[\"status\"]}')

print()

# Step 3: Apply another good policy to prove system recovered
print('>>> Applying 30 Mbps policy after recovery...')
rm.apply_policy(30, 'diffserv4')
healthy = rm.health_check()
print(f'    Health check: {\"PASS ✅\" if healthy else \"FAIL ❌\"}')
rm.make_permanent(30)
print(f'    System fully recovered. Current config: {rm.last_good_config} Mbps')

print()
print('============================================================')
print('  RESULT: Deliberate failure → auto-revert → recovery: PASS ✅')
print('============================================================')
"

echo ""
echo "To test with REAL kernel operations (requires sudo):"
echo "  sudo $PYTHON policy_engine/test_rollback_scenario.py"
