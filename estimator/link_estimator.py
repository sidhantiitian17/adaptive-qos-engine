"""
Unified Link Capacity Estimator Frontend (M2)

Integrates the SLoPS-style active probing engine (SlopsLinkEstimator)
while preserving full backward compatibility with existing callers.

Research Basis:
  1. Manish Jain & Constantine Dovrolis:
     "End-to-End Available Bandwidth: Measurement Methodology, Dynamics,
      and Relation with TCP Throughput" (IEEE/ACM Trans. Networking, 2003).
  2. Manish Jain & Constantine Dovrolis:
     "Ten Fallacies and Pitfalls on End-to-End Available Bandwidth Estimation" (ACM IMC 2004).
"""

import time
import os
import sys
from collections import deque
from typing import Optional, List, Dict, Any
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from estimator.slops_estimator import (
        SlopsLinkEstimator,
        SlopsConfig,
        CapacityEstimate,
        EstimatorState
    )
except ImportError:
    from slops_estimator import (
        SlopsLinkEstimator,
        SlopsConfig,
        CapacityEstimate,
        EstimatorState
    )


class LinkEstimator:
    """
    SLoPS-Style Available Bandwidth Estimator.
    Measures available bandwidth via iterative periodic packet streams,
    detecting queue buildup through Pairwise Comparison Test (PCT) and
    Pairwise Difference Test (PDT).
    """

    def __init__(
        self,
        target_ip: str = "10.0.3.2",
        target_port: int = 54321,
        window: int = 5,
        namespace: Optional[str] = None,
        receiver_namespace: Optional[str] = None,
        config: Optional[SlopsConfig] = None
    ):
        self.target_ip = target_ip
        self.target_port = target_port
        is_testbed = (target_ip in ["10.0.3.2", "fd00:3::2"])
        self.sender_namespace = namespace or ("lan1" if os.path.exists("/var/run/netns/lan1") and is_testbed else None)
        self.receiver_namespace = receiver_namespace or ("wanhost" if os.path.exists("/var/run/netns/wanhost") and is_testbed else None)

        self.config = config or SlopsConfig(target_port=target_port)
        self.slops = SlopsLinkEstimator(
            target_ip=self.target_ip,
            sender_namespace=self.sender_namespace,
            receiver_namespace=self.receiver_namespace,
            config=self.config
        )

        self.history = deque(maxlen=window)
        self.last_estimate: Optional[CapacityEstimate] = None
        self.last_error = None
        self.last_timestamp = None

    def estimate_slops(self) -> CapacityEstimate:
        """
        Runs the full iterative SLoPS search and returns the structured
        CapacityEstimate dataclass including available bandwidth range,
        confidence, PCT, PDT, and state transitions.
        """
        estimate = self.slops.estimate_capacity()
        self.last_estimate = estimate
        self.last_timestamp = estimate.timestamp
        self.last_error = estimate.error
        self.history.append(estimate.effective_capacity_mbps)
        return estimate

    def estimate(self, probe_duration: float = 2.0, samples: int = 3) -> Optional[float]:
        """
        Backward-compatible estimate method.
        Executes SLoPS active probing and returns the effective capacity in Mbps.
        """
        try:
            est = self.estimate_slops()
            if est and est.effective_capacity_mbps > 0:
                return round(est.effective_capacity_mbps, 2)
            return None
        except Exception as e:
            self.last_error = str(e)
            return None

    def get_details(self) -> Optional[Dict[str, Any]]:
        """Returns structured metadata of the latest estimate."""
        if self.last_estimate:
            return self.last_estimate.to_dict()
        return None

    def get_state(self) -> str:
        """Returns the current state machine state."""
        return self.slops.state.value

    def detect_change(self, threshold_pct: float = 15.0) -> bool:
        """
        Hysteresis change detection: returns True if latest estimate
        differs from preceding estimate by more than threshold_pct.
        """
        if len(self.history) < 2:
            return False
        prev, curr = self.history[-2], self.history[-1]
        if prev <= 0:
            return False
        change_pct = abs(curr - prev) / prev * 100.0
        return change_pct > threshold_pct

    def get_history(self) -> List[float]:
        """Returns history of effective capacity estimates."""
        return list(self.history)

    def close(self):
        """Clean up background receivers."""
        if hasattr(self.slops, "stop_receiver"):
            self.slops.stop_receiver()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "10.0.3.2"
    print(f"=== Estimating link capacity to {target} using SLoPS ===")
    est = LinkEstimator(target)
    try:
        details = est.estimate_slops()
        print("\nSLoPS Detailed Result:")
        import json
        print(json.dumps(details.to_dict(), indent=2))
        print(f"\nEstimated available bandwidth range: [{details.estimated_bandwidth_min_mbps}, {details.estimated_bandwidth_max_mbps}] Mbps")
        print(f"Midpoint: {details.estimated_bandwidth_mid_mbps} Mbps | Confidence: {details.confidence}")
    finally:
        est.close()
