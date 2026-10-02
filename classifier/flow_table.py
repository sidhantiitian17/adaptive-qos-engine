"""
Real-time thread-safe flow table tracking active network flows,
their classification states, packet statistics, and manual overrides.
"""
import time
import threading
from collections import defaultdict, deque

class FlowTable:
    def __init__(self, max_packet_history=20, flow_timeout_sec=30):
        self.lock = threading.Lock()
        self.max_packet_history = max_packet_history
        self.flow_timeout_sec = flow_timeout_sec
        self.flows = {}
        # Stores recent packet features per flow: flow_id -> deque of (length, ttl, inter_arrival_ms)
        self.flow_history = defaultdict(lambda: deque(maxlen=self.max_packet_history))
        self.last_packet_time = {}

    def record_packet(self, flow_id, length, ttl, timestamp=None):
        """
        Record a packet arrival for a flow and calculate inter-arrival time.
        Returns: (inter_arrival_ms, current_history)
        """
        if timestamp is None:
            timestamp = time.time()

        with self.lock:
            last_t = self.last_packet_time.get(flow_id, timestamp)
            inter_arrival_ms = max(0.0, (timestamp - last_t) * 1000.0)
            self.last_packet_time[flow_id] = timestamp

            self.flow_history[flow_id].append({
                "total_length": length,
                "ttl": ttl,
                "inter_arrival_ms": inter_arrival_ms,
                "timestamp": timestamp
            })

            if flow_id not in self.flows:
                self.flows[flow_id] = {
                    "flow_id": flow_id,
                    "class": "unclassified",
                    "confidence": 0.0,
                    "probabilities": {},
                    "packet_count": 0,
                    "byte_count": 0,
                    "first_seen": timestamp,
                    "last_seen": timestamp,
                    "overridden": False,
                    "needs_confirmation": False
                }

            flow = self.flows[flow_id]
            flow["packet_count"] += 1
            flow["byte_count"] += length
            flow["last_seen"] = timestamp

            history_snapshot = list(self.flow_history[flow_id])
            return inter_arrival_ms, history_snapshot

    def update_classification(self, flow_id, predicted_class, confidence, probabilities=None):
        """Update classification outcome unless flow has been manually overridden."""
        with self.lock:
            if flow_id not in self.flows:
                return
            flow = self.flows[flow_id]
            if flow.get("overridden", False):
                return  # Manual override takes precedence

            flow["class"] = predicted_class
            flow["confidence"] = round(float(confidence), 4)
            flow["probabilities"] = {k: round(float(v), 4) for k, v in (probabilities or {}).items()}
            flow["needs_confirmation"] = confidence < 0.70

    def override(self, flow_id, corrected_class):
        """Manually override classification (Fulfills Constraint C5)."""
        with self.lock:
            if flow_id not in self.flows:
                now = time.time()
                self.flows[flow_id] = {
                    "flow_id": flow_id,
                    "class": corrected_class,
                    "confidence": 1.0,
                    "probabilities": {corrected_class: 1.0},
                    "packet_count": 0,
                    "byte_count": 0,
                    "first_seen": now,
                    "last_seen": now,
                    "overridden": True,
                    "needs_confirmation": False
                }
            else:
                flow = self.flows[flow_id]
                flow["class"] = corrected_class
                flow["confidence"] = 1.0
                flow["probabilities"] = {corrected_class: 1.0}
                flow["overridden"] = True
                flow["needs_confirmation"] = False

    def get(self, flow_id):
        with self.lock:
            f = self.flows.get(flow_id)
            return dict(f) if f else None

    def get_active_flows(self, active_within_sec=15):
        """Return list of active flows within given time window."""
        now = time.time()
        with self.lock:
            active = []
            for fid, f in self.flows.items():
                if now - f["last_seen"] <= active_within_sec:
                    active.append(dict(f))
            return active

    def prune_inactive(self):
        """Evict stale flows inactive for longer than flow_timeout_sec."""
        now = time.time()
        with self.lock:
            stale = [fid for fid, f in self.flows.items() if now - f["last_seen"] > self.flow_timeout_sec]
            for fid in stale:
                del self.flows[fid]
                if fid in self.flow_history:
                    del self.flow_history[fid]
                if fid in self.last_packet_time:
                    del self.last_packet_time[fid]
            return len(stale)

    def get_summary(self):
        """Return high-level summary of active classes."""
        active = self.get_active_flows()
        summary = defaultdict(int)
        for f in active:
            summary[f["class"]] += 1
        return dict(summary)
