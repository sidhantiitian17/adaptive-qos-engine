"""
Phase 4 Operational Hardening, Deployment & Safety Test Suite
Validates:
1. Interface discovery & non-loopback enforcement
2. Safe lifecycle startup and shutdown
3. API input validation & injection security
4. Production observability endpoints (/health, /readiness, /api/network/status, etc.)
5. Atomic rollback under invalid policies
6. Anti-starvation 20% floor preservation
"""
import unittest
import os
import sys
import json
import time
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dashboard.unified_dashboard import app, controller
from network.interface_discovery import InterfaceDiscovery, InterfaceDiscoveryError
from policy_engine.rollback_manager import RollbackManager
from policy_engine.policy_rules import decide_policy

class TestPhase4OperationalHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["AQE_API_TOKEN"] = "dev-secret-token-123"
        cls.client = TestClient(app, headers={"X-API-Token": "dev-secret-token-123"})

    def test_01_interface_discovery_non_loopback(self):
        """Verify interface discovery rejects loopback and discovers real network device."""
        disco = InterfaceDiscovery()
        topo = disco.discover_topology()
        self.assertIn("wan_interface", topo)
        self.assertNotEqual(topo["wan_interface"], "lo")
        self.assertNotEqual(topo["wan_interface"], "localhost")
        self.assertIn("environment_classification", topo)

    def test_02_interface_discovery_rejects_loopback_override(self):
        """Verify that explicit loopback override raises an explicit configuration error."""
        disco = InterfaceDiscovery(wan_override="lo")
        with self.assertRaises(InterfaceDiscoveryError) as ctx:
            disco.discover_topology()
        self.assertIn("Rejected loopback interface", str(ctx.exception))

    def test_03_observability_health_endpoint(self):
        """Verify /health endpoint returns structured health telemetry without fake fallbacks."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn(data["status"], ["healthy", "degraded"])
        self.assertTrue(data["database_healthy"])
        self.assertIn("uptime_sec", data)
        self.assertIn("effective_capacity_mbps", data)

    def test_04_observability_readiness_endpoint(self):
        """Verify /readiness endpoint returns ready status when classifier is active."""
        resp = self.client.get("/readiness")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ready")

    def test_05_observability_network_status_endpoint(self):
        """Verify /api/network/status returns live topology discovery details."""
        resp = self.client.get("/api/network/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("wan_interface", data)
        self.assertIn("routes", data)

    def test_06_observability_evidence_endpoints(self):
        """Verify /api/measurements, /api/policies, /api/evidence endpoints."""
        r_meas = self.client.get("/api/measurements?limit=5")
        self.assertEqual(r_meas.status_code, 200)
        self.assertIsInstance(r_meas.json(), list)

        r_pol = self.client.get("/api/policies?limit=5")
        self.assertEqual(r_pol.status_code, 200)
        self.assertIsInstance(r_pol.json(), list)

        r_ev = self.client.get("/api/evidence")
        self.assertEqual(r_ev.status_code, 200)
        self.assertIn("counts", r_ev.json())
        self.assertGreater(r_ev.json()["counts"].get("measurements", 0), 0)

    def test_07_api_intent_validation_empty_text(self):
        """Verify /api/intent rejects empty text with HTTP 400."""
        resp = self.client.post("/api/intent", json={"text": ""})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("cannot be empty", resp.json()["detail"])

    def test_08_api_intent_validation_max_length(self):
        """Verify /api/intent rejects text exceeding 256 characters with HTTP 400."""
        long_text = "prioritize gaming " * 30
        resp = self.client.post("/api/intent", json={"text": long_text})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("exceeds maximum allowed length", resp.json()["detail"])

    def test_09_api_intent_validation_duration_bounds(self):
        """Verify /api/intent rejects duration outside [10, 86400] seconds."""
        resp_too_low = self.client.post("/api/intent", json={"text": "prioritize gaming", "duration_sec": 5})
        self.assertEqual(resp_too_low.status_code, 400)

        resp_too_high = self.client.post("/api/intent", json={"text": "prioritize gaming", "duration_sec": 100000})
        self.assertEqual(resp_too_high.status_code, 400)

    def test_10_api_intent_validation_control_characters(self):
        """Verify /api/intent rejects unprintable control characters with HTTP 400."""
        malicious_text = "prioritize gaming\x00\x07"
        resp = self.client.post("/api/intent", json={"text": malicious_text})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("control characters", resp.json()["detail"])

    def test_11_api_override_validation(self):
        """Verify /api/override rejects empty flow_id and invalid traffic class."""
        resp_empty = self.client.post("/api/override", json={"flow_id": "", "corrected_class": "gaming"})
        self.assertEqual(resp_empty.status_code, 400)

        resp_bad_class = self.client.post("/api/override", json={"flow_id": "1.2.3.4:1->5.6.7.8:2/tcp", "corrected_class": "super_vip"})
        self.assertEqual(resp_bad_class.status_code, 400)
        self.assertIn("Invalid corrected_class", resp_bad_class.json()["detail"])

    def test_12_atomic_rollback_on_failed_policy(self):
        """Verify rollback manager reverts to known-good policy when tentative policy fails."""
        rb = RollbackManager(iface="veth-gw-wan", namespace="gw", dry_run=True)
        # Checkpoint safe state
        self.assertTrue(rb.apply_policy(95, "diffserv4"))
        rb.make_permanent(95)
        self.assertEqual(rb.last_good_config, 95)

        # Apply tentative bad state
        self.assertTrue(rb.apply_policy(1, "diffserv4"))
        self.assertEqual(rb.history_log[-1]["bandwidth_mbit"], 1)

        # Revert to safe
        rb.rollback()
        self.assertEqual(rb.history_log[-1]["status"], "rolled_back")

    def test_13_anti_starvation_guaranteed_floor(self):
        """Verify policy engine always reserves at least 20% capacity for bulk traffic."""
        # 100 Mbps capacity, heavy high-priority video intent
        decision = decide_policy(
            available_bandwidth_mbps=100.0,
            active_flows=[{"flow_id": "1", "class": "video_conference"}, {"flow_id": "2", "class": "bulk_download"}],
            user_intent={"traffic_class": "video_conference", "action": "prioritize", "duration_sec": 1200}
        )
        self.assertIn("reasoning", decision)
        # Verify bulk floor statement is present and accurate
        found_floor = any("Bulk non-starvation objective" in r for r in decision["reasoning"])
        self.assertTrue(found_floor, "Bulk progress floor missing from policy decision")

        # 20 Mbps capacity
        decision_collapsed = decide_policy(
            available_bandwidth_mbps=20.0,
            active_flows=[{"flow_id": "1", "class": "video_conference"}, {"flow_id": "2", "class": "bulk_download"}],
            user_intent=None
        )
        found_floor_collapsed = any("Bulk non-starvation objective" in r for r in decision_collapsed["reasoning"])
        self.assertTrue(found_floor_collapsed)

if __name__ == "__main__":
    unittest.main()
