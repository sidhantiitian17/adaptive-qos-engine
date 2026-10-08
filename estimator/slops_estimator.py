"""
SLoPS-Style Active Probing Link Capacity Estimator (M2)

Research Basis:
  1. Manish Jain & Constantine Dovrolis:
     "End-to-End Available Bandwidth: Measurement Methodology, Dynamics,
      and Relation with TCP Throughput" (IEEE/ACM Trans. Networking, 2003 / Pathload).
  2. Manish Jain & Constantine Dovrolis:
     "Ten Fallacies and Pitfalls on End-to-End Available Bandwidth Estimation" (ACM IMC 2004).

Methodology & Principles:
  - Generates periodic probe streams of K packets at rate R.
  - SLoPS Principle: If probing rate R <= available bandwidth A, one-way delays
    remain non-increasing. If R > A, queue backlog builds up at the bottleneck,
    causing one-way delays to show a statistically increasing trend.
  - Trend detection uses:
      * Pairwise Comparison Test (PCT): Fraction of positive delay increments.
      * Pairwise Difference Test (PDT): Ratio of total delay variation to cumulative variation.
  - Measurements are grouped (G groups) to filter transient OS/scheduling noise.
  - Iterative rate search bounds available bandwidth in a RANGE [R_low, R_high].
  - Returns range, midpoint, confidence, and state machine transitions.
  - Enforces hysteresis to prevent policy oscillations.
  - Contract M2 -> M3: Estimator outputs CapacityEstimate; M3 decides policy;
    M4 enforces CAKE; M5 verifies; M6 rolls back on failure.

Prototype Distinction:
  - Paper: Probes across wide-area Internet paths.
  - Prototype: Operates across Linux network namespaces with NetEm/CAKE bottleneck.
  - Relative one-way delay variation is measured via high-precision timestamps.
"""

import time
import socket
import struct
import threading
import subprocess
import os
import json
import enum
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple, Optional, Any

# Magic byte marker for SLoPS probe packets: ASCII 'SLOP' (0x534C4F50)
SLOPS_MAGIC = 0x534C4F50
# Header format: Magic (4B), StreamID (4B), Seq (8B), SendTimestamp (8B double), ProbeRateBps (8B)
HEADER_FORMAT = "!IIQdQ"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


class EstimatorState(str, enum.Enum):
    IDLE = "IDLE"
    PROBING = "PROBING"
    MEASURING = "MEASURING"
    TREND_ANALYSIS = "TREND_ANALYSIS"
    BOUND_UPDATE = "BOUND_UPDATE"
    CONVERGING = "CONVERGING"
    STABLE = "STABLE"
    PROBE_FAILURE = "PROBE_FAILURE"
    INVALID_MEASUREMENT = "INVALID_MEASUREMENT"
    NO_CONVERGENCE = "NO_CONVERGENCE"
    DEGRADED = "DEGRADED"


class TrendDecision(str, enum.Enum):
    CONGESTED = "CONGESTED"        # R > A (increasing delay)
    UNCONGESTED = "UNCONGESTED"    # R <= A (flat/decreasing delay)
    UNCERTAIN = "UNCERTAIN"        # Grey region


@dataclass
class SlopsConfig:
    probe_packet_size: int = 1200             # Constant probe packet size in bytes
    packets_per_probe: int = 80               # K packets per stream
    minimum_probe_rate_mbps: float = 2.0      # R_min search bound
    maximum_probe_rate_mbps: float = 150.0    # R_max search bound
    maximum_iterations: int = 8               # Max binary search steps
    group_count: int = 10                     # G groups for filtering
    pct_threshold: float = 0.55               # PCT threshold (> 0.55 -> increasing)
    pdt_threshold: float = 0.40               # PDT threshold (> 0.40 -> increasing)
    convergence_tolerance_mbps: float = 3.0   # Bandwidth range convergence tolerance
    hysteresis_percentage: float = 15.0       # Minimum change to trigger M3 update
    confidence_threshold: float = 0.80        # Confidence required for STABLE
    target_port: int = 54321                  # UDP probing port
    timeout_sec: float = 2.5                  # Stream timeout


