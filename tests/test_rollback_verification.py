"""
Authoritative Test Suite for Policy Rollback Verification, Bulk Non-Starvation,
and Kernel State Validation (Phases 1, 3, 4, 5).
Includes:
  1. Unit tests with mocked _exec() verifying apply_cake(), rollback(), checkpoint().
  2. Unit tests verifying bulk non-starvation rate calculations (20% floor) and reasoning.
  3. Opt-in live kernel integration tests (gated by AQE_INTEGRATION_TEST=1) testing
     isolated netns creation, CAKE apply, verified rollback, and contention servicing.
"""
import os
import sys
import time
import subprocess
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from network.tc_manager import TcManager
from policy_engine.rollback_manager import RollbackManager
from policy_engine.policy_rules import decide_policy


class TestTcManagerAndRollbackUnit(unittest.TestCase):
    """Unit tests for TcManager and RollbackManager with mocked _exec / subroutines."""

    def test_apply_cake_returns_success_when_output_matches_target(self):
        """apply_cake() returns success when parsed state matches requested bandwidth & diffserv."""
        tc = TcManager(iface="veth-test", namespace="testns", dry_run=False)
        # Mock _exec to succeed
        tc._exec = MagicMock(return_value=(0, "", ""))

        mock_kernel_output = (
            "qdisc cake 8001: root refcnt 2 bandwidth 60Mbit diffserv4 "
            "triple-isolate nonat nowash no-ack-filter split-gso rtt 100ms\n"
            " Sent 1000 bytes 10 pkt (dropped 0, overlimits 0 requeues 0)\n"
            " backlog 0b 0p requeues 0\n"
        )
        tc.parse_qdisc_output = MagicMock(return_value={
            "status": "verified",
            "qdisc_type": "cake",
            "interface": "veth-test",
            "namespace": "testns",
            "bandwidth": "60Mbit",
            "bandwidth_mbit": 60.0,
            "diffserv_mode": "diffserv4",
            "handle": "8001:",
            "parent": "root"
        })
        tc.get_qdisc_state = MagicMock(return_value={
            "status": "verified",
            "qdisc_type": "cake",
            "interface": "veth-test",
            "namespace": "testns",
            "bandwidth": "60Mbit",
            "bandwidth_mbit": 60.0,
            "diffserv_mode": "diffserv4",
            "handle": "8001:",
            "parent": "root"
        })

        result = tc.apply_cake(bandwidth_mbit=60, diffserv="diffserv4")
        self.assertTrue(result["success"])
        self.assertIsNone(result["error"])
        self.assertEqual(result["verified_state"]["bandwidth_mbit"], 60.0)
        self.assertEqual(result["verified_state"]["diffserv_mode"], "diffserv4")

    def test_apply_cake_returns_failure_when_kernel_reports_different_bandwidth(self):
        """apply_cake() fails when kernel reports different bandwidth despite returncode 0."""
        tc = TcManager(iface="veth-test", namespace="testns", dry_run=False)
        tc._exec = MagicMock(return_value=(0, "", ""))
        tc.get_qdisc_state = MagicMock(return_value={
            "status": "verified",
            "qdisc_type": "cake",
            "interface": "veth-test",
            "namespace": "testns",
            "bandwidth": "20Mbit",
            "bandwidth_mbit": 20.0,
            "diffserv_mode": "diffserv4",
            "handle": "8001:",
            "parent": "root"
        })

        result = tc.apply_cake(bandwidth_mbit=75, diffserv="diffserv4")
        self.assertFalse(result["success"])
        self.assertIn("bandwidth mismatch", result["error"])

    def test_apply_cake_returns_failure_when_kernel_reports_different_diffserv(self):
        """apply_cake() fails when kernel reports different diffserv mode."""
        tc = TcManager(iface="veth-test", namespace="testns", dry_run=False)
        tc._exec = MagicMock(return_value=(0, "", ""))
        tc.get_qdisc_state = MagicMock(return_value={
            "status": "verified",
            "qdisc_type": "cake",
            "interface": "veth-test",
            "namespace": "testns",
            "bandwidth": "50Mbit",
            "bandwidth_mbit": 50.0,
            "diffserv_mode": "besteffort",
            "handle": "8001:",
            "parent": "root"
        })

        result = tc.apply_cake(bandwidth_mbit=50, diffserv="diffserv4")
        self.assertFalse(result["success"])
        self.assertIn("diffserv mismatch", result["error"])

    def test_rollback_restores_exact_snapshot_parameters_not_hardcoded_50mbps(self):
        """rollback() restores exact previous snapshot parameters (e.g. 85 Mbps diffserv3)."""
        mock_tc = MagicMock()
        mock_tc.get_qdisc_state.return_value = {
            "status": "verified",
            "qdisc_type": "cake",
            "bandwidth_mbit": 85.0,
            "diffserv_mode": "diffserv3"
        }
        mock_tc.apply_cake.return_value = {
            "success": True,
            "verified_state": {
                "status": "verified",
                "qdisc_type": "cake",
                "bandwidth_mbit": 85.0,
                "diffserv_mode": "diffserv3"
            }
        }

        rb = RollbackManager(dry_run=False, tc_manager=mock_tc)
        # Snapshot 85 Mbps diffserv3 as last known-good
        rb.make_permanent(85, "diffserv3")

        # Now simulate a failure triggering rollback
        rb_ok = rb.rollback()
        self.assertTrue(rb_ok)
        mock_tc.apply_cake.assert_called_with(85, diffserv="diffserv3")
        self.assertEqual(rb.history_log[-1]["rollback_bandwidth"], 85)
        self.assertEqual(rb.history_log[-1]["rollback_diffserv"], "diffserv3")

    def test_rollback_marks_failure_when_kernel_verification_fails_after_restoration(self):
        """rollback() records failure if verification fails after restoration attempt."""
        mock_tc = MagicMock()
        mock_tc.apply_cake.return_value = {
            "success": False,
            "error": "Kernel state verification failed: bandwidth mismatch",
            "verified_state": {
                "status": "verified",
                "qdisc_type": "cake",
                "bandwidth_mbit": 10.0,
                "diffserv_mode": "diffserv4"
            }
        }

        rb = RollbackManager(dry_run=False, tc_manager=mock_tc)
        rb.make_permanent(90, "diffserv4")
        rb_ok = rb.rollback()
        self.assertFalse(rb_ok)
        self.assertEqual(rb.history_log[-1]["status"], "rollback_failed")

    def test_checkpoint_produces_valid_structured_snapshot(self):
        """checkpoint() produces valid dictionary capturing all canonical qdisc fields."""
        mock_tc = MagicMock()
        mock_tc.get_qdisc_state.return_value = {
            "status": "verified",
            "qdisc_type": "cake",
            "interface": "veth0",
            "namespace": "gw",
            "bandwidth": "70Mbit",
            "bandwidth_mbit": 70.0,
            "diffserv_mode": "diffserv4",
            "handle": "8001:",
            "parent": "root",
            "sent_bytes": 1000,
            "sent_packets": 10,
            "dropped": 0
        }

        rb = RollbackManager(iface="veth0", namespace="gw", dry_run=False, tc_manager=mock_tc)
        snap = rb.checkpoint()
        self.assertIsNotNone(snap)
        self.assertEqual(snap["interface"], "veth0")
        self.assertEqual(snap["namespace"], "gw")
        self.assertEqual(snap["qdisc_type"], "cake")
        self.assertEqual(snap["bandwidth_mbit"], 70.0)
        self.assertEqual(snap["diffserv_mode"], "diffserv4")
        self.assertTrue(snap["kernel_verified"])


