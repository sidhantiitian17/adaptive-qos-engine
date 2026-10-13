#!/usr/bin/env python3
import os, sys
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import subprocess
from network.tc_manager import TcManager
from network.netns_manager import NetnsManager
from policy_engine.rollback_manager import RollbackManager

NetnsManager().setup()
tc = TcManager(iface="veth-gw-wan", namespace="gw")

print("=" * 72)
print("ROLLBACK MANAGER ATOMIC RECOVERY & KERNEL PARITY VERIFICATION")
print("=" * 72)

# 1. Start with initial baseline qdisc state
tc.apply_cake(67)
print(f"[*] Step 0: Initial Ambient Datapath Rate:    67.0 Mbps")

# 2. Commit 95 Mbps known-good permanent checkpoint
rm = RollbackManager(tc_manager=tc)
rm.commit_known_good(bandwidth="95mbit", diffserv="diffserv4")
snap_commit = rm.last_known_good_snapshot
print(f"[*] Step 1: Known-Good Permanent Commit:     {snap_commit['bandwidth_mbit']} Mbps (diffserv4)")

# 3. Simulate tentatve bad policy injection (1 Mbps degraded state)
res_bad = rm.apply_tentative(bandwidth="1mbit", diffserv="diffserv4")
print(f"[*] Step 2: Tentative Bad Policy Applied:    1.0 Mbps (Result: {res_bad})")
state_tentative = tc.get_qdisc_state()
print(f"    -> Kernel Verified Tentative State:      {state_tentative.get('bandwidth_mbit')} Mbps")

# 4. Trigger atomic rollback
rev_ok = rm.revert()
print(f"\n[*] Step 3: Atomic Rollback Triggered:       Success={rev_ok}")
snap_revert = rm.history_log[-1]
qdisc_kernel = tc.get_qdisc_state()

print("=" * 72)
print("FINAL REPRODUCIBILITY & CONSISTENCY AUDIT:")
print("=" * 72)
print(f"[+] Committed Bandwidth:                    {snap_commit['bandwidth_mbit']} Mbps")
print(f"[+] Reverted Rollback Bandwidth:             {snap_revert['rollback_bandwidth']} Mbps")
print(f"[+] Kernel Verified Active Bandwidth:        {qdisc_kernel['bandwidth_mbit']} Mbps")
print("=" * 72)

assert snap_commit['bandwidth_mbit'] == 95, "Commit bandwidth mismatch"
assert snap_revert['rollback_bandwidth'] == 95, "Revert bandwidth mismatch"
assert qdisc_kernel['bandwidth_mbit'] == 95.0, "Kernel state bandwidth mismatch"

print("RESULT: 100% PARITY PROVEN — COMMIT (95M) == REVERT (95M) == KERNEL (95M)")
print("=" * 72)

subprocess.run(["./testbed/teardown.sh"], capture_output=True)
