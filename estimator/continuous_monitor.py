import time
import sys
from link_estimator import LinkEstimator

def monitor(target_ip, duration_sec=40, interval_sec=8):
    est = LinkEstimator(target_ip)
    start = time.time()

    print(f"=== Continuous monitoring for {duration_sec}s (probe every {interval_sec}s) ===\n")
    while time.time() - start < duration_sec:
        result = est.estimate(probe_duration=2, samples=1)
        elapsed = round(time.time() - start, 1)
        change = est.detect_change()
        flag = " <-- CHANGE DETECTED!" if change else ""
        print(f"[t={elapsed}s] Estimate: {result} Mbps{flag}")
        time.sleep(interval_sec)

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "10.0.3.2"
    monitor(target)
