import subprocess
import json
import time
from collections import deque

class LinkEstimator:
    """
    Direct-probing based available bandwidth estimator, inspired by
    Jain & Dovrolis SLoPS/Pathload methodology (IMC'04 fallacies paper,
    TNET'03 pathload paper). We use short iperf3 bursts as our 'probe
    stream' (K packets analog), and average over 'fleet' of samples to
    control variance (tau = averaging timescale).
    """

    def __init__(self, target_ip, target_port=5201, window=5):
        self.target_ip = target_ip
        self.target_port = target_port
        self.history = deque(maxlen=window)  # last N estimates (fleet)

    def _single_probe(self, duration_sec=2):
        """Ek chhota iperf3 burst chalao aur achieved throughput return karo (Mbps)."""
        cmd = [
            "iperf3", "-c", self.target_ip, "-p", str(self.target_port),
            "-t", str(duration_sec),"-R", "-J"  # JSON output
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration_sec + 5)
            data = json.loads(result.stdout)
            mbps = data["end"]["sum_received"]["bits_per_second"] / 1e6
            return round(mbps, 2)
        except Exception as e:
            print(f"[ERROR] Probe failed: {e}")
            return None

    def estimate(self, probe_duration=2, samples=3):
        """
        'Fleet' of samples leke average nikaalo (variance kam karne ke liye,
        jaisa Jain&Dovrolis paper mein Eq.11 discuss hua tha).
        """
        readings = []
        for i in range(samples):
            mbps = self._single_probe(probe_duration)
            if mbps is not None:
                readings.append(mbps)
                print(f"  [probe {i+1}/{samples}] {mbps} Mbps")

        if not readings:
            return None

        avg = round(sum(readings) / len(readings), 2)
        self.history.append(avg)
        return avg

    def detect_change(self, threshold_pct=20):
        """Agar last do estimates ke beech >threshold% ka farak ho, 'change detected' bolo."""
        if len(self.history) < 2:
            return False
        prev, curr = self.history[-2], self.history[-1]
        if prev == 0:
            return False
        change_pct = abs(curr - prev) / prev * 100
        return change_pct > threshold_pct

    def get_history(self):
        return list(self.history)


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "10.0.3.2"

    est = LinkEstimator(target)
    print(f"=== Estimating link capacity to {target} ===")
    result = est.estimate()
    print(f"\nEstimated available bandwidth: {result} Mbps")
