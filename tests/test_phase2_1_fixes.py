"""
Phase 2.1 Acceptance Fix Verification Suite:
Covers all four critical blockers identified during independent Phase 2 audit:
  - BLOCKER 1: Zero synthetic scenario metrics (21.2, 84.5, 0.12, 42.0, backlog fallback purged)
  - BLOCKER 2: Real two-way UDP echo RTT and consecutive MAD jitter protocol
  - BLOCKER 3: LiveFlowSniffer interface detection, classification, error capturing, FlowTable integration
  - BLOCKER 4: ExecutionBackend hierarchy, rootless user namespace support, CAKE & NetEm verification
  - Evidence DB: Auto-population of experiment_runs and policy_changes tables
"""
import os
import sys
import time
import shutil
import tempfile
import unittest
import sqlite3

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from experiments.rtt_probe import UdpEchoServer, UdpRttProber
from experiments.evidence_db import EvidenceDB
from network.execution_backend import get_execution_backend, ExecutionBackend, UserNamespaceExecutionBackend
from network.tc_manager import TcManager
from network.netns_manager import NetnsManager
from classifier.runtime_classifier import FlowClassifier, LiveFlowSniffer
from classifier.flow_table import FlowTable
from experiments.scenario_runner import ScenarioRunner


class TestPhase21Fixes(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_udp_echo_rtt_and_jitter(self):
        """Verify genuine two-way UDP echo round-trip and RFC 3550 consecutive MAD jitter."""
        port = 5291
        server = UdpEchoServer(host="127.0.0.1", port=port)
        server.start()
        time.sleep(0.1)

        prober = UdpRttProber()
        train_res = prober.run_probe_train(
            target_host="127.0.0.1",
            target_port=port,
            count=8,
            interval_sec=0.03,
            timeout_sec=0.3
        )
        server.stop()

        self.assertEqual(train_res["status"], "success")
        self.assertEqual(train_res["samples_received"], 8)
        self.assertEqual(train_res["loss_pct"], 0.0)
        self.assertIsNotNone(train_res["avg_rtt_ms"])
        self.assertGreater(train_res["avg_rtt_ms"], 0.0)
        self.assertIsNotNone(train_res["jitter_ms"])
        self.assertEqual(train_res["jitter_method"], "consecutive_rtt_mad")
        self.assertEqual(len(train_res["raw_rtts"]), 8)

    def test_02_udp_echo_timeout_no_synthetic_fallback(self):
        """Verify that when echo server does not respond, prober returns None/timeout and never fabricates latency."""
        prober = UdpRttProber()
        dead_port = 5293
        rtt = prober.probe_once("127.0.0.1", dead_port, timeout_sec=0.1)
        self.assertIsNone(rtt)

        train_res = prober.run_probe_train("127.0.0.1", dead_port, count=3, interval_sec=0.01, timeout_sec=0.1)
        self.assertEqual(train_res["status"], "timeout")
        self.assertEqual(train_res["samples_received"], 0)
        self.assertEqual(train_res["loss_pct"], 100.0)
        self.assertIsNone(train_res["avg_rtt_ms"])
        self.assertIsNone(train_res["jitter_ms"])

    def test_03_jitter_calculation_math(self):
        """Verify consecutive MAD jitter formula calculation."""
        # Known sequence: 10.0, 14.0, 11.0, 15.0 -> MAD = 3.6667
        rtts = [10.0, 14.0, 11.0, 15.0]
        jitter = UdpRttProber.calculate_jitter(rtts)
        self.assertAlmostEqual(jitter, 3.6667, places=3)

        self.assertEqual(UdpRttProber.calculate_jitter([10.0]), 0.0)
        self.assertIsNone(UdpRttProber.calculate_jitter([]))

    def test_04_execution_backend_detection(self):
        """Verify backend hierarchy detection and kernel capability inspection."""
        backend = get_execution_backend(force_refresh=True)
        self.assertTrue(backend.is_available())
        self.assertIn(backend.name, ("root", "sudo", "rootless_userns"))

        status = backend.get_status()
        self.assertEqual(status["status"], "available")
        self.assertIn("kernel", status)
        self.assertTrue(status["kernel"]["cake"])
        self.assertTrue(status["kernel"]["netem"])

    def test_05_tc_manager_with_backend(self):
        """Verify TcManager executes through backend and parses kernel state accurately."""
        backend = get_execution_backend()
        tc = TcManager(iface="lo", namespace=None, backend=backend)
        state = tc.get_qdisc_state()
        self.assertIn("status", state)
        self.assertIn("interface", state)
        self.assertEqual(state["interface"], "lo")

    def test_06_netns_manager_with_backend(self):
        """Verify NetnsManager reflects execution backend capabilities truthfully."""
        backend = get_execution_backend()
        netns = NetnsManager(backend=backend)
        self.assertEqual(netns.backend_name, backend.name)
        setup_res = netns.setup()
        self.assertIn("status", setup_res)

    def test_07_live_sniffer_interface_detection(self):
        """Verify LiveFlowSniffer detects interfaces and reports status cleanly."""
        sniffer = LiveFlowSniffer()
        self.assertGreaterEqual(len(sniffer.ifaces), 1)
        status = sniffer.get_status()
        self.assertEqual(status["status"], "stopped")
        self.assertIsNone(status["last_error"])

    def test_08_evidence_db_runs_and_policy_changes(self):
        """Verify EvidenceDB auto-populates experiment_runs and policy_changes."""
        db_file = os.path.join(self.test_dir, "test_evidence.db")
        db = EvidenceDB(db_file)

        exp_id = db.record_experiment("SCENARIO_B", "ADAPTIVE", {"nominal_mbps": 100})
        db.record_policy_change(
            experiment_id=exp_id,
            previous_policy="DEFAULT_FAIRNESS_100M",
            new_policy="CONGESTION_MANAGEMENT_19M",
            reason="WAN collapse detected"
        )
        db.finish_experiment(exp_id)

        with sqlite3.connect(db_file) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Check experiments
            cur.execute("SELECT * FROM experiments WHERE experiment_id = ?", (exp_id,))
            exp = cur.fetchone()
            self.assertIsNotNone(exp)
            self.assertEqual(exp["status"], "COMPLETED")

            # Check experiment_runs
            cur.execute("SELECT * FROM experiment_runs WHERE experiment_id = ?", (exp_id,))
            runs = cur.fetchall()
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["experiment_id"], exp_id)
            self.assertEqual(runs[0]["status"], "COMPLETED")

            # Check policy_changes
            cur.execute("SELECT * FROM policy_changes WHERE experiment_id = ?", (exp_id,))
            pchanges = cur.fetchall()
            self.assertEqual(len(pchanges), 1)
            self.assertEqual(pchanges[0]["previous_policy"], "DEFAULT_FAIRNESS_100M")
            self.assertEqual(pchanges[0]["new_policy"], "CONGESTION_MANAGEMENT_19M")

    def test_09_purge_of_synthetic_constants(self):
        """Verify that synthetic constants 21.2, 84.5, 0.12, 42.0 are completely absent from scenario_runner.py."""
        scenario_runner_path = os.path.join(PROJECT_ROOT, "experiments", "scenario_runner.py")
        with open(scenario_runner_path, "r") as f:
            content = f.read()

        forbidden_patterns = [
            "21.2",
            "84.5",
            "0.12",
            "42.0",
            "backlog_pkts\") or 12",
            "backlog_pkts\") or 0"
        ]
        for pattern in forbidden_patterns:
            self.assertNotIn(pattern, content, f"Forbidden synthetic pattern found in scenario_runner.py: '{pattern}'")


if __name__ == "__main__":
    unittest.main()
