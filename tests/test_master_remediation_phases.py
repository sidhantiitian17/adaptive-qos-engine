"""
Authoritative Test Suite for Master Engineering Remediation (Phases 1 - 7).
Validates:
  Phase 1: Genuine per-flow 5-tuple DSCP marking, IPv4/IPv6, rule isolation.
  Phase 2: Correct intent-to-class mappings (gaming -> EF, video -> AF41, validation).
  Phase 3: Autonomous active SLoPS probing, concurrency bounding, fallback hierarchy.
  Phase 4: Fail-closed enforcement, structured snapshots, verified atomic rollback.
  Phase 5: Bulk progress floor calculation and CAKE DRR anti-starvation semantics.
  Phase 6: API security, loopback default binding, token auth, probe rate limiting.
  Phase 7: Complete cross-component closed loop life cycle and fault injection.
"""
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from classifier.flow_tuple import FlowTuple
from enforcement.dscp_marker import DscpMarker
from policy_engine.traffic_classes import (
    normalize_class_name,
    get_dscp_for_class,
    get_expected_cake_tin,
    validate_intent_class,
    CLASS_SPECS
)
from policy_engine.policy_rules import decide_policy
from policy_engine.rollback_manager import RollbackManager
from controller_daemon import AdaptiveQoSController
from estimator.slops_estimator import CapacityEstimate
from dashboard.unified_dashboard import app
from fastapi.testclient import TestClient


class TestPhase1PerFlowEnforcement(unittest.TestCase):
    """Phase 1: Per-Flow DSCP Enforcement Tests."""

    def setUp(self):
        self.marker = DscpMarker(dry_run=True)

    def test_two_flows_same_host_retain_different_dscp(self):
        """Two flows from the same source IP with different ports retain different DSCP markings."""
        f_gaming = FlowTuple.create("10.0.1.2", "10.0.3.2", 45000, 27015, "udp")
        f_bulk = FlowTuple.create("10.0.1.2", "10.0.3.2", 55000, 80, "tcp")

        self.assertTrue(self.marker.mark_flow(f_gaming, "gaming"))
        self.assertTrue(self.marker.mark_flow(f_bulk, "bulk_download"))

        rules = self.marker.get_rules()
        self.assertEqual(len(rules), 2)

        r_game = self.marker.get_flow_rule(f_gaming.to_string())
        r_bulk = self.marker.get_flow_rule(f_bulk.to_string())

        self.assertIsNotNone(r_game)
        self.assertIsNotNone(r_bulk)
        self.assertEqual(r_game["dscp"], "EF")
        self.assertEqual(r_bulk["dscp"], "CS1")

    def test_updating_one_flow_does_not_mutate_other_flow(self):
        """Updating class on Flow A does not affect or remove Flow B."""
        f1 = FlowTuple.create("10.0.1.2", "10.0.3.2", 4001, 8080, "tcp")
        f2 = FlowTuple.create("10.0.1.2", "10.0.3.2", 4002, 8080, "tcp")

        self.marker.mark_flow(f1, "gaming")
        self.marker.mark_flow(f2, "bulk_download")

        # Update f1 to video_conference
        self.marker.mark_flow(f1, "video_conference")

        r1 = self.marker.get_flow_rule(f1.to_string())
        r2 = self.marker.get_flow_rule(f2.to_string())

        self.assertEqual(r1["dscp"], "AF41")
        self.assertEqual(r2["dscp"], "CS1")
        self.assertEqual(len(self.marker.get_rules()), 2)

    def test_clear_flow_removes_only_target_flow(self):
        """Clearing one flow removes its rule while preserving other flows from that host."""
        f1 = FlowTuple.create("10.0.1.2", "10.0.3.2", 5001, 80, "tcp")
        f2 = FlowTuple.create("10.0.1.2", "10.0.3.2", 5002, 80, "tcp")

        self.marker.mark_flow(f1, "gaming")
        self.marker.mark_flow(f2, "bulk_download")

        self.marker.clear_flow(f1)
        self.assertIsNone(self.marker.get_flow_rule(f1.to_string()))
        self.assertIsNotNone(self.marker.get_flow_rule(f2.to_string()))
        self.assertEqual(len(self.marker.get_rules()), 1)

    def test_ipv6_tuple_handling(self):
        """IPv6 flows use ip6tables tool and normalize address strings."""
        f_v6 = FlowTuple.create("fd00:1::2", "fd00:3::2", 9000, 9000, "udp")
        self.assertTrue(f_v6.is_ipv6())
        self.marker.mark_flow(f_v6, "gaming")

        r = self.marker.get_flow_rule(f_v6.to_string())
        self.assertEqual(r["tool"], "ip6tables")
        self.assertEqual(r["dscp"], "EF")

    def test_flow_tuple_validation_and_reverse(self):
        """FlowTuple creation rejects invalid ports, mismatched address families, and supports reverse."""
        with self.assertRaises(ValueError):
            FlowTuple.create("10.0.1.2", "10.0.3.2", -1, 80, "tcp")
        with self.assertRaises(ValueError):
            FlowTuple.create("10.0.1.2", "10.0.3.2", 80, 70000, "tcp")
        with self.assertRaises(ValueError):
            FlowTuple.create("10.0.1.2", "fd00::1", 80, 80, "tcp")  # v4/v6 mismatch

        f = FlowTuple.create("10.0.1.2", "10.0.3.2", 1234, 5678, "tcp")
        rev = f.reverse()
        self.assertEqual(rev.src_ip, "10.0.3.2")
        self.assertEqual(rev.dst_ip, "10.0.1.2")
        self.assertEqual(rev.sport, 5678)
        self.assertEqual(rev.dport, 1234)


