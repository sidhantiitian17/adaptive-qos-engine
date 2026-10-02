"""
Continuous metrics logger:
Polls collect_snapshot() periodically and appends JSON-lines to metrics_log.jsonl.
"""
import time
import json
import os
import sys

# Ensure local imports work cleanly
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dashboard.metrics_collector import collect_snapshot

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metrics_log.jsonl")

def run_logger(interval_sec=2, duration_sec=120):
    start = time.time()
    print(f"=== Starting Metrics Logger (interval={interval_sec}s, duration={duration_sec}s) ===")
    with open(LOG_FILE, "a") as f:
        while time.time() - start < duration_sec:
            snapshot = collect_snapshot()
            f.write(json.dumps(snapshot) + "\n")
            f.flush()
            print(f"[LOGGED] t={round(time.time()-start,1)}s | "
                  f"lat={snapshot['latency_ms']}ms | "
                  f"jit={snapshot['jitter_ms']}ms | "
                  f"q={snapshot['queue_depth_pkts']}p | "
                  f"fairness={snapshot['fairness_index']}")
            time.sleep(interval_sec)

if __name__ == "__main__":
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    run_logger(duration_sec=duration)
