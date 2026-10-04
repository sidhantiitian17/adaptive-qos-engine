import os
import sys
import time
import json
import statistics
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if os.geteuid() != 0:
    subprocess.run(["unshare", "-rn", sys.executable, __file__] + sys.argv[1:])
    sys.exit(0)

subprocess.run(["ip", "link", "set", "dev", "lo", "up"], check=True)

from experiments.rtt_probe import UdpEchoServer, UdpRttProber
from network.tc_manager import TcManager

print("=== STARTING RTT, JITTER, AND NETEM IMPAIRMENT AUDIT ===")

# 1. Start Echo Server on 5206
echo = UdpEchoServer(host="127.0.0.1", port=5206)
echo.start()
time.sleep(0.1)

# 2. Test RTT Prober under unimpaired baseline (50 samples)
prober = UdpRttProber()
raw_samples_baseline = []
for seq in range(1, 51):
    rtt = prober.probe_once("127.0.0.1", 5206, seq=seq, timeout_sec=0.2)
    if rtt is not None:
        raw_samples_baseline.append(rtt)
    time.sleep(0.01)

# 3. Test NetEm impairment (Apply 25ms delay + 5ms jitter via NetEm)
tc = TcManager(iface="lo", namespace=None)
tc_netem_before = tc.get_qdisc_state()
tc.apply_netem(rate_mbit=20, delay_ms=25.0, jitter_ms=5.0)
tc_netem_active = tc.get_qdisc_state()

raw_samples_netem = []
for seq in range(1, 51):
    rtt = prober.probe_once("127.0.0.1", 5206, seq=seq, timeout_sec=0.2)
    if rtt is not None:
        raw_samples_netem.append(rtt)
    time.sleep(0.01)

tc.remove_qdisc()
tc_netem_after = tc.get_qdisc_state()

echo.stop()

# 4. Statistical analysis & percentile calculation
def analyze_rtts(rtts, requested_count=50):
    n = len(rtts)
    timeouts = requested_count - n
    loss_pct = round((timeouts / requested_count) * 100.0, 2)
    if n == 0:
        return {"n": 0, "timeouts": timeouts, "loss_pct": 100.0}

    sorted_r = sorted(rtts)
    def p(pct):
        idx = int(round((pct / 100.0) * (n - 1)))
        return sorted_r[idx]

    return {
        "n_sent": requested_count,
        "n_received": n,
        "timeouts": timeouts,
        "probe_loss_pct": loss_pct,
        "min_ms": round(min(rtts), 3),
        "median_ms": round(statistics.median(rtts), 3),
        "mean_ms": round(statistics.mean(rtts), 3),
        "p95_ms": round(p(95), 3),
        "p99_ms": round(p(99), 3),
        "max_ms": round(max(rtts), 3),
        "consecutive_mad_jitter_ms": round(prober.calculate_jitter(rtts), 4),
        "raw_samples": rtts
    }

stat_baseline = analyze_rtts(raw_samples_baseline, 50)
stat_netem = analyze_rtts(raw_samples_netem, 50)

# Save RTT raw samples artifact
rtt_output = {
    "audit": "Two-Way UDP Echo RTT and NetEm Verification",
    "unimpaired_baseline": stat_baseline,
    "netem_impaired_25ms_delay": stat_netem,
    "netem_qdisc_before": tc_netem_before,
    "netem_qdisc_active": tc_netem_active,
    "netem_qdisc_after": tc_netem_after
}

with open("audit_artifacts/rtt_raw_samples.json", "w") as f:
    json.dump(rtt_output, f, indent=2)

# Save Worked Jitter Calculation artifact
sample_seq = stat_netem["raw_samples"][:10]
diffs = [abs(sample_seq[i] - sample_seq[i-1]) for i in range(1, len(sample_seq))]
worked_jitter = sum(diffs) / len(diffs)

jitter_output = {
    "method": "RFC 3550 / Consecutive RTT Mean Absolute Difference (MAD)",
    "formula": "Jitter = (1 / (N - 1)) * sum(|RTT_i - RTT_{i-1}| for i in 2..N)",
    "first_10_samples": sample_seq,
    "consecutive_absolute_differences": [round(d, 4) for d in diffs],
    "sum_of_differences": round(sum(diffs), 4),
    "denominator_n_minus_1": len(diffs),
    "calculated_jitter_ms": round(worked_jitter, 4),
    "prober_library_output_ms": round(prober.calculate_jitter(sample_seq), 4),
    "is_match": round(worked_jitter, 4) == round(prober.calculate_jitter(sample_seq), 4)
}

with open("audit_artifacts/jitter_calculation.json", "w") as f:
    json.dump(jitter_output, f, indent=2)

print("RTT, Jitter, and NetEm forensic audit complete.")