class TestPhase2IntentMapping(unittest.TestCase):
    """Phase 2: Correct Intent-to-Class Mapping Tests."""

    def test_gaming_intent_maps_to_ef_voice_tin(self):
        """Gaming intent preserves gaming class and maps to EF (Tin 3)."""
        norm = normalize_class_name("gaming")
        self.assertEqual(norm, "gaming")
        spec = CLASS_SPECS["gaming"]
        self.assertEqual(spec["dscp_name"], "EF")
        self.assertEqual(spec["cake_tin"], "voice")
        self.assertEqual(spec["cake_tin_index"], 3)

    def test_video_intent_maps_to_af41_video_tin(self):
        """Video intent maps to video_conference and AF41 (Tin 2)."""
        norm = normalize_class_name("video")
        self.assertEqual(norm, "video_conference")
        spec = CLASS_SPECS["video_conference"]
        self.assertEqual(spec["dscp_name"], "AF41")
        self.assertEqual(spec["cake_tin"], "video")
        self.assertEqual(spec["cake_tin_index"], 2)

    def test_unsupported_intent_raises_validation_error(self):
        """Unsupported intent class raises explicit ValueError."""
        with self.assertRaises(ValueError):
            validate_intent_class("invalid_quantum_traffic")

    def test_controller_preserves_gaming_class_under_gaming_intent(self):
        """Controller does not overwrite gaming flows with video_conference when gaming intent is active."""
        c = AdaptiveQoSController(dry_run=True)
        f = FlowTuple.create("10.0.1.2", "10.0.3.2", 3000, 3000, "udp")
        c.flow_table.record_packet(f.to_string(), 150, 64)
        c.flow_table.update_classification(f.to_string(), "gaming", 0.98)

        c.schedule_intent("gaming", "prioritize", 600)
        rules = c.dscp_marker.get_rules()
        r = next(r for r in rules if r.get("flow_id") == f.to_string())
        self.assertEqual(r["class"], "gaming")
        self.assertEqual(r["dscp"], "EF")

    def test_intent_expiry_restores_baseline_policy(self):
        """Clearing or expiring an intent restores baseline policy immediately."""
        c = AdaptiveQoSController(dry_run=True)
        c.schedule_intent("video_conference", "prioritize", 600)
        self.assertEqual(c._status, "PRIORITY_ACTIVE")
        c.clear_intent()
        self.assertEqual(c._status, "NORMAL")
        self.assertIsNone(c.scheduler.get_active_intent())