class TestPhase5BulkCalculation(unittest.TestCase):
    """Unit tests for Phase 5 bulk traffic non-starvation rate calculations."""

    def test_bulk_calculation_edge_cases(self):
        """Verify bulk calculation: 20% floor for various shaped link rates."""
        # 10 Mbps link -> 9.5 -> 10 Mbps shaped (banker's round), 20% floor = 2 Mbps min
        dec10 = decide_policy(available_bandwidth_mbps=10.0, active_flows=[])
        self.assertEqual(dec10["bandwidth_mbit"], 10)
        self.assertEqual(dec10["min_bulk_bandwidth_mbit"], 2)

        # 100 Mbps link -> 95 Mbps shaped, 20% floor = 19 Mbps min
        dec100 = decide_policy(available_bandwidth_mbps=100.0, active_flows=[])
        self.assertEqual(dec100["bandwidth_mbit"], 95)
        self.assertEqual(dec100["min_bulk_bandwidth_mbit"], 19)

        # 5 Mbps link -> 4.75 -> 5 Mbps shaped (link safety floor), 20% floor = max(2, 1) = 2 Mbps min
        dec5 = decide_policy(available_bandwidth_mbps=5.0, active_flows=[])
        self.assertEqual(dec5["bandwidth_mbit"], 5)
        self.assertEqual(dec5["min_bulk_bandwidth_mbit"], 2)

    def test_reasoning_string_describes_non_starvation_semantics(self):
        """Policy decision reasoning explicitly documents the bulk non-starvation planning objective."""
        dec = decide_policy(available_bandwidth_mbps=80.0, active_flows=[])
        reasoning_joined = " ".join(dec["reasoning"])
        self.assertIn("Bulk non-starvation objective (Option B)", reasoning_joined)
        self.assertIn("CAKE DRR quantum allocation", reasoning_joined)


