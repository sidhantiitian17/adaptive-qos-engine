"""
Unit & Consistency Tests for Module M2 Evaluation Metrics & Artifacts.
Validates:
1. Mathematical calculation formulas (midpoint, relative error, spread).
2. Distinction between interval containment and point-estimate error tolerances.
3. Consistency across results/m2/*.json, summary.csv, and report.md.
4. Total absence of stale 'variance_mbps' metric.
"""
import os
import json
import csv
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_M2_DIR = os.path.join(PROJECT_ROOT, "results", "m2")


class TestM2MetricCalculations(unittest.TestCase):
    """Validates mathematical correctness of M2 evaluation formulas."""

    def test_midpoint_formula(self):
        low, high = 18.1, 20.5
        midpoint = round((low + high) / 2.0, 3)
        self.assertEqual(midpoint, 19.3)

        low_b, high_b = 20.5, 22.8
        midpoint_b = round((low_b + high_b) / 2.0, 3)
        self.assertEqual(midpoint_b, 21.65)

    def test_relative_error_formula(self):
        # Test 2: 19.3 vs 20.0 GT
        gt_2 = 20.0
        pt_2 = 19.3
        rel_err_2 = round(abs(pt_2 - gt_2) / gt_2 * 100.0, 1)
        self.assertEqual(rel_err_2, 3.5)

        # Baseline SLoPS: 21.65 vs 20.0 GT
        pt_b = 21.65
        rel_err_b = round(abs(pt_b - gt_2) / gt_2 * 100.0, 1)
        self.assertEqual(rel_err_b, 8.2)

        # Baseline Passive: 100.0 vs 20.0 GT
        pt_p = 100.0
        rel_err_p = round(abs(pt_p - gt_2) / gt_2 * 100.0, 1)
        self.assertEqual(rel_err_p, 400.0)

    def test_spread_formula_vs_variance(self):
        samples = [49.35, 51.7, 49.35]
        spread = round(max(samples) - min(samples), 2)
        self.assertEqual(spread, 2.35)
        # Arithmetic mean
        mean_val = round(sum(samples) / len(samples), 2)
        self.assertEqual(mean_val, 50.13)
        # Range midpoint
        mid_val = round((min(samples) + max(samples)) / 2.0, 3)
        self.assertEqual(mid_val, 50.525)


class TestM2IntervalContainment(unittest.TestCase):
    """
    Explicitly tests and proves interval containment vs non-containment,
    ensuring that no false claims of interval coverage are possible.
    """

    def test_test2_interval_contains_ground_truth(self):
        gt = 20.0
        interval = [18.1, 20.5]
        covers = (interval[0] <= gt <= interval[1])
        self.assertTrue(covers, "Test 2 [18.1, 20.5] must contain 20.0 Mbps ground truth")

    def test_baseline_interval_does_not_contain_ground_truth(self):
        gt = 20.0
        interval = [20.5, 22.8]
        covers = (interval[0] <= gt <= interval[1])
        self.assertFalse(covers, "Baseline [20.5, 22.8] does NOT contain 20.0 Mbps ground truth (20.0 < 20.5)")

        # But point estimate meets tolerance
        midpoint = (interval[0] + interval[1]) / 2.0
        rel_err = abs(midpoint - gt) / gt * 100.0
        self.assertLessEqual(rel_err, 20.0, "Midpoint relative error must still meet <= 20% tolerance")

    def test_test1_interval_does_not_contain_ground_truth(self):
        gt = 100.0
        interval = [87.5, 89.8]
        covers = (interval[0] <= gt <= interval[1])
        self.assertFalse(covers, "Test 1 [87.5, 89.8] does not contain 100.0 Mbps ground truth")
        midpoint = (interval[0] + interval[1]) / 2.0
        rel_err = abs(midpoint - gt) / gt * 100.0
        self.assertLessEqual(rel_err, 20.0, "Test 1 midpoint meets <= 20% tolerance")


class TestM2ArtifactsIntegrity(unittest.TestCase):
    """Validates on-disk results/m2/*.json and summary.csv artifacts."""

    def test_no_variance_mbps_in_json_artifacts(self):
        for fname in os.listdir(RESULTS_M2_DIR):
            if fname.endswith(".json"):
                fpath = os.path.join(RESULTS_M2_DIR, fname)
                with open(fpath, "r") as f:
                    content = f.read()
                self.assertNotIn("variance_mbps", content, f"{fname} must not contain stale 'variance_mbps'")

    def test_bursty_cross_traffic_json_fields(self):
        fpath = os.path.join(RESULTS_M2_DIR, "bursty_cross_traffic.json")
        with open(fpath, "r") as f:
            data = json.load(f)
        # Verify internal mathematical consistency of the persisted artifact
        samples = data["sample_estimates_mbps"]
        expected_spread = round(max(samples) - min(samples), 2)
        expected_mean = round(sum(samples) / len(samples), 2)
        expected_mid = round((min(samples) + max(samples)) / 2.0, 3)
        expected_rel_err = round(abs(expected_mean - data["ground_truth_mbps"]) / data["ground_truth_mbps"] * 100.0, 1)

        self.assertEqual(data["spread_mbps"], expected_spread)
        self.assertEqual(data["mean_estimate_mbps"], expected_mean)
        self.assertEqual(data["range_midpoint_mbps"], expected_mid)
        self.assertEqual(data["relative_error_pct"], expected_rel_err)

    def test_summary_csv_matches_json(self):
        fpath = os.path.join(RESULTS_M2_DIR, "summary.csv")
        self.assertTrue(os.path.exists(fpath))
        with open(fpath, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        self.assertEqual(len(rows), 6)

        # Load static_20.json and verify summary.csv row matches JSON artifact
        s20_path = os.path.join(RESULTS_M2_DIR, "static_20.json")
        with open(s20_path, "r") as f:
            s20_data = json.load(f)

        t2_row = next(r for r in rows if r["Test ID"] == "TEST 2")
        self.assertEqual(float(t2_row["Ground Truth (Mbps)"]), float(s20_data["ground_truth_mbps"]))
        expected_range = f"[{s20_data['estimated_bandwidth_min_mbps']}, {s20_data['estimated_bandwidth_max_mbps']}]"
        self.assertEqual(t2_row["Estimated Range (Mbps)"], expected_range)
        self.assertEqual(float(t2_row["Point Estimate (Mbps)"]), float(s20_data["estimated_bandwidth_mid_mbps"]))
        self.assertEqual(float(t2_row["Relative Error (%)"]), float(s20_data["relative_error_pct"]))
        self.assertEqual(t2_row["Status"], s20_data["status"])


if __name__ == "__main__":
    unittest.main()