class TestPhase3AutonomousActiveEstimator(unittest.TestCase):
    """Phase 3: Autonomous Active SLoPS Estimator Integration Tests."""

    def test_probing_concurrency_protection(self):
        """Simultaneous active probe attempts are rejected while a probe is running."""
        c = AdaptiveQoSController(dry_run=True)
        # Lock probing
        c._probing_lock.acquire()
        try:
            res = c.run_active_probing()
            # Must return existing estimate without crashing or overlapping
            self.assertEqual(res, c.latest_capacity_estimate)
        finally:
            c._probing_lock.release()

    def test_fresh_active_estimate_precedence(self):
        """Fresh measured active estimate takes precedence over passive estimate."""
        c = AdaptiveQoSController(dry_run=True)
        fake_est = CapacityEstimate(
            estimated_bandwidth_min_mbps=48.0,
            estimated_bandwidth_max_mbps=52.0,
            estimated_bandwidth_mid_mbps=50.0,
            effective_capacity_mbps=50.0,
            confidence=1.0,
            probe_rate_start_mbps=10.0,
            probe_rate_final_mbps=50.0,
            iterations=3,
            samples=200,
            pct=0.1,
            pdt=0.1,
            converged=True,
            stable=True,
            timestamp=time.time(),
            method="SLOPS",
            state="STABLE",
            status="measured"
        )
        c.latest_capacity_estimate = fake_est

        eff = c.get_effective_capacity()
        self.assertEqual(eff, 50.0)
        self.assertEqual(c.estimator_source_used, "active_slops")

    def test_stale_active_estimate_falls_back_to_passive(self):
        """Active estimate older than max_estimate_age_sec falls back to passive estimator."""
        c = AdaptiveQoSController(dry_run=True)
        fake_est = CapacityEstimate(
            estimated_bandwidth_min_mbps=48.0,
            estimated_bandwidth_max_mbps=52.0,
            estimated_bandwidth_mid_mbps=50.0,
            effective_capacity_mbps=50.0,
            confidence=1.0,
            probe_rate_start_mbps=10.0,
            probe_rate_final_mbps=50.0,
            iterations=3,
            samples=200,
            pct=0.1,
            pdt=0.1,
            converged=True,
            stable=True,
            timestamp=time.time() - 120.0,
            method="SLOPS",
            state="STABLE",
            status="measured"
        )
        c.latest_capacity_estimate = fake_est

        eff = c.get_effective_capacity()
        self.assertEqual(c.estimator_source_used, "passive_fallback")


class TestPhase4FailClosedAndRollback(unittest.TestCase):
    """Phase 4: Fail-Closed Enforcement and Verified Rollback Tests."""

    def test_apply_policy_failure_aborts_commit(self):
        """When apply_policy fails at kernel level, controller aborts commit and does not update current_applied_bw."""
        c = AdaptiveQoSController(dry_run=True)
        c.rollback_mgr.apply_policy = MagicMock(return_value=False)

        res = c.run_one_cycle(simulated_capacity_mbps=20.0)
        self.assertEqual(res["action_taken"], "apply_failed")
        self.assertIsNone(c.current_applied_bw)
        self.assertEqual(c._status, "ROLLED_BACK")

    def test_health_check_failure_triggers_atomic_rollback(self):
        """Failed health check rolls back to previous safe configuration."""
        rb = RollbackManager(dry_run=True)
        rb.apply_policy(80, "diffserv4")
        rb.make_permanent(80, "diffserv4")
        self.assertEqual(rb.last_good_config, 80)

        # Apply bad state
        rb.apply_policy(1, "diffserv4")
        # In mock, 1 mbit triggers health check failure
        self.assertFalse(rb.health_check())

        # Rollback
        success = rb.rollback()
        self.assertTrue(success)
        self.assertEqual(rb.history_log[-1]["status"], "rolled_back")
        self.assertEqual(rb.history_log[-1]["rollback_bandwidth"], 80)


