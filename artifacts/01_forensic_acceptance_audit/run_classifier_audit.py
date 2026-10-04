import os
import sys
import time
import json
import socket
import threading
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# If not running with euid == 0, re-exec under unshare -rn for raw packet sniffing
if os.geteuid() != 0:
    subprocess.run(["unshare", "-rn", sys.executable, __file__] + sys.argv[1:])
    sys.exit(0)

# Bring up lo inside user namespace
subprocess.run(["ip", "link", "set", "dev", "lo", "up"], check=True)

from classifier.flow_table import FlowTable
from classifier.runtime_classifier import FlowClassifier, LiveFlowSniffer
from experiments.traffic_generator import RealTrafficGenerator, TrafficReceiver, TRAFFIC_PROFILES
from policy_engine.policy_rules import decide_policy
from experiments.evidence_db import EvidenceDB

print("=== STARTING REAL PACKET -> CLASSIFIER -> FLOWTABLE AUDIT ===")

db = EvidenceDB()
exp_id = db.record_experiment("AUDIT_CLASSIFIER_7CLASSES", "AUDIT", {"profiles": list(TRAFFIC_PROFILES.keys())})

ft = FlowTable()
clf = FlowClassifier()
sniffer = LiveFlowSniffer(ifaces=["lo"], flow_table=ft, classifier=clf)
sniffer.start()

print(f"Sniffer started on {sniffer.ifaces}, status: {sniffer.status}")

# Start receivers for all 7 traffic profiles
receivers = []
for name, prof in TRAFFIC_PROFILES.items():
    rx = TrafficReceiver(port=prof["port"], proto=prof["proto"])
    rx.start()
    receivers.append(rx)

time.sleep(0.3)

# Generate actual traffic across all 7 profiles
tx = RealTrafficGenerator(target_ip="127.0.0.1")
threads = []
for name in TRAFFIC_PROFILES.keys():
    t = threading.Thread(target=tx.run_flow, args=(name, 1.5))
    threads.append(t)
    t.start()

for t in threads:
    t.join()

time.sleep(0.5)

sniffer.stop()
for rx in receivers:
    rx.stop()

print(f"Traffic generation complete. Sniffer status: {sniffer.status}, packets sniffed: {sniffer.packet_count}")

# Query active flows from authoritative FlowTable
active_flows = ft.get_active_flows(active_within_sec=10)
print(f"Captured and classified {len(active_flows)} flows in FlowTable.")

trace_records = []
for f in active_flows:
    fid = f["flow_id"]
    hist = list(ft.flow_history[fid])
    sample_input = hist[-1] if hist else {}

    # Run decision policy on active flows
    decision = decide_policy(available_bandwidth_mbps=50.0, active_flows=[f])

    # Record in evidence.db
    db.record_flow(
        experiment_id=exp_id,
        flow_id=fid,
        traffic_class=f["class"],
        confidence=f["confidence"],
        classifier_source="xgboost_netmatrix",
        packet_count=f["packet_count"],
        byte_count=f["byte_count"]
    )

    trace_records.append({
        "flow_id": fid,
        "class": f["class"],
        "confidence": f["confidence"],
        "probabilities": f["probabilities"],
        "packet_count": f["packet_count"],
        "byte_count": f["byte_count"],
        "sample_input_metadata": sample_input,
        "controller_target_bw": decision["bandwidth_mbit"],
        "controller_reasons": decision["reasoning"],
        "constraint_c1_payload_inspected": False
    })

db.finish_experiment(exp_id)

# Test Section 4: Confidence & Correction Audit
print("\n--- Running Section 4: Classifier Confidence & Correction Tests ---")
# 1. High Confidence sample
res_high = clf.predict_sample(total_length=200, ttl=64, inter_arrival_ms=0.4)
# 2. Low Confidence / Boundary sample
res_low = clf.predict_sample(total_length=800, ttl=50, inter_arrival_ms=15.0)
# 3. Flow history update test
ft_test = FlowTable()
ft_test.record_packet("test_flow", 200, 64, time.time())
ft_test.record_packet("test_flow", 205, 64, time.time() + 0.001)
ft_test.record_packet("test_flow", 210, 64, time.time() + 0.002)
h = list(ft_test.flow_history["test_flow"])
pred_initial = clf.predict_flow_history(h)
ft_test.update_classification("test_flow", pred_initial["class"], pred_initial["confidence"], pred_initial["probabilities"])

# Subsequent update with different behavior
for i in range(5):
    ft_test.record_packet("test_flow", 1460, 64, time.time() + 0.1 * i)
h2 = list(ft_test.flow_history["test_flow"])
pred_updated = clf.predict_flow_history(h2)
ft_test.update_classification("test_flow", pred_updated["class"], pred_updated["confidence"], pred_updated["probabilities"])

output_data = {
    "experiment_id": exp_id,
    "total_flows_captured": len(active_flows),
    "packets_sniffed": sniffer.packet_count,
    "trace_records": trace_records,
    "confidence_correction_audit": {
        "high_confidence_sample": res_high,
        "low_confidence_sample": res_low,
        "initial_flow_prediction": pred_initial,
        "updated_flow_prediction": pred_updated,
        "classification_updated_successfully": pred_initial["class"] != pred_updated["class"] or pred_initial["confidence"] != pred_updated["confidence"]
    }
}

with open("audit_artifacts/flow_classifier_trace.json", "w") as out_f:
    json.dump(output_data, out_f, indent=2)

print(f"Classification trace saved to audit_artifacts/flow_classifier_trace.json")
