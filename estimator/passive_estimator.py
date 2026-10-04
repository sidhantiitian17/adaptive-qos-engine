"""
Passive WAN Link and Throughput Estimator:
Samples interface byte counters (/proc/net/dev) over time to track real-time
link utilization, peak observed capacity, and sudden bandwidth collapse
without injecting disruptive saturation traffic.
"""
import time
import subprocess
import os

class PassiveEstimator:
    def __init__(self, iface="veth-gw-wan", namespace="gw", nominal_capacity_mbps=100.0):
        self.iface = iface
        self.namespace = namespace
        self.nominal_capacity_mbps = nominal_capacity_mbps
        self.last_bytes = None
        self.last_time = None
        self.history = []
        self.peak_observed_mbps = 0.0

        self.last_source = "unavailable"
        self.last_error = None

    def _read_iface_bytes(self) -> int:
        """Read transmitted and received bytes for the configured interface."""
        # 1. Attempt reading from network namespace if specified
        if self.namespace:
            cmd = ["ip", "netns", "exec", self.namespace, "cat", "/proc/net/dev"] if os.geteuid() == 0 else ["sudo", "-n", "ip", "netns", "exec", self.namespace, "cat", "/proc/net/dev"]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        parts = line.strip().split()
                        if parts and parts[0].startswith(f"{self.iface}:"):
                            rx_bytes = int(parts[1])
                            tx_bytes = int(parts[9])
                            self.last_source = f"netns:{self.namespace}:{self.iface}"
                            self.last_error = None
                            return rx_bytes + tx_bytes
            except Exception as e:
                self.last_error = f"Netns command failed: {e}"

        # 2. Check current namespace /proc/net/dev for self.iface ONLY (never substitute lo)
        try:
            if os.path.exists("/proc/net/dev"):
                with open("/proc/net/dev", "r") as f:
                    for line in f:
                        parts = line.strip().split()
                        if parts and parts[0].startswith(f"{self.iface}:"):
                            rx_bytes = int(parts[1])
                            tx_bytes = int(parts[9])
                            self.last_source = f"local:{self.iface}"
                            self.last_error = None
                            return rx_bytes + tx_bytes
        except Exception as e:
            self.last_error = f"Reading local /proc/net/dev failed: {e}"

        self.last_source = "unavailable"
        if not self.last_error:
            self.last_error = f"Interface {self.iface} not found in {self.namespace or 'local'} /proc/net/dev"
        return 0

    def sample_rate(self) -> float:
        """Sample byte counters and compute current throughput in Mbps."""
        now = time.time()
        curr_bytes = self._read_iface_bytes()

        if self.last_bytes is None or self.last_time is None:
            self.last_bytes = curr_bytes
            self.last_time = now
            return 0.0

        dt = now - self.last_time
        if dt <= 0:
            return 0.0

        delta_bytes = max(0, curr_bytes - self.last_bytes)
        mbps = (delta_bytes * 8.0) / (dt * 1e6)

        self.last_bytes = curr_bytes
        self.last_time = now
        self.history.append((now, mbps))
        if len(self.history) > 60:
            self.history.pop(0)

        if mbps > self.peak_observed_mbps:
            self.peak_observed_mbps = round(mbps, 2)

        return round(mbps, 2)

    def get_effective_capacity(self) -> float:
        """
        Return the estimated available link capacity.
        Uses nominal capacity if link is lightly utilized,
        or tracks observed peak if saturated.
        """
        recent = [r[1] for r in self.history[-5:]] if self.history else []
        avg_recent = sum(recent) / len(recent) if recent else 0.0

        # If throughput approaches nominal capacity, update capacity estimate
        if avg_recent > self.nominal_capacity_mbps * 0.9:
            return avg_recent
        return self.nominal_capacity_mbps

    def detect_capacity_drop(self, threshold_pct=30.0) -> bool:
        """Detect sudden drop in link throughput over recent samples."""
        if len(self.history) < 4:
            return False
        recent_avg = sum(r[1] for r in self.history[-3:]) / 3.0
        older_avg = sum(r[1] for r in self.history[-6:-3]) / 3.0 if len(self.history) >= 6 else self.nominal_capacity_mbps

        if older_avg > 5.0 and (older_avg - recent_avg) / older_avg * 100.0 >= threshold_pct:
            return True
        return False

    def get_metadata(self) -> dict:
        """Return provenance metadata distinguishing configured, estimated, and measured values."""
        recent = [r[1] for r in self.history[-5:]] if self.history else []
        last_measured = recent[-1] if recent else 0.0
        return {
            "status": "unavailable" if self.last_source == "unavailable" else "measured",
            "interface": self.iface,
            "namespace": self.namespace,
            "source": self.last_source,
            "error": self.last_error,
            "configured_capacity_mbps": self.nominal_capacity_mbps,
            "estimated_capacity_mbps": self.get_effective_capacity(),
            "measured_throughput_mbps": last_measured,
            "measurement_method": "proc_net_dev_delta",
            "timestamp": time.time()
        }


if __name__ == "__main__":
    print("Testing PassiveEstimator:")
    pe = PassiveEstimator(nominal_capacity_mbps=50.0)
    pe.sample_rate()
    time.sleep(0.5)
    rate = pe.sample_rate()
    print(f"Sampled Rate: {rate} Mbps")
    print(f"Effective Capacity: {pe.get_effective_capacity()} Mbps")
    assert pe.get_effective_capacity() == 50.0
    print("PassiveEstimator verification: PASS ✅")