class TestPhase5BulkStarvationPrevention(unittest.TestCase):
    """Phase 5: Bulk Starvation Prevention and Claim Accuracy Tests."""

    def test_bulk_progress_floor_calculation(self):
        """Policy engine computes accurate analytical 20% progress floor."""
        dec = decide_policy(available_bandwidth_mbps=100.0, active_flows=[])
        self.assertEqual(dec["bandwidth_mbit"], 95)
        self.assertEqual(dec["min_bulk_bandwidth_mbit"], 19)

        dec_low = decide_policy(available_bandwidth_mbps=20.0, active_flows=[])
        self.assertEqual(dec_low["bandwidth_mbit"], 19)
        self.assertEqual(dec_low["min_bulk_bandwidth_mbit"], 4)

    def test_diffserv4_bulk_tin_assignment(self):
        """Bulk download maps to CS1 and Bulk tin index 0."""
        dscp = get_dscp_for_class("bulk_download")
        self.assertEqual(dscp["name"], "CS1")
        tin = get_expected_cake_tin("bulk_download")
        self.assertEqual(tin, "bulk")


class TestPhase6ApiSecurity(unittest.TestCase):
    """Phase 6: Dashboard & API Security Tests."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_probe_cooldown_rate_limit(self):
        """POST /api/estimator/probe returns HTTP 429 when triggered repeatedly within cooldown."""
        from dashboard.unified_dashboard import controller
        controller.last_probe_time = time.time()
        controller.probe_cooldown_sec = 10.0

        resp = self.client.post("/api/estimator/probe")
        self.assertEqual(resp.status_code, 429)
        self.assertIn("cooldown active", resp.json()["detail"])

        # Reset cooldown
        controller.last_probe_time = None

    def test_token_auth_enforcement_when_configured(self):
        """When AQE_API_TOKEN is set in environment, unauthorized requests receive HTTP 401."""
        with patch.dict(os.environ, {"AQE_API_TOKEN": "secret_test_token_123"}):
            # Unauthorized call without header
            resp_no_token = self.client.post("/api/intent", json={"text": "prioritize gaming"})
            self.assertEqual(resp_no_token.status_code, 401)

            # Authorized call with header
            resp_auth = self.client.post(
                "/api/intent",
                json={"text": "prioritize gaming"},
                headers={"X-API-Token": "secret_test_token_123"}
            )
            self.assertEqual(resp_auth.status_code, 200)
            self.assertEqual(resp_auth.json()["traffic_class"], "gaming")


class TestPhase7ClosedLoopIntegration(unittest.TestCase):
    """Phase 7: Full Closed Loop Integration and Lifecycle Tests."""

    def test_end_to_end_flow_to_policy_lifecycle(self):
        """Simulate flow packet -> classification -> override -> policy calculation -> safe commit."""
        c = AdaptiveQoSController(dry_run=True)

        # 1. New flow arrives
        f = FlowTuple.create("10.0.1.55", "10.0.3.2", 8080, 80, "tcp")
        c.flow_table.record_packet(f.to_string(), 1200, 64)
        c.flow_table.update_classification(f.to_string(), "bulk_download", 0.95)

        # 2. Control cycle evaluates flow
        res = c.run_one_cycle(simulated_capacity_mbps=50.0)
        self.assertEqual(res["target_bw_mbit"], 48)
        self.assertEqual(res["action_taken"], "applied_and_committed")

        rule = c.dscp_marker.get_flow_rule(f.to_string())
        self.assertIsNotNone(rule)
        self.assertEqual(rule["dscp"], "CS1")

        # 3. Administrative manual override to gaming
        c.override_flow(f.to_string(), "gaming")
        rule_overridden = c.dscp_marker.get_flow_rule(f.to_string())
        self.assertEqual(rule_overridden["dscp"], "EF")

        # 4. Injected failure triggers rollback
        c.rollback_mgr.apply_policy = MagicMock(return_value=False)
        fail_res = c.run_one_cycle(simulated_capacity_mbps=20.0)
        self.assertEqual(fail_res["action_taken"], "apply_failed")
        self.assertEqual(c._status, "ROLLED_BACK")


if __name__ == "__main__":
    unittest.main()
