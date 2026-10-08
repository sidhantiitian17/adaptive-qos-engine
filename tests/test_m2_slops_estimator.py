"""
Unit & Integration Tests for Module M2: SLoPS Link Capacity Estimator
Tests SLoPS algorithm, TrendAnalyzer (PCT/PDT), state machine, hysteresis,
failure fallback, and M2 -> M3 contract.
"""
import unittest
import time
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from estimator.slops_estimator import (
    SlopsLinkEstimator,
    SlopsConfig,
    TrendAnalyzer,
    TrendDecision,
    EstimatorState,
    CapacityEstimate
)
from policy_engine.policy_rules import decide_policy


class TestM2TrendAnalyzer(unittest.TestCase):
    """Validates PCT and PDT calculation per Jain & Dovrolis methodology."""

    def test_uncongested_stream_flat_delays(self):
        # 50 samples with minor non-accumulating jitter
        delays = [0.005 + (0.0001 * (i % 3 - 1)) for i in range(50)]
        pct, pdt, decision, group_delays = TrendAnalyzer.analyze(
            delays_sec=delays, group_count=10, pct_threshold=0.55, pdt_threshold=0.40
        )
        self.assertLessEqual(pct, 0.55, f"PCT {pct} should not indicate congestion for flat delays")
        self.assertEqual(decision, TrendDecision.UNCONGESTED)

    def test_congested_stream_strictly_increasing_delays(self):
        # 50 samples with strictly increasing queuing delay
        delays = [0.002 + (0.001 * i) for i in range(50)]
        pct, pdt, decision, group_delays = TrendAnalyzer.analyze(
            delays_sec=delays, group_count=10, pct_threshold=0.55, pdt_threshold=0.40
        )
        self.assertGreater(pct, 0.55, f"PCT {pct} should detect congestion")
        self.assertGreater(pdt, 0.40, f"PDT {pdt} should detect congestion")
        self.assertEqual(decision, TrendDecision.CONGESTED)

    def test_outlier_filtering_with_median_grouping(self):
        # Mostly flat with isolated spikes (e.g. OS scheduling hiccups)
        delays = [0.005 for _ in range(50)]
        delays[12] = 0.050  # outlier spike
        delays[34] = 0.045  # outlier spike
        pct, pdt, decision, group_delays = TrendAnalyzer.analyze(
            delays_sec=delays, group_count=10
        )
        self.assertEqual(decision, TrendDecision.UNCONGESTED, "Median grouping must filter isolated spikes")


class TestM2EstimatorConfigAndHysteresis(unittest.TestCase):
    """Validates configurable parameters and hysteresis stability checks."""

    def test_configurable_parameters(self):
        cfg = SlopsConfig(
            probe_packet_size=1400,
            packets_per_probe=40,
            minimum_probe_rate_mbps=10.0,
            maximum_probe_rate_mbps=120.0,
            maximum_iterations=6,
            pct_threshold=0.60,
            pdt_threshold=0.45,
            hysteresis_percentage=20.0
        )
        est = SlopsLinkEstimator(target_ip="127.0.0.1", config=cfg)
        self.assertEqual(est.config.probe_packet_size, 1400)
        self.assertEqual(est.config.packets_per_probe, 40)
        self.assertEqual(est.config.pct_threshold, 0.60)
        self.assertEqual(est.config.hysteresis_percentage, 20.0)

    def test_hysteresis_detect_significant_change(self):
        cfg = SlopsConfig(hysteresis_percentage=15.0)
        est = SlopsLinkEstimator(target_ip="127.0.0.1", config=cfg)

        # Baseline estimate of 100 Mbps
        est.last_estimate = CapacityEstimate(
            estimated_bandwidth_min_mbps=95.0,
            estimated_bandwidth_max_mbps=105.0,
            estimated_bandwidth_mid_mbps=100.0,
            effective_capacity_mbps=100.0,
            confidence=0.95,
            probe_rate_start_mbps=50.0,
            probe_rate_final_mbps=100.0,
            iterations=5,
            samples=250,
            pct=0.4,
            pdt=0.1,
            converged=True,
            stable=True,
            timestamp=time.time(),
            method="SLOPS_ACTIVE",
            state="STABLE",
            status="measured"
        )

        # Small 5% change should NOT trigger significant change
        self.assertFalse(est.detect_significant_change(current_estimate=95.0))
        self.assertFalse(est.detect_significant_change(current_estimate=105.0))

        # Large 80% drop to 20 Mbps MUST trigger significant change
        self.assertTrue(est.detect_significant_change(current_estimate=20.0))


