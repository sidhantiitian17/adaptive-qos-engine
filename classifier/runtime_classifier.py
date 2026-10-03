"""
Real-time flow classification and multi-protocol packet sniffer.
Loads trained XGBoost model and extracts NetMatrix features (IPv4 + IPv6).
Payloads are never inspected or decrypted (Constraint C1).
"""
import os
import sys
import time
import pickle
import threading
import pandas as pd
import numpy as np

# Add parent directory to path if needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from flow_table import FlowTable

class FlowClassifier:
    """Loads trained XGBoost model and performs inference on packet feature sets."""
    def __init__(self, model_path=None):
        if model_path is None:
            # Look in same directory as this file or current working directory
            cur_dir = os.path.dirname(os.path.abspath(__file__))
            candidates = [
                os.path.join(cur_dir, "xgb_model.pkl"),
                os.path.join(os.getcwd(), "classifier", "xgb_model.pkl"),
                os.path.join(os.getcwd(), "xgb_model.pkl")
            ]
            for c in candidates:
                if os.path.exists(c):
                    model_path = c
                    break

        if not model_path or not os.path.exists(model_path):
            raise FileNotFoundError(f"XGBoost model file not found in candidates: {candidates}")

        with open(model_path, "rb") as f:
            data = pickle.load(f)
            self.model = data["model"]
            self.label_encoder = data["label_encoder"]
            self.classes = list(self.label_encoder.classes_)

    def predict_sample(self, total_length: float, ttl: int, inter_arrival_ms: float) -> dict:
        """
        Predict traffic class for a single feature tuple.
        Returns: {
            'class': str,
            'confidence': float,
            'probabilities': dict,
            'needs_confirmation': bool
        }
        """
        df = pd.DataFrame([{
            "total_length": float(total_length),
            "ttl": int(ttl),
            "inter_arrival_ms": float(inter_arrival_ms)
        }])

        probs = self.model.predict_proba(df)[0]
        max_idx = int(np.argmax(probs))
        pred_class = self.classes[max_idx]
        confidence = float(probs[max_idx])

        prob_dict = {cls: float(p) for cls, p in zip(self.classes, probs)}
        return {
            "class": pred_class,
            "confidence": round(confidence, 4),
            "probabilities": prob_dict,
            "needs_confirmation": confidence < 0.70
        }

    def predict_flow_history(self, history: list) -> dict:
        """
        Aggregates recent packet history for a flow to produce a stable prediction.
        Uses median/mean of features to smooth jitter.
        """
        if not history:
            return {
                "class": "unclassified",
                "confidence": 0.0,
                "probabilities": {},
                "needs_confirmation": True
            }

        # Take median of packet lengths, modal TTL, and 75th percentile of inter-arrival
        lengths = [p["total_length"] for p in history]
        ttls = [p["ttl"] for p in history]
        arrivals = [p["inter_arrival_ms"] for p in history if p["inter_arrival_ms"] > 0]
        if not arrivals:
            arrivals = [0.1]

        agg_len = float(np.median(lengths))
        agg_ttl = int(np.median(ttls))
        agg_arr = float(np.median(arrivals))

        return self.predict_sample(agg_len, agg_ttl, agg_arr)


class LiveFlowSniffer:
    """
    Live packet sniffer capturing headers from specified interfaces.
    Inspects only IP/IPv6 length, TTL/hop limit, and arrival timing.
    Payloads are completely ignored.
    """
    def __init__(self, ifaces=None, flow_table=None, classifier=None):
        self.ifaces = ifaces or ["veth-lan1-gw", "veth-lan2-gw"]
        if isinstance(self.ifaces, str):
            self.ifaces = [self.ifaces]
        self.flow_table = flow_table or FlowTable()
        self.classifier = classifier or FlowClassifier()
        self._stop_event = threading.Event()
        self._thread = None

    def _packet_handler(self, pkt):
        try:
            from scapy.layers.inet import IP, TCP, UDP
            from scapy.layers.inet6 import IPv6
        except ImportError:
            return

        is_ipv4 = IP in pkt
        is_ipv6 = IPv6 in pkt

        if not is_ipv4 and not is_ipv6:
            return

        now = time.time()
        if is_ipv4:
            src_ip = pkt[IP].src
            dst_ip = pkt[IP].dst
            total_len = pkt[IP].len
            ttl = pkt[IP].ttl
            proto = pkt[IP].proto
        else:
            src_ip = pkt[IPv6].src
            dst_ip = pkt[IPv6].dst
            total_len = pkt[IPv6].plen + 40
            ttl = pkt[IPv6].hlim
            proto = pkt[IPv6].nh

        if TCP in pkt:
            sport = pkt[TCP].sport
            dport = pkt[TCP].dport
            proto_str = "tcp"
        elif UDP in pkt:
            sport = pkt[UDP].sport
            dport = pkt[UDP].dport
            proto_str = "udp"
        else:
            sport = 0
            dport = 0
            proto_str = f"proto{proto}"

        # Standard 5-tuple flow key
        flow_id = f"{src_ip}:{sport}->{dst_ip}:{dport}/{proto_str}"

        # Record packet in flow table
        inter_arrival_ms, history = self.flow_table.record_packet(flow_id, total_len, ttl, now)

        # Run inference once we have at least 3 packets, or periodically every 5 packets
        count = len(history)
        if count >= 3 and (count == 3 or count % 5 == 0):
            res = self.classifier.predict_flow_history(history)
            self.flow_table.update_classification(
                flow_id,
                res["class"],
                res["confidence"],
                res["probabilities"]
            )

    def start(self):
        """Start asynchronous sniffing on configured interfaces."""
        from scapy.all import sniff
        self._stop_event.clear()

        def _worker():
            try:
                sniff(
                    iface=self.ifaces,
                    prn=self._packet_handler,
                    stop_filter=lambda x: self._stop_event.is_set(),
                    store=False
                )
            except Exception as e:
                # Expected when running without kernel netns or ifaces not yet bound
                pass

        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)


def test_sniffer(duration=5, iface="veth-lan1-gw"):
    """Standalone test function for Step 1.1 verification."""
    print(f"=== Testing packet sniffer on {iface} for {duration}s ===")
    ft = FlowTable()
    clf = FlowClassifier()
    sniffer = LiveFlowSniffer(ifaces=[iface], flow_table=ft, classifier=clf)
    sniffer.start()
    time.sleep(duration)
    sniffer.stop()
    flows = ft.get_active_flows(active_within_sec=10)
    print(f"Captured {len(flows)} active flows.")
    for f in flows:
        print(f"  [{f['flow_id']}] -> Class: {f['class']} (conf: {f['confidence']}) Pkts: {f['packet_count']}")
    return len(flows)


if __name__ == "__main__":
    clf = FlowClassifier()
    print("Testing single-sample prediction:")
    for test_len, test_ttl, test_arr in [(200, 64, 0.4), (1450, 64, 2.0), (60, 64, 0.1)]:
        res = clf.predict_sample(test_len, test_ttl, test_arr)
        print(f"  len={test_len}, ttl={test_ttl}, arr={test_arr}ms -> {res['class']} (conf: {res['confidence']})")