class TestOptInKernelIntegration(unittest.TestCase):
    """
    Opt-in live kernel integration test running in an isolated test namespace.
    Only executed if AQE_INTEGRATION_TEST=1 and root/passwordless sudo is available.
    """

    TEST_NS = "aqe_test_ns"
    VETH_LOCAL = "veth-aqe-test"
    VETH_PEER = "veth-aqe-peer"

    @classmethod
    def setUpClass(cls):
        if os.environ.get("AQE_INTEGRATION_TEST") != "1":
            raise unittest.SkipTest("Skipping kernel integration test (AQE_INTEGRATION_TEST != 1)")

        # Verify sudo availability
        try:
            check = subprocess.run(["sudo", "-n", "true"], capture_output=True)
            if check.returncode != 0:
                raise unittest.SkipTest("Skipping kernel integration test (passwordless sudo unavailable)")
        except Exception:
            raise unittest.SkipTest("Skipping kernel integration test (sudo execution failed)")

        # Setup isolated namespace and veth pair
        cls._cleanup()
        try:
            subprocess.run(["sudo", "ip", "netns", "add", cls.TEST_NS], check=True, capture_output=True)
            subprocess.run([
                "sudo", "ip", "link", "add", cls.VETH_LOCAL, "type", "veth",
                "peer", "name", cls.VETH_PEER
            ], check=True, capture_output=True)
            subprocess.run(["sudo", "ip", "link", "set", cls.VETH_PEER, "netns", cls.TEST_NS], check=True, capture_output=True)
            subprocess.run(["sudo", "ip", "link", "set", cls.VETH_LOCAL, "up"], check=True, capture_output=True)
            subprocess.run(["sudo", "ip", "addr", "add", "10.200.55.1/24", "dev", cls.VETH_LOCAL], check=True, capture_output=True)
            subprocess.run(["sudo", "ip", "netns", "exec", cls.TEST_NS, "ip", "link", "set", cls.VETH_PEER, "up"], check=True, capture_output=True)
            subprocess.run(["sudo", "ip", "netns", "exec", cls.TEST_NS, "ip", "addr", "add", "10.200.55.2/24", "dev", cls.VETH_PEER], check=True, capture_output=True)
        except Exception as e:
            cls._cleanup()
            raise unittest.SkipTest(f"Failed to create isolated test namespace: {e}")

    @classmethod
    def tearDownClass(cls):
        cls._cleanup()

    @classmethod
    def _cleanup(cls):
        subprocess.run(["sudo", "ip", "link", "del", cls.VETH_LOCAL], capture_output=True)
        subprocess.run(["sudo", "ip", "netns", "del", cls.TEST_NS], capture_output=True)

    def test_live_cake_apply_and_verified_rollback(self):
        """Live CAKE qdisc application and verified atomic rollback in isolated test namespace."""
        tc = TcManager(iface=self.VETH_PEER, namespace=self.TEST_NS, dry_run=False)
        rb = RollbackManager(iface=self.VETH_PEER, namespace=self.TEST_NS, dry_run=False, tc_manager=tc)

        # 1. Apply initial 50 Mbps diffserv4 policy and make permanent
        init_ok = rb.apply_policy(50, "diffserv4")
        self.assertTrue(init_ok, "Initial CAKE policy apply must succeed in test netns")
        rb.make_permanent(50, "diffserv4")

        # Verify kernel state directly
        state = tc.get_qdisc_state()
        self.assertEqual(state["status"], "verified")
        self.assertEqual(state["qdisc_type"], "cake")
        self.assertAlmostEqual(state["bandwidth_mbit"], 50.0, delta=1.0)
        self.assertEqual(state["diffserv_mode"], "diffserv4")

        # 2. Apply a tentative 75 Mbps policy
        tentative_ok = rb.apply_policy(75, "diffserv4")
        self.assertTrue(tentative_ok, "Tentative 75 Mbps apply must succeed")

        state75 = tc.get_qdisc_state()
        self.assertAlmostEqual(state75["bandwidth_mbit"], 75.0, delta=1.0)

        # 3. Simulate failure and execute rollback
        rb_ok = rb.rollback()
        self.assertTrue(rb_ok, "Rollback to 50 Mbps must succeed")

        # Verify kernel state restored to exact 50 Mbps
        restored = tc.get_qdisc_state()
        self.assertEqual(restored["status"], "verified")
        self.assertAlmostEqual(restored["bandwidth_mbit"], 50.0, delta=1.0)
        self.assertEqual(restored["diffserv_mode"], "diffserv4")

    def test_live_cake_bulk_contention_and_servicing(self):
        """
        Verify sustained contention behavior under 20 Mbps CAKE diffserv4:
        Competing priority video traffic (AF41 / UDP 12M) vs Bulk traffic (CS1 / TCP).
        Measures actual bulk throughput and verifies CAKE DRR prevents starvation.
        """
        tc = TcManager(iface=self.VETH_PEER, namespace=self.TEST_NS, dry_run=False)
        res = tc.apply_cake(20, diffserv="diffserv4")
        self.assertTrue(res["success"], "Shaping to 20 Mbps CAKE must succeed")

        s_video = None
        s_bulk = None
        p_video = None
        p_bulk = None
        file_video = None
        file_bulk = None

        try:
            # Start two iperf3 servers on test namespace
            s_video = subprocess.Popen([
                "sudo", "ip", "netns", "exec", self.TEST_NS,
                "iperf3", "-s", "-B", "10.200.55.2", "-p", "5208", "-1"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            s_bulk = subprocess.Popen([
                "sudo", "ip", "netns", "exec", self.TEST_NS,
                "iperf3", "-s", "-B", "10.200.55.2", "-p", "5209", "-1"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.4)

            import tempfile
            import json
            with tempfile.NamedTemporaryFile("w+", delete=False) as f_v, \
                 tempfile.NamedTemporaryFile("w+", delete=False) as f_b:
                file_video = f_v.name
                file_bulk = f_b.name

            # Launch Video: UDP offering 12 Mbps (DSCP AF41 / 34)
            with open(file_video, "w") as f_out_v, open(file_bulk, "w") as f_out_b:
                p_video = subprocess.Popen([
                    "iperf3", "-c", "10.200.55.2", "-p", "5208", "-u", "-b", "12M",
                    "-t", "3", "-R", "--dscp", "34", "-J"
                ], stdout=f_out_v, stderr=subprocess.DEVNULL)

                # Launch Bulk: TCP stream (DSCP CS1 / 8)
                p_bulk = subprocess.Popen([
                    "iperf3", "-c", "10.200.55.2", "-p", "5209",
                    "-t", "3", "-R", "--dscp", "8", "-J"
                ], stdout=f_out_b, stderr=subprocess.DEVNULL)

                p_video.wait(timeout=10)
                p_bulk.wait(timeout=10)

            with open(file_video, "r") as f:
                data_video = json.loads(f.read())
            with open(file_bulk, "r") as f:
                data_bulk = json.loads(f.read())

            video_bps = data_video["end"]["sum"]["bits_per_second"]
            bulk_bps = data_bulk["end"]["sum_received"]["bits_per_second"]
            video_mbps = video_bps / 1_000_000.0
            bulk_mbps = bulk_bps / 1_000_000.0
            total_mbps = video_mbps + bulk_mbps

            # Verify acceptance criteria:
            # 1. Bulk throughput is strictly non-zero (non-starved via CAKE DRR quantum servicing)
            self.assertGreater(bulk_mbps, 1.0, f"Bulk flow must not starve under contention (got {bulk_mbps:.2f} Mbps)")
            # 2. Priority video traffic achieves its offered load
            self.assertGreater(video_mbps, 8.0, f"Priority video flow must receive preferential service (got {video_mbps:.2f} Mbps)")
            # 3. Total throughput is shaped by the 20 Mbps CAKE bottleneck
            self.assertLessEqual(total_mbps, 22.0, f"Total throughput must be bounded by CAKE shaping (got {total_mbps:.2f} Mbps)")
        finally:
            # Terminate and wait for only the specific processes started by this test
            for proc in [p_video, p_bulk, s_video, s_bulk]:
                if proc is not None and proc.poll() is None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=1.0)
                    except Exception:
                        try:
                            proc.kill()
                            proc.wait(timeout=1.0)
                        except Exception:
                            pass
            for path in [file_video, file_bulk]:
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                    except Exception:
                        pass


if __name__ == "__main__":
    unittest.main()