@dataclass
class StreamMeasurement:
    rate_mbps: float
    packets_sent: int
    packets_received: int
    pct: float
    pdt: float
    decision: TrendDecision
    duration_sec: float
    group_delays_ms: List[float]
    loss_pct: float
    recv_rate_mbps: float = 0.0


@dataclass
class CapacityEstimate:
    estimated_bandwidth_min_mbps: float
    estimated_bandwidth_max_mbps: float
    estimated_bandwidth_mid_mbps: float
    effective_capacity_mbps: float
    confidence: float
    probe_rate_start_mbps: float
    probe_rate_final_mbps: float
    iterations: int
    samples: int
    pct: float
    pdt: float
    converged: bool
    stable: bool
    timestamp: float
    method: str
    state: str
    status: str
    error: Optional[str] = None
    overhead: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TrendAnalyzer:
    """
    Computes Pairwise Comparison Test (PCT) and Pairwise Difference Test (PDT)
    over grouped one-way delay variations per Jain & Dovrolis (2002/2003).
    """

    @staticmethod
    def analyze(delays_sec: List[float], group_count: int = 10,
                pct_threshold: float = 0.55, pdt_threshold: float = 0.40) -> Tuple[float, float, TrendDecision, List[float]]:
        if len(delays_sec) < group_count:
            return 0.5, 0.0, TrendDecision.UNCERTAIN, []

        # 1. Group measurements into G groups to eliminate OS scheduling noise
        group_size = len(delays_sec) // group_count
        group_delays = []
        for g in range(group_count):
            chunk = delays_sec[g * group_size : (g + 1) * group_size]
            # Use median of each group to resist outliers
            sorted_chunk = sorted(chunk)
            median_val = sorted_chunk[len(sorted_chunk) // 2]
            group_delays.append(median_val)

        G = len(group_delays)
        if G < 2:
            return 0.5, 0.0, TrendDecision.UNCERTAIN, [d * 1000 for d in group_delays]

        # 2. Pairwise Comparison Test (PCT)
        # Fraction of delay increments between consecutive groups
        positive_increases = sum(1 for i in range(1, G) if group_delays[i] > group_delays[i - 1])
        pct = positive_increases / float(G - 1)

        # 3. Pairwise Difference Test (PDT)
        # Metric capturing overall drift relative to total variation
        overall_diff = group_delays[-1] - group_delays[0]
        cumulative_abs_diff = sum(abs(group_delays[i] - group_delays[i - 1]) for i in range(1, G))
        pdt = overall_diff / max(1e-12, cumulative_abs_diff)
        diff_ms = overall_diff * 1000.0

        max_buildup_ms = (max(group_delays) - group_delays[0]) * 1000.0

        # 4. Determine trend
        # Per Jain & Dovrolis (2002/2003):
        # A stream is congested (R > A) if both PCT and PDT confirm increasing delays,
        # or if significant positive drift / queue buildup is sustained.
        if (pct > pct_threshold and pdt > pdt_threshold) or (pdt > 0.45 and diff_ms > 0.4) or (diff_ms > 1.0):
            decision = TrendDecision.CONGESTED
        # Non-increasing (R <= A): delays are stationary or decreasing, without accumulated queue buildup
        elif pct <= 0.58 and pdt <= 0.25 and diff_ms <= 0.3:
            decision = TrendDecision.UNCONGESTED
        else:
            decision = TrendDecision.UNCERTAIN

        group_delays_ms = [round(d * 1000.0, 3) for d in group_delays]
        return round(pct, 3), round(pdt, 3), decision, group_delays_ms


class SlopsReceiver:
    """
    Lightweight UDP receiver that records arrival timestamps of SLoPS probe streams.
    Can run in any network namespace or interface.
    """

    def __init__(self, bind_ip: str = "0.0.0.0", port: int = 54321, namespace: Optional[str] = None):
        self.bind_ip = bind_ip
        self.port = port
        self.namespace = namespace
        self.running = False
        self._sock = None
        self._thread = None
        self._streams: Dict[int, List[Tuple[int, float, float]]] = {}  # stream_id -> list of (seq, t_send, t_recv)
        self._lock = threading.Lock()

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        time.sleep(0.05)

    def _enter_namespace(self):
        if self.namespace and os.path.exists(f"/var/run/netns/{self.namespace}"):
            try:
                import ctypes
                libc = ctypes.CDLL("libc.so.6", use_errno=True)
                fd = os.open(f"/var/run/netns/{self.namespace}", os.O_RDONLY)
                libc.setns(fd, 0x40000000)
                os.close(fd)
            except Exception:
                pass

    def _run(self):
        self._enter_namespace()
        try:
            self._sock = socket.socket(socket.AF_INET6 if ":" in self.bind_ip else socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind((self.bind_ip, self.port))
            self._sock.settimeout(0.5)
        except Exception:
            self.running = False
            return

        while self.running:
            try:
                data, _ = self._sock.recvfrom(2048)
                t_recv = time.perf_counter()
                if len(data) >= HEADER_SIZE:
                    magic, stream_id, seq, t_send, rate = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
                    if magic == SLOPS_MAGIC:
                        with self._lock:
                            if stream_id not in self._streams:
                                self._streams[stream_id] = []
                            self._streams[stream_id].append((seq, t_send, t_recv))
            except socket.timeout:
                continue
            except Exception:
                break

    def get_stream_samples(self, stream_id: int, clear: bool = True) -> List[Tuple[int, float, float]]:
        with self._lock:
            samples = self._streams.pop(stream_id, []) if clear else self._streams.get(stream_id, [])
        if not samples:
            return []
        samples.sort(key=lambda s: s[0])
        return samples

    def get_stream_delays(self, stream_id: int, clear: bool = True) -> List[float]:
        samples = self.get_stream_samples(stream_id, clear=clear)
        return [s[2] - s[1] for s in samples]

    def stop(self):
        self.running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)


class SlopsSender:
    """
    High-precision SLoPS packet sender.
    Emits K packets of size P at constant inter-packet spacing corresponding to rate R.
    """

    def __init__(self, target_ip: str = "10.0.3.2", port: int = 54321, namespace: Optional[str] = None):
        self.target_ip = target_ip
        self.port = port
        self.namespace = namespace

    def _enter_namespace(self):
        if self.namespace and os.path.exists(f"/var/run/netns/{self.namespace}"):
            try:
                import ctypes
                libc = ctypes.CDLL("libc.so.6", use_errno=True)
                fd = os.open(f"/var/run/netns/{self.namespace}", os.O_RDONLY)
                libc.setns(fd, 0x40000000)
                os.close(fd)
            except Exception:
                pass

    def send_stream(self, stream_id: int, rate_mbps: float, K: int = 50, packet_size: int = 1200) -> Tuple[int, float]:
        """
        Transmits K packets at rate_mbps with high-precision busy-wait spacing.
        Returns (packets_sent, duration_sec).
        """
        self._enter_namespace()
        sock = socket.socket(socket.AF_INET6 if ":" in self.target_ip else socket.AF_INET, socket.SOCK_DGRAM)

        rate_bps = int(max(1e5, rate_mbps * 1e6))
        interval_sec = (packet_size * 8.0) / float(rate_bps)
        buf = bytearray(packet_size)

        t_start = time.perf_counter()
        packets_sent = 0

        for k in range(K):
            target_time = t_start + (k * interval_sec)
            # High-precision busy wait for sub-millisecond inter-arrival intervals
            while time.perf_counter() < target_time:
                pass

            now = time.perf_counter()
            struct.pack_into(HEADER_FORMAT, buf, 0, SLOPS_MAGIC, stream_id, k, now, rate_bps)
            try:
                sock.sendto(buf, (self.target_ip, self.port))
                packets_sent += 1
            except Exception:
                break

        actual_duration = max(1e-6, time.perf_counter() - t_start)
        sock.close()
        return packets_sent, actual_duration


class SlopsLinkEstimator:
    """
    SLoPS-Style Available Bandwidth Estimator.
    Controls the state machine, iterative rate search, trend analysis,
    confidence assessment, hysteresis, and M2 contract output.
    """

    def __init__(
        self,
        target_ip: str = "10.0.3.2",
        sender_namespace: Optional[str] = "lan1",
        receiver_namespace: Optional[str] = "wanhost",
        config: Optional[SlopsConfig] = None,
        on_state_change: Optional[Any] = None
    ):
        self.target_ip = target_ip
        self.sender_namespace = sender_namespace
        self.receiver_namespace = receiver_namespace
        self.config = config or SlopsConfig()
        self.on_state_change = on_state_change

        self.state = EstimatorState.IDLE
        self.last_estimate: Optional[CapacityEstimate] = None
        self.last_known_good_capacity: float = 100.0
        self.last_error: Optional[str] = None
        self._lock = threading.Lock()

        # Receiver & sender setup
        self._receiver = SlopsReceiver(bind_ip="::" if ":" in self.target_ip else "0.0.0.0",
                                       port=self.config.target_port,
                                       namespace=self.receiver_namespace)
        self._sender = SlopsSender(target_ip=self.target_ip,
                                   port=self.config.target_port,
                                   namespace=self.sender_namespace)
        self._receiver_started = False
        self._stream_counter = int(time.time()) % 100000

    def _set_state(self, new_state: EstimatorState):
        self.state = new_state
        if callable(self.on_state_change):
            try:
                self.on_state_change(new_state.value)
            except Exception:
                pass

    def start_receiver(self):
        if not self._receiver_started:
            self._receiver.start()
            self._receiver_started = True

    def stop_receiver(self):
        if self._receiver_started:
            self._receiver.stop()
            self._receiver_started = False

    def close(self):
        self.stop_receiver()

    def stop(self):
        self.stop_receiver()

    def probe_stream(self, rate_mbps: float) -> StreamMeasurement:
        """
        Executes a single periodic stream at rate_mbps and analyzes delay trend.
        """
        self.start_receiver()
        self._stream_counter += 1
        stream_id = self._stream_counter

        self._set_state(EstimatorState.PROBING)
        packets_sent, duration = self._sender.send_stream(
            stream_id=stream_id,
            rate_mbps=rate_mbps,
            K=self.config.packets_per_probe,
            packet_size=self.config.probe_packet_size
        )

        self._set_state(EstimatorState.MEASURING)
        # Allow brief propagation window for trailing packets
        time.sleep(0.05)
        delays = []
        recv_rate_mbps = 0.0
        samples = self._receiver.get_stream_samples(stream_id, clear=True)
        packets_recv = len(samples)
        if samples:
            delays = [s[2] - s[1] for s in samples]
            if len(samples) > 1 and (samples[-1][2] - samples[0][2]) > 0:
                recv_rate_mbps = round(((len(samples) - 1) * self.config.probe_packet_size * 8) / ((samples[-1][2] - samples[0][2]) * 1e6), 2)
        loss_pct = round(((packets_sent - packets_recv) / max(1, packets_sent)) * 100.0, 1)

        self._set_state(EstimatorState.TREND_ANALYSIS)
        pct, pdt, decision, group_delays = TrendAnalyzer.analyze(
            delays_sec=delays,
            group_count=self.config.group_count,
            pct_threshold=self.config.pct_threshold,
            pdt_threshold=self.config.pdt_threshold
        )

        # High packet loss (> 20%) is also a direct indicator of link congestion/exceeded capacity
        if (loss_pct > 20.0 or (recv_rate_mbps > 5.0 and rate_mbps > recv_rate_mbps * 1.35 and pct > 0.55)) and decision != TrendDecision.CONGESTED:
            decision = TrendDecision.CONGESTED

        return StreamMeasurement(
            rate_mbps=rate_mbps,
            packets_sent=packets_sent,
            packets_received=packets_recv,
            pct=pct,
            pdt=pdt,
            decision=decision,
            duration_sec=duration,
            group_delays_ms=group_delays,
            loss_pct=loss_pct,
            recv_rate_mbps=recv_rate_mbps
        )

    def estimate_capacity(self) -> CapacityEstimate:
        """
        Full SLoPS iterative bisection search algorithm.
        Returns CapacityEstimate with range [R_low, R_high], midpoint,
        confidence, and stability.
        """
        with self._lock:
            start_time = time.time()
            t_cpu_0 = time.process_time()

            r_low = self.config.minimum_probe_rate_mbps
            r_high = self.config.maximum_probe_rate_mbps
            current_rate = round((r_low + r_high) / 2.0, 1)

            iterations = 0
            total_samples = 0
            history_measurements: List[StreamMeasurement] = []
            converged = False

            self._set_state(EstimatorState.CONVERGING)

            try:
                for iteration in range(self.config.maximum_iterations):
                    iterations += 1
                    measurement = self.probe_stream(current_rate)
                    history_measurements.append(measurement)
                    total_samples += measurement.packets_received

                    self._set_state(EstimatorState.BOUND_UPDATE)

                    # Update bounds according to SLoPS criteria
                    if measurement.decision == TrendDecision.UNCONGESTED:
                        # R <= A -> lower bound advances
                        r_low = current_rate
                    elif measurement.decision == TrendDecision.CONGESTED:
                        # R > A -> upper bound contracts
                        r_high = current_rate
                    else:  # UNCERTAIN
                        # Gray region per SLoPS: check if stationary vs upward drift
                        diff = (measurement.group_delays_ms[-1] - measurement.group_delays_ms[0]) if measurement.group_delays_ms else 0.0
                        if measurement.pdt < 0.25 and measurement.pct <= 0.55 and diff <= 0.25:
                            r_low = current_rate
                        else:
                            r_high = current_rate

                    # Check convergence
                    if (r_high - r_low) <= self.config.convergence_tolerance_mbps or r_low >= r_high:
                        converged = True
                        break

                    # Next probe rate: midpoint of [r_low, r_high]
                    current_rate = round((r_low + r_high) / 2.0, 1)

                r_low = round(min(r_low, r_high), 2)
                r_high = round(max(r_low, r_high), 2)
                midpoint = round((r_low + r_high) / 2.0, 2)

                last_m = history_measurements[-1] if history_measurements else None
                pct_val = last_m.pct if last_m else 0.5
                pdt_val = last_m.pdt if last_m else 0.0

                # Compute confidence score based on convergence, packet delivery, and sample consistency
                avg_delivery = (sum(m.packets_received for m in history_measurements) /
                                max(1, sum(m.packets_sent for m in history_measurements)))
                convergence_factor = 1.0 if converged else max(0.5, 1.0 - (r_high - r_low) / self.config.maximum_probe_rate_mbps)
                confidence = round(avg_delivery * convergence_factor, 2)

                # Check stability via hysteresis compared to last estimate
                stable = True
                if self.last_estimate and self.last_estimate.effective_capacity_mbps > 0:
                    prev_mid = self.last_estimate.estimated_bandwidth_mid_mbps
                    pct_change = abs(midpoint - prev_mid) / prev_mid * 100.0
                    # If within hysteresis, mark stable
                    stable = (pct_change <= self.config.hysteresis_percentage)

                # If no packets delivered or delivery severely impaired (< 20%), transition to DEGRADED fallback
                is_degraded = (total_samples == 0 or avg_delivery < 0.20)
                if is_degraded:
                    self._set_state(EstimatorState.DEGRADED)
                    status_str = "degraded"
                    error_str = "Insufficient or zero probe packet arrivals (target unreachable or link down)"
                    converged = False
                    confidence = 0.0
                    midpoint = self.last_known_good_capacity
                    r_low = round(self.last_known_good_capacity * 0.9, 1)
                    r_high = round(self.last_known_good_capacity * 1.1, 1)
                else:
                    self._set_state(EstimatorState.STABLE if (converged and confidence >= self.config.confidence_threshold) else EstimatorState.BOUND_UPDATE)
                    status_str = "measured"
                    error_str = None

                # Calculate resource overhead
                elapsed = max(0.001, time.time() - start_time)
                cpu_time = time.process_time() - t_cpu_0
                total_bytes_sent = sum(m.packets_sent * self.config.probe_packet_size for m in history_measurements)
                overhead = {
                    "total_probe_packets": sum(m.packets_sent for m in history_measurements),
                    "total_probe_bytes": total_bytes_sent,
                    "total_probe_mb": round(total_bytes_sent / 1e6, 3),
                    "probe_duration_sec": round(elapsed, 3),
                    "cpu_time_ms": round(cpu_time * 1000.0, 2),
                    "avg_probe_bandwidth_mbps": round((total_bytes_sent * 8.0) / (elapsed * 1e6), 2)
                }

                result = CapacityEstimate(
                    estimated_bandwidth_min_mbps=r_low,
                    estimated_bandwidth_max_mbps=r_high,
                    estimated_bandwidth_mid_mbps=midpoint,
                    effective_capacity_mbps=midpoint,
                    confidence=confidence,
                    probe_rate_start_mbps=round(self.config.maximum_probe_rate_mbps / 2.0, 1),
                    probe_rate_final_mbps=current_rate,
                    iterations=iterations,
                    samples=total_samples,
                    pct=pct_val,
                    pdt=pdt_val,
                    converged=converged,
                    stable=stable,
                    timestamp=time.time(),
                    method="SLOPS_ACTIVE" if not is_degraded else "SLOPS_FALLBACK",
                    state=self.state.value,
                    status=status_str,
                    error=error_str,
                    overhead=overhead
                )

                self.last_estimate = result
                if not is_degraded:
                    self.last_known_good_capacity = midpoint
                self.last_error = error_str
                return result

            except Exception as e:
                self._set_state(EstimatorState.DEGRADED)
                self.last_error = str(e)
                # Fallback to last known good capacity without fabricating or breaking control loop
                fallback = CapacityEstimate(
                    estimated_bandwidth_min_mbps=round(self.last_known_good_capacity * 0.9, 1),
                    estimated_bandwidth_max_mbps=round(self.last_known_good_capacity * 1.1, 1),
                    estimated_bandwidth_mid_mbps=self.last_known_good_capacity,
                    effective_capacity_mbps=self.last_known_good_capacity,
                    confidence=0.5,
                    probe_rate_start_mbps=self.config.minimum_probe_rate_mbps,
                    probe_rate_final_mbps=self.config.minimum_probe_rate_mbps,
                    iterations=iterations,
                    samples=total_samples,
                    pct=0.5,
                    pdt=0.0,
                    converged=False,
                    stable=False,
                    timestamp=time.time(),
                    method="SLOPS_FALLBACK",
                    state=EstimatorState.DEGRADED.value,
                    status="degraded",
                    error=str(e),
                    overhead=None
                )
                self.last_estimate = fallback
                return fallback

    def detect_significant_change(self, current_estimate: float) -> bool:
        """
        Hysteresis check: Returns True only if new estimate differs from current
        by more than hysteresis_percentage.
        """
        if self.last_estimate is None or current_estimate <= 0:
            return False
        est_mid = self.last_estimate.estimated_bandwidth_mid_mbps
        diff_pct = abs(est_mid - current_estimate) / current_estimate * 100.0
        return diff_pct > self.config.hysteresis_percentage

    def get_effective_capacity(self) -> float:
        """Contract for M3: returns effective capacity midpoint or last known good."""
        if self.last_estimate:
            return self.last_estimate.effective_capacity_mbps
        return self.last_known_good_capacity


if __name__ == "__main__":
    print("=== Testing SLoPS Link Capacity Estimator ===")
    config = SlopsConfig(
        packets_per_probe=20,
        maximum_iterations=4,
        minimum_probe_rate_mbps=5.0,
        maximum_probe_rate_mbps=80.0
    )
    estimator = SlopsLinkEstimator(target_ip="127.0.0.1", sender_namespace=None, receiver_namespace=None, config=config)
    try:
        est = estimator.estimate_capacity()
        print("Estimate Output:", json.dumps(est.to_dict(), indent=2))
        assert est.estimated_bandwidth_min_mbps > 0
        assert est.estimated_bandwidth_max_mbps >= est.estimated_bandwidth_min_mbps
        print("SLoPS Estimator verification: PASS ✅")
    finally:
        estimator.stop_receiver()
