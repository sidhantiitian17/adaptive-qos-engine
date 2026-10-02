import sys
sys.path.append(".")
from link_estimator import LinkEstimator

def test_estimator(target_ip, ground_truth_mbps, tolerance_pct=20):
    est = LinkEstimator(target_ip)
    print(f"=== Testing estimator against ground truth: {ground_truth_mbps} Mbps ===")
    result = est.estimate()

    if result is None:
        print("FAIL: Estimator returned no result")
        return False

    error_pct = abs(result - ground_truth_mbps) / ground_truth_mbps * 100
    passed = error_pct <= tolerance_pct

    print(f"\nGround truth : {ground_truth_mbps} Mbps")
    print(f"Estimated    : {result} Mbps")
    print(f"Error        : {error_pct:.1f}%")
    print(f"Tolerance    : {tolerance_pct}%")
    print(f"Result       : {'PASS ✅' if passed else 'FAIL ❌'}")
    return passed

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "10.0.3.2"
    ground_truth = float(sys.argv[2]) if len(sys.argv) > 2 else 30
    tolerance = float(sys.argv[3]) if len(sys.argv) > 3 else 20

    ok = test_estimator(target, ground_truth, tolerance)
    sys.exit(0 if ok else 1)
