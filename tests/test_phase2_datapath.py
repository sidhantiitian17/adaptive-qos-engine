"""
Phase 2 Datapath & Evidence Automation Test Suite:
Validates real socket traffic generation, zero fake fallback metrics,
Linux TC manager execution, SQLite evidence persistence, and dynamic report generation.
"""
import os
import time
import unittest
import socket
from experiments.evidence_db import EvidenceDB
from experiments.traffic_generator import RealTrafficGenerator, TrafficReceiver
from network.tc_manager import TcManager
from dashboard.metrics_collector import collect_snapshot
from estimator.passive_estimator import PassiveEstimator
from dashboard.report_generator import get_report_data, generate_report_markdown, generate_report_html


class TestPhase2TrafficDatapath(unittest.TestCase):
    """Validates real UDP/TCP socket packet transmission and rate accounting."""

    def test_udp_real_packet_exchange(self):
        port = 15202
        receiver = TrafficReceiver(host="127.0.0.1", port=port, proto="udp")
        receiver.start()
        time.sleep(0.1)

        generator = RealTrafficGenerator(target_ip="127.0.0.1")
        stats = generator.run_flow(
            profile_name="VIDEO_CONFERENCE",
            duration_sec=0.5,
            target_port=port
        )
        time.sleep(0.1)
        receiver.stop()
        rx_stats = receiver.get_stats()

        self.assertGreater(stats["packets_sent"], 0, "No packets were sent by generator")
        self.assertGreater(stats["bytes_sent"], 0, "No bytes were sent by generator")
        self.assertGreater(rx_stats["packets_received"], 0, "Receiver did not capture packets")
        self.assertGreater(rx_stats["bytes_received"], 0, "Receiver recorded 0 bytes")
        self.assertGreater(rx_stats["achieved_mbps"], 0.0, "Achieved Mbps should be non-zero")

    def test_dscp_tos_mapping(self):
        from experiments.traffic_generator import TRAFFIC_PROFILES
        self.assertEqual(TRAFFIC_PROFILES["VOICE"]["tos"], 0xB8)  # EF
        self.assertEqual(TRAFFIC_PROFILES["VIDEO_CONFERENCE"]["tos"], 0x88)  # AF41
        self.assertEqual(TRAFFIC_PROFILES["BULK_DOWNLOAD"]["tos"], 0x20)  # CS1


class TestPhase2ZeroFakeFallbacks(unittest.TestCase):
    """Enforces RULE 1: Never fabricate a measurement; return null/unavailable on failure."""

    def test_metrics_collector_unconfigured_interface(self):
        from dashboard.metrics_collector import get_cake_stats, get_latency_and_loss
        cake = get_cake_stats(namespace="nonexistent_gw", iface="nonexistent_veth")
        self.assertEqual(cake["status"], "unavailable")
        self.assertIsNone(cake["queue_depth_pkts"], "Queue depth must be None, not fabricated")
        lat = get_latency_and_loss(namespace="nonexistent_gw", target_ip="192.0.2.1")
        self.assertEqual(lat["status"], "unavailable")
        self.assertIsNone(lat["avg_ms"], "Latency must be None, not fabricated 20.0/20.5")

    def test_passive_estimator_unconfigured_interface(self):
        estimator = PassiveEstimator(iface="nonexistent_veth_test", namespace="nonexistent_ns")
        rate = estimator.sample_rate()
        self.assertEqual(rate, 0.0, "Rate must be 0.0 on missing interface, not host fallback")
        meta = estimator.get_metadata()
        self.assertEqual(meta["status"], "unavailable")
        self.assertIsNotNone(meta["error"])


class TestPhase2TcManager(unittest.TestCase):
    """Validates Linux Traffic Control invocation and safe argument-list parsing."""

    def test_tc_manager_argument_construction(self):
        tc = TcManager(iface="veth-gw-wan", namespace="gw")
        cake_res = tc.apply_cake(bandwidth_mbit=19, diffserv="diffserv4")
        self.assertIn("requested_bandwidth_mbit", cake_res)
        self.assertEqual(cake_res["requested_bandwidth_mbit"], 19)
        self.assertEqual(cake_res["diffserv_mode"], "diffserv4")

        netem_res = tc.apply_netem(rate_mbit=20, delay_ms=20.0)
        self.assertIn("requested_rate_mbit", netem_res)
        self.assertEqual(netem_res["requested_rate_mbit"], 20)
        self.assertEqual(netem_res["delay_ms"], 20.0)

    def test_tc_manager_state_schema(self):
        tc = TcManager(iface="lo", namespace=None)
        state = tc.get_qdisc_state()
        self.assertIn("qdisc_type", state)
        self.assertIn("status", state)
        self.assertIn("backlog_pkts", state)
        self.assertIn("backlog_bytes", state)
        self.assertIn("dropped", state)