class TestM2ContractWithPolicyEngine(unittest.TestCase):
    """Validates contract M2 (CapacityEstimate) -> M3 (PolicyEngine decide_policy)."""

    def test_m2_to_m3_nominal_capacity(self):
        est = CapacityEstimate(
            estimated_bandwidth_min_mbps=95.0,
            estimated_bandwidth_max_mbps=105.0,
            estimated_bandwidth_mid_mbps=100.0,
            effective_capacity_mbps=100.0,
            confidence=0.92,
            probe_rate_start_mbps=50.0,
            probe_rate_final_mbps=100.0,
            iterations=6,
            samples=300,
            pct=0.4,
            pdt=0.1,
            converged=True,
            stable=True,
            timestamp=time.time(),
            method="SLOPS_ACTIVE",
            state="STABLE",
            status="measured"
        )
        flows = [{"flow_id": "f1", "class": "video_conference"}]
        decision = decide_policy(available_bandwidth_mbps=est.effective_capacity_mbps, active_flows=flows)

        self.assertEqual(decision["bandwidth_mbit"], 95, "95% shaping of 100 Mbps must equal 95 Mbps")
        self.assertEqual(decision["min_bulk_bandwidth_mbit"], 19, "20% minimum bulk floor")

    def test_m2_to_m3_degraded_capacity(self):
        est = CapacityEstimate(
            estimated_bandwidth_min_mbps=18.5,
            estimated_bandwidth_max_mbps=21.5,
            estimated_bandwidth_mid_mbps=20.0,
            effective_capacity_mbps=20.0,
            confidence=0.90,
            probe_rate_start_mbps=50.0,
            probe_rate_final_mbps=20.0,
            iterations=7,
            samples=350,
            pct=0.5,
            pdt=0.2,
            converged=True,
            stable=True,
            timestamp=time.time(),
            method="SLOPS_ACTIVE",
            state="STABLE",
            status="measured"
        )
        flows = [{"flow_id": "f1", "class": "video_conference"}]
        decision = decide_policy(available_bandwidth_mbps=est.effective_capacity_mbps, active_flows=flows)

        self.assertEqual(decision["bandwidth_mbit"], 19, "95% shaping of 20 Mbps must equal 19 Mbps")
        self.assertEqual(decision["min_bulk_bandwidth_mbit"], 4, "20% bulk floor of 19 Mbps must equal 4 Mbps")


class TestM2ExecutionAndFallback(unittest.TestCase):
    """Validates local SLoPS execution, schema output, and error fallback."""

    def test_loopback_slops_execution(self):
        cfg = SlopsConfig(
            packets_per_probe=20,
            maximum_iterations=3,
            minimum_probe_rate_mbps=10.0,
            maximum_probe_rate_mbps=60.0
        )
        est = SlopsLinkEstimator(target_ip="127.0.0.1", sender_namespace=None, receiver_namespace=None, config=cfg)
        try:
            res = est.estimate_capacity()
            self.assertIsInstance(res, CapacityEstimate)
            self.assertGreater(res.estimated_bandwidth_min_mbps, 0)
            self.assertGreaterEqual(res.estimated_bandwidth_max_mbps, res.estimated_bandwidth_min_mbps)
            self.assertGreater(res.samples, 0)
            self.assertEqual(res.method, "SLOPS_ACTIVE")
            self.assertIsNotNone(res.overhead)
            self.assertGreater(res.overhead["total_probe_packets"], 0)
        finally:
            est.stop_receiver()

    def test_safe_fallback_on_unreachable_target(self):
        # 192.0.2.1 is TEST-NET-1 (RFC 5737), blackholed
        cfg = SlopsConfig(timeout_sec=0.2, maximum_iterations=2, packets_per_probe=10)
        est = SlopsLinkEstimator(target_ip="192.0.2.1", config=cfg)
        est.last_known_good_capacity = 75.0
        res = est.estimate_capacity()

        # Must not crash, must return fallback with status degraded
        self.assertEqual(res.status, "degraded")
        self.assertEqual(res.effective_capacity_mbps, 75.0)
        self.assertFalse(res.converged)


if __name__ == "__main__":
    unittest.main()
