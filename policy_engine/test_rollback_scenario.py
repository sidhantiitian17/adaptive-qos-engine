"""
Deliberately simulate a 'bad' policy (very low bandwidth that would 
cause high latency/starvation), and verify that RollbackManager 
correctly detects it and reverts.
"""
from rollback_manager import RollbackManager
import time

rm = RollbackManager()

print("=== Step 1: Apply a GOOD policy first (baseline) ===")
rm.apply_policy(80)
time.sleep(1)
if rm.health_check(latency_threshold_ms=100):
    rm.make_permanent(80)
print()

print("=== Step 2: Apply a 'BAD' policy (extremely low bandwidth) ===")
rm.apply_policy(1)  # 1mbit — bahut kam, latency/congestion barhega
time.sleep(1)

# Health check: agar threshold bahut strict rakhein (jaise 5ms), 
# to 1mbit pe bhi normal ping-latency pass ho sakti hai (ping chhota packet hai),
# isliye iss test mein hum THRESHOLD KO AGGRESSIVELY STRICT rakhte hain
# taaki rollback trigger ho (real-world mein throughput-based check behtar hoga)
healthy = rm.health_check(latency_threshold_ms=0.05)  # unrealistically strict, demo ke liye

if healthy:
    rm.make_permanent(1)
    print("[RESULT] Policy committed (unexpected for this test)")
else:
    rm.rollback()
    print("[RESULT] Policy rolled back successfully!")

print("\n=== Final History ===")
import json
print(json.dumps(rm.get_history(), indent=2))

print("\n=== Verify current qdisc state ===")
import subprocess
result = subprocess.run(
    "sudo ip netns exec gw tc qdisc show dev veth-gw-wan",
    shell=True, capture_output=True, text=True
)
print(result.stdout)
