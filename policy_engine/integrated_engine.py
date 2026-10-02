"""
End-to-end integration: Estimator -> Classifier (simplified, mock for now) 
-> Policy Rules -> Rollback-protected Apply
"""
import sys
sys.path.append("../estimator")
sys.path.append("../classifier")

from link_estimator import LinkEstimator
from policy_rules import decide_policy
from rollback_manager import RollbackManager
import time

def run_one_cycle(target_ip="10.0.3.2"):
    print("=== CYCLE START ===\n")

    # Step 1: Estimate current link capacity
    est = LinkEstimator(target_ip)
    available_mbps = est.estimate(probe_duration=2, samples=2)
    print(f"[ESTIMATOR] Available bandwidth: {available_mbps} Mbps\n")

    # Step 2: Mock classifier output (real version would use trained XGBoost model
    # on live captured packets; for this integration test we use a fixed scenario)
    active_flows = [
        {"flow_id": "f1", "class": "video_conference", "confidence": 0.9},
        {"flow_id": "f2", "class": "bulk_download", "confidence": 0.85},
    ]
    print(f"[CLASSIFIER] Active flows: {active_flows}\n")

    # Step 3: Decide policy
    decision = decide_policy(available_mbps, active_flows)
    print(f"[POLICY ENGINE] Decision: {decision}\n")

    # Step 4: Apply with rollback protection
    rm = RollbackManager()
    rm.apply_policy(decision["bandwidth_mbit"], decision["diffserv_mode"])
    time.sleep(1)
    if rm.health_check():
        rm.make_permanent(decision["bandwidth_mbit"])
        print("[RESULT] Policy committed successfully.")
    else:
        rm.rollback()
        print("[RESULT] Policy rolled back.")

    print("\n=== CYCLE END ===")

if __name__ == "__main__":
    run_one_cycle()
