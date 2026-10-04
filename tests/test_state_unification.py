"""
Phase 1 State Unification Test Suite:
Validates that the Adaptive QoS Engine operates under ONE authoritative control plane
and ONE consistent backend state without divergence.
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from dashboard.unified_dashboard import app, controller

class TestStateUnification(unittest.TestCase):
    def setUp(self):
        # Reset state cleanly between test runs
        controller.scheduler.clear()
        with controller.flow_table.lock:
            controller.flow_table.flows.clear()
        with controller.rollback_mgr._lock:
            controller.rollback_mgr.history_log.clear()
        with controller.dscp_marker._lock:
            controller.dscp_marker.mock_rules.clear()
        controller.current_applied_bw = None
        controller._status = "NORMAL"
        self.client = TestClient(app)

    def test_01_intent_state_unification(self):
        """
        Test 1: Submitting an intent via POST /api/intent updates the authoritative
        controller.scheduler, and controller.run_one_cycle() immediately observes this intent.
        """
        resp = self.client.post("/api/intent", json={"text": "prioritize zoom call for 15 minutes"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["traffic_class"], "video_conference")

        # Verify authoritative controller state directly
        active_intent = controller.scheduler.get_active_intent()
        self.assertIsNotNone(active_intent)
        self.assertEqual(active_intent["traffic_class"], "video_conference")
        self.assertEqual(controller._status, "PRIORITY_ACTIVE")

        # Verify control cycle observes this intent
        cycle_res = controller.run_one_cycle(simulated_capacity_mbps=80.0)
        reasons_str = " ".join(cycle_res["decision"]["reasoning"]).lower()
        self.assertIn("video_conference", reasons_str)

        # Clear intent via DELETE /api/intent and verify authoritative controller reflects it
        del_resp = self.client.delete("/api/intent")
        self.assertEqual(del_resp.status_code, 200)
        self.assertIsNone(controller.scheduler.get_active_intent())
        self.assertEqual(controller._status, "NORMAL")

    def test_02_flow_state_unification(self):
        """
        Test 2: Flows recorded in controller.flow_table are immediately visible in GET /api/flows
        and consumed during controller.run_one_cycle().
        """
        flow_id = "10.0.1.50:45000->10.0.3.2:443/tcp"
        for _ in range(5):
            controller.flow_table.record_packet(flow_id, length=1200, ttl=64)
        controller.flow_table.update_classification(flow_id, "video_conference", 0.95)

        # Query flows via REST API
        resp = self.client.get("/api/flows")
        self.assertEqual(resp.status_code, 200)
        flows_data = resp.json()
        self.assertGreaterEqual(flows_data["total"], 1)
        found = [f for f in flows_data["flows"] if f["flow_id"] == flow_id]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["class"], "video_conference")

        # Verify control cycle observes the flow
        cycle_res = controller.run_one_cycle(simulated_capacity_mbps=100.0)
        self.assertIn("video_conference", cycle_res["decision"]["active_classes"])

    def test_03_override_state_unification(self):
        """
        Test 3: Flow override via POST /api/override updates controller.flow_table
        and immediately updates DSCP marking via controller.dscp_marker.
        """
        flow_id = "10.0.2.77:8080->10.0.3.2:80/tcp"
        controller.flow_table.record_packet(flow_id, length=1400, ttl=64)
        controller.flow_table.update_classification(flow_id, "bulk_download", 0.88)

        # Submit manual override via API
        resp = self.client.post("/api/override", json={
            "flow_id": flow_id,
            "corrected_class": "gaming",
            "reason": "Administrative correction for low latency"
        })
        self.assertEqual(resp.status_code, 200)

        # Verify authoritative flow_table was updated
        flow_entry = controller.flow_table.get(flow_id)
        self.assertIsNotNone(flow_entry)
        self.assertEqual(flow_entry["class"], "gaming")
        self.assertTrue(flow_entry.get("overridden"))

        # Verify authoritative DSCP marker tagged the host with EF (0x2E) for gaming
        rules = controller.dscp_marker.get_rules()
        gaming_rules = [r for r in rules if r.get("ip") == "10.0.2.77" and r.get("dscp") == "EF"]
        self.assertGreaterEqual(len(gaming_rules), 1)

    def test_04_rollback_state_unification(self):
        """
        Test 4: Rollback triggered during control or simulation updates controller.rollback_mgr
        and immediately propagates to GET /api/status.
        """
        # Trigger simulate inject failure
        resp = self.client.post("/api/simulate/inject-failure")
        self.assertEqual(resp.status_code, 200)
        res_data = resp.json()
        self.assertEqual(res_data["result"], "rollback_triggered")

        # Verify authoritative rollback manager recorded the rollback
        history = controller.rollback_mgr.get_history()
        self.assertGreaterEqual(len(history), 2)
        self.assertEqual(history[-1]["status"], "rolled_back")

        # Verify status endpoint reflects ROLLED_BACK
        status_resp = self.client.get("/api/status")
        self.assertEqual(status_resp.status_code, 200)
        self.assertEqual(status_resp.json()["system_status"], "ROLLED_BACK")
        self.assertEqual(status_resp.json()["active_policy_name"], "SAFE STATE RESTORED")

    def test_05_restart_and_consistency(self):
        """
        Test 5: The control plane maintains non-divergent state across cycles
        and empty initial state does not invent fake flows.
        """
        # With no flows added, active flows should be 0
        resp = self.client.get("/api/flows")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total"], 0)
        self.assertEqual(resp.json()["flows"], [])

        # Run first control cycle
        res1 = controller.run_one_cycle(simulated_capacity_mbps=100.0)
        self.assertEqual(res1["action_taken"], "applied_and_committed")

        # Second cycle with same capacity should take no change
        res2 = controller.run_one_cycle(simulated_capacity_mbps=100.0)
        self.assertEqual(res2["action_taken"], "no_change_needed")
        self.assertEqual(controller.current_applied_bw, res1["target_bw_mbit"])


if __name__ == "__main__":
    unittest.main()