class TestPhase2EvidencePersistence(unittest.TestCase):
    """Validates SQLite evidence database schema, traceability, and lineage."""

    def setUp(self):
        self.db_path = f"/tmp/test_evidence_{int(time.time()*1000)}.db"
        self.db = EvidenceDB(db_path=self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_record_and_retrieve_comparison(self):
        # Record baseline
        b_id = self.db.record_experiment("SCENARIO_A", "BASELINE", {"test": True})
        self.db.record_measurement(b_id, "latency_ms", 950.0, "ms", "socket_probe")
        self.db.record_measurement(b_id, "jitter_ms", 420.0, "ms", "socket_probe")
        self.db.finish_experiment(b_id, "COMPLETED")

        # Record adaptive
        a_id = self.db.record_experiment("SCENARIO_A", "ADAPTIVE", {"test": True})
        self.db.record_measurement(a_id, "latency_ms", 20.5, "ms", "socket_probe")
        self.db.record_measurement(a_id, "jitter_ms", 0.18, "ms", "socket_probe")
        self.db.finish_experiment(a_id, "COMPLETED")

        comp = self.db.get_latest_scenario_comparison("SCENARIO_A")
        self.assertIsNotNone(comp)
        self.assertEqual(comp["baseline_metrics"]["latency_ms"], 950.0)
        self.assertEqual(comp["adaptive_metrics"]["latency_ms"], 20.5)
        self.assertEqual(comp["baseline_metrics"]["jitter_ms"], 420.0)
        self.assertEqual(comp["adaptive_metrics"]["jitter_ms"], 0.18)


class TestPhase2ReportGenerator(unittest.TestCase):
    """Validates dynamic report generation directly from EvidenceDB."""

    def test_dynamic_report_kpi_extraction(self):
        d = get_report_data()
        self.assertIn("metadata", d)
        self.assertIn("kpis", d)
        self.assertIn("acceptance_summary", d)
        self.assertEqual(len(d["kpis"]), 6, "Must provide exactly 6 core telemetry KPIs")

        # Check each KPI has valid fields
        for kpi in d["kpis"]:
            self.assertIn("label", kpi)
            self.assertIn("baseline", kpi)
            self.assertIn("optimized", kpi)
            self.assertIn("status", kpi)
            self.assertIn(kpi["status"], ["PASS", "FAIL", "UNAVAILABLE"])

    def test_report_markdown_and_html_generation(self):
        md = generate_report_markdown()
        self.assertIsInstance(md, str)
        self.assertNotIn("__KPI_ROWS_MD__", md)
        self.assertNotIn("__ACC_ROWS_MD__", md)
        self.assertIn("Interactive Latency", md)

        html = generate_report_html(standalone=True)
        self.assertIsInstance(html, str)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("rep-kpi-card", html)


class TestPhase2ApiIntegration(unittest.TestCase):
    """Validates unified FastAPI REST endpoints against real datapath and SQLite persistence."""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from dashboard.unified_dashboard import app
        cls.client = TestClient(app)

    def test_api_comparison_dynamic_query(self):
        resp = self.client.get("/api/comparison")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("status", data)
        self.assertIn("headline", data)
        self.assertIn("baseline_experiment_id", data)
        self.assertIn("adaptive_experiment_id", data)
        self.assertIn("baseline_latency_ms", data["headline"])
        self.assertIn("optimized_latency_ms", data["headline"])

    def test_api_network_status(self):
        resp = self.client.get("/api/network/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("status", data)
        self.assertIn("gateway_qos", data)
        self.assertIn("wan_impairment", data)
        self.assertIn("estimator_capacity_mbps", data)

    def test_api_report_data_kpis(self):
        resp = self.client.get("/api/report/data")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("kpis", data)
        self.assertIn("acceptance_summary", data)
        self.assertEqual(len(data["kpis"]), 6)


if __name__ == "__main__":
    unittest.main()
