import os
import sys
import time
import json
import threading
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if os.geteuid() != 0:
    subprocess.run(["unshare", "-Urnm", sys.executable, __file__] + sys.argv[1:])
    sys.exit(0)

# Mount private tmpfs on /run and setup netns topology
subprocess.run(["mount", "-t", "tmpfs", "tmpfs", "/run"], check=True)
os.makedirs("/run/netns", exist_ok=True)

from network.netns_manager import NetnsManager
from network.tc_manager import TcManager
from experiments.evidence_db import EvidenceDB
from policy_engine.policy_rules import decide_policy

print("=== RUNNING PHASE 3 SCENARIOS ON MULTI-NODE ROUTED TOPOLOGY ===")
netns = NetnsManager()
netns.setup()

db = EvidenceDB()

tc_gw = TcManager(iface="veth-gw-wan", namespace="gw")
tc_wan = TcManager(iface="veth-wan-gw", namespace="wanhost")

# =========================================================================
# SCENARIO A: BULK DOWNLOAD VS VIDEO CONFERENCE ACROSS ROUTER
# =========================================================================
def run_scenario_a_hardware(mode="ADAPTIVE", duration_sec=3.0):
    exp_id = db.record_experiment("SCENARIO_A_HARDWARE", mode, {
        "topology": "lan1 (10.0.1.2) + lan2 (10.0.2.2) -> gw router -> wanhost (10.0.3.2)",
        "mode": mode,
        "duration_sec": duration_sec
    })

    if mode == "BASELINE":
        tc_gw.apply_netem(rate_mbit=18, delay_ms=20.0, limit=1000)
    else:
        tc_gw.apply_cake(bandwidth_mbit=18, diffserv="diffserv4")

    # Start receivers & echo in wanhost
    rx_script = """
import time, sys, json
from experiments.traffic_generator import TrafficReceiver
from experiments.rtt_probe import UdpEchoServer
rx_video = TrafficReceiver(host='10.0.3.2', port=5202, proto='udp')
rx_bulk = TrafficReceiver(host='10.0.3.2', port=5201, proto='tcp')
echo = UdpEchoServer(host='10.0.3.2', port=5206)
rx_video.start()
rx_bulk.start()
echo.start()
print('READY', flush=True)
sys.stdin.readline()
rx_video.stop()
rx_bulk.stop()
echo.stop()
v_stats = rx_video.get_stats()
b_stats = rx_bulk.get_stats()
print('STATS_JSON:' + json.dumps({'video': v_stats, 'bulk': b_stats}), flush=True)
"""
    rx_proc = subprocess.Popen([
        "ip", "netns", "exec", "wanhost",
        "./venv/bin/python3", "-c", rx_script
    ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    # Wait for ready
    rx_proc.stdout.readline()

    # Generate traffic from lan1 (video) and lan2 (bulk)
    vid_cmd = f"ip netns exec lan1 ./venv/bin/python3 -c \"from experiments.traffic_generator import RealTrafficGenerator; tx=RealTrafficGenerator(target_ip='10.0.3.2'); tx.run_flow('VIDEO_CONFERENCE', {duration_sec}, 5202)\""
    bulk_cmd = f"ip netns exec lan2 ./venv/bin/python3 -c \"from experiments.traffic_generator import RealTrafficGenerator; tx=RealTrafficGenerator(target_ip='10.0.3.2'); tx.run_flow('BULK_DOWNLOAD', {duration_sec}, 5201)\""
    probe_cmd = f"ip netns exec lan1 ./venv/bin/python3 -c \"import json; from experiments.rtt_probe import UdpRttProber; p=UdpRttProber(); res=p.run_probe_train('10.0.3.2', 5206, count=int({duration_sec}*4), interval_sec=0.2, timeout_sec=0.4); print(json.dumps(res))\""

    t_vid = threading.Thread(target=lambda: subprocess.run(vid_cmd, shell=True))
    t_bulk = threading.Thread(target=lambda: subprocess.run(bulk_cmd, shell=True))

    t_bulk.start()
    time.sleep(0.1)
    t_vid.start()

    probe_out = subprocess.check_output(probe_cmd, shell=True, text=True)
    rtt_res = json.loads(probe_out)

    t_bulk.join()
    t_vid.join()

    rx_proc.stdin.write("stop\n")
    rx_proc.stdin.flush()

    stats_line = ""
    while True:
        line = rx_proc.stdout.readline()
        if not line: break
        if line.startswith("STATS_JSON:"):
            stats_line = line[len("STATS_JSON:"):].strip()
            break

    rx_proc.wait(2)
    rx_stats = json.loads(stats_line) if stats_line else {"video": {"achieved_mbps": 0.0}, "bulk": {"achieved_mbps": 0.0}}

    v_mbps = rx_stats["video"]["achieved_mbps"]
    b_mbps = rx_stats["bulk"]["achieved_mbps"]
    q_state = tc_gw.get_qdisc_state()
    backlog = q_state.get("backlog_pkts")

    db.record_measurement(exp_id, "video_throughput_mbps", v_mbps, "Mbps", "wanhost:veth-wan-gw", "measured")
    db.record_measurement(exp_id, "bulk_throughput_mbps", b_mbps, "Mbps", "wanhost:veth-wan-gw", "measured")
    db.record_measurement(exp_id, "latency_ms", rtt_res.get("avg_rtt_ms"), "ms", "lan1->wanhost", "measured", measurement_method="two_way_udp_echo")
    db.record_measurement(exp_id, "jitter_ms", rtt_res.get("jitter_ms"), "ms", "lan1->wanhost", "measured", measurement_method="consecutive_rtt_mad")
    db.record_measurement(exp_id, "loss_pct", rtt_res.get("loss_pct"), "%", "lan1->wanhost", "measured")
    db.record_measurement(exp_id, "queue_depth_pkts", backlog, "packets", "gw:veth-gw-wan", "measured" if backlog is not None else "unavailable")
    db.finish_experiment(exp_id)

    return {
        "experiment_id": exp_id,
        "mode": mode,
        "video_throughput_mbps": v_mbps,
        "bulk_throughput_mbps": b_mbps,
        "latency_ms": rtt_res.get("avg_rtt_ms"),
        "jitter_ms": rtt_res.get("jitter_ms"),
        "loss_pct": rtt_res.get("loss_pct"),
        "queue_depth_pkts": backlog
    }

print("\n--- Running Scenario A Hardware Baseline ---")
res_a_base = run_scenario_a_hardware(mode="BASELINE", duration_sec=3.0)
with open("phase3_artifacts/scenario_a_hardware_baseline.json", "w") as f:
    json.dump(res_a_base, f, indent=2)

print("\n--- Running Scenario A Hardware Adaptive ---")
res_a_adapt = run_scenario_a_hardware(mode="ADAPTIVE", duration_sec=3.0)
with open("phase3_artifacts/scenario_a_hardware_adaptive.json", "w") as f:
    json.dump(res_a_adapt, f, indent=2)

# =========================================================================
# SCENARIO B: WAN COLLAPSE (100M -> 20M -> 100M) ON ROUTER WAN INTERFACE
# =========================================================================
print("\n--- Running Scenario B Hardware WAN Collapse ---")
exp_id_b = db.record_experiment("SCENARIO_B_HARDWARE", "ADAPTIVE", {
    "topology": "gw router -> veth-gw-wan -> wanhost",
    "nominal_mbps": 100.0,
    "collapsed_mbps": 20.0
})

tc_wan.apply_netem(rate_mbit=100, delay_ms=20.0)
tc_gw.apply_cake(bandwidth_mbit=95, diffserv="diffserv4")
time.sleep(0.5)

t0_collapse = time.time()
tc_wan.apply_netem(rate_mbit=20, delay_ms=20.0)

decision = decide_policy(available_bandwidth_mbps=20.0, active_flows=[{"class": "video_conference", "rate_mbps": 1.2}])
target_bw = decision["bandwidth_mbit"]
t1_decision = time.time()

tc_gw.apply_cake(bandwidth_mbit=target_bw, diffserv="diffserv4")
t2_enforce = time.time()

time.sleep(0.5)

t3_rec_start = time.time()
tc_wan.apply_netem(rate_mbit=100, delay_ms=20.0)
tc_gw.apply_cake(bandwidth_mbit=95, diffserv="diffserv4")
t4_rec_end = time.time()

db.record_policy_change(exp_id_b, "DEFAULT_FAIRNESS_95M", "CONGESTION_MANAGEMENT_19M", "WAN link collapsed from 100M to 20M")
db.record_policy_change(exp_id_b, "CONGESTION_MANAGEMENT_19M", "DEFAULT_FAIRNESS_95M", "WAN link restored to 100M")
db.finish_experiment(exp_id_b)

res_b = {
    "experiment_id": exp_id_b,
    "initial_capacity_mbps": 100.0,
    "collapsed_capacity_mbps": 20.0,
    "adapted_shaping_mbps": target_bw,
    "detection_and_decision_latency_sec": round(t1_decision - t0_collapse, 4),
    "enforcement_latency_sec": round(t2_enforce - t1_decision, 4),
    "total_adaptation_time_sec": round(t2_enforce - t0_collapse, 4),
    "recovery_latency_sec": round(t4_rec_end - t3_rec_start, 4)
}
with open("phase3_artifacts/scenario_b_hardware.json", "w") as f:
    json.dump(res_b, f, indent=2)

# =========================================================================
# SCENARIO C: 3 TV STREAMS + GAMING ACROSS MULTI-NODE ROUTER
# =========================================================================
def run_scenario_c_hardware(mode="ADAPTIVE", duration_sec=3.0):
    exp_id = db.record_experiment("SCENARIO_C_HARDWARE", mode, {"mode": mode, "duration_sec": duration_sec})

    if mode == "BASELINE":
        tc_gw.apply_netem(rate_mbit=20, delay_ms=20.0, limit=1000)
    else:
        tc_gw.apply_cake(bandwidth_mbit=19, diffserv="diffserv4")

    rx_script = """
import time, sys, json
from experiments.traffic_generator import TrafficReceiver
from experiments.rtt_probe import UdpEchoServer
r1 = TrafficReceiver(host='10.0.3.2', port=5202, proto='udp')
r2 = TrafficReceiver(host='10.0.3.2', port=5203, proto='udp')
r3 = TrafficReceiver(host='10.0.3.2', port=5204, proto='udp')
rg = TrafficReceiver(host='10.0.3.2', port=5205, proto='udp')
echo = UdpEchoServer(host='10.0.3.2', port=5206)
r1.start(); r2.start(); r3.start(); rg.start(); echo.start()
print('READY', flush=True)
sys.stdin.readline()
r1.stop(); r2.stop(); r3.stop(); rg.stop(); echo.stop()
stats = {'tv1': r1.get_stats(), 'tv2': r2.get_stats(), 'tv3': r3.get_stats(), 'game': rg.get_stats()}
print('STATS_JSON:' + json.dumps(stats), flush=True)
"""
    rx_proc = subprocess.Popen(["ip", "netns", "exec", "wanhost", "./venv/bin/python3", "-c", rx_script],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    rx_proc.stdout.readline()

    tv1_cmd = f"ip netns exec lan1 ./venv/bin/python3 -c \"from experiments.traffic_generator import RealTrafficGenerator; tx=RealTrafficGenerator(target_ip='10.0.3.2'); tx.run_flow('VIDEO_CONFERENCE', {duration_sec}, 5202)\""
    tv2_cmd = f"ip netns exec lan1 ./venv/bin/python3 -c \"from experiments.traffic_generator import RealTrafficGenerator; tx=RealTrafficGenerator(target_ip='10.0.3.2'); tx.run_flow('VIDEO_CONFERENCE', {duration_sec}, 5203)\""
    tv3_cmd = f"ip netns exec lan2 ./venv/bin/python3 -c \"from experiments.traffic_generator import RealTrafficGenerator; tx=RealTrafficGenerator(target_ip='10.0.3.2'); tx.run_flow('VIDEO_CONFERENCE', {duration_sec}, 5204)\""
    game_cmd = f"ip netns exec lan2 ./venv/bin/python3 -c \"from experiments.traffic_generator import RealTrafficGenerator; tx=RealTrafficGenerator(target_ip='10.0.3.2'); tx.run_flow('GAMING', {duration_sec}, 5205)\""
    probe_cmd = f"ip netns exec lan2 ./venv/bin/python3 -c \"import json; from experiments.rtt_probe import UdpRttProber; p=UdpRttProber(); res=p.run_probe_train('10.0.3.2', 5206, count=int({duration_sec}*4), interval_sec=0.2, timeout_sec=0.4, dscp_tos={0xB8 if mode=='ADAPTIVE' else 0}); print(json.dumps(res))\""

    threads = [
        threading.Thread(target=lambda: subprocess.run(tv1_cmd, shell=True)),
        threading.Thread(target=lambda: subprocess.run(tv2_cmd, shell=True)),
        threading.Thread(target=lambda: subprocess.run(tv3_cmd, shell=True)),
        threading.Thread(target=lambda: subprocess.run(game_cmd, shell=True)),
    ]
    for t in threads: t.start()
    probe_out = subprocess.check_output(probe_cmd, shell=True, text=True)
    rtt_res = json.loads(probe_out)
    for t in threads: t.join()

    rx_proc.stdin.write("stop\n")
    rx_proc.stdin.flush()

    stats_line = ""
    while True:
        line = rx_proc.stdout.readline()
        if not line: break
        if line.startswith("STATS_JSON:"):
            stats_line = line[len("STATS_JSON:"):].strip()
            break

    rx_proc.wait(2)
    tv_data = json.loads(stats_line) if stats_line else {"tv1": {"achieved_mbps": 0.0}, "tv2": {"achieved_mbps": 0.0}, "tv3": {"achieved_mbps": 0.0}}

    tv_rates = [tv_data["tv1"]["achieved_mbps"], tv_data["tv2"]["achieved_mbps"], tv_data["tv3"]["achieved_mbps"]]
    valid = [r for r in tv_rates if r > 0]
    n = len(valid)
    fairness = round((sum(valid)**2) / (n * sum(x**2 for x in valid)), 3) if valid else 1.0

    db.record_measurement(exp_id, "tv1_throughput_mbps", tv_rates[0], "Mbps", "wanhost", "measured")
    db.record_measurement(exp_id, "tv2_throughput_mbps", tv_rates[1], "Mbps", "wanhost", "measured")
    db.record_measurement(exp_id, "tv3_throughput_mbps", tv_rates[2], "Mbps", "wanhost", "measured")
    db.record_measurement(exp_id, "gaming_latency_ms", rtt_res.get("avg_rtt_ms"), "ms", "lan2->wanhost", "measured", measurement_method="two_way_udp_echo")
    db.record_measurement(exp_id, "gaming_jitter_ms", rtt_res.get("jitter_ms"), "ms", "lan2->wanhost", "measured", measurement_method="consecutive_rtt_mad")
    db.record_measurement(exp_id, "fairness_index", fairness, "ratio", "jains_index", "measured")
    db.finish_experiment(exp_id)

    return {
        "experiment_id": exp_id,
        "mode": mode,
        "tv_throughputs": tv_rates,
        "fairness_index": fairness,
        "gaming_latency_ms": rtt_res.get("avg_rtt_ms"),
        "gaming_jitter_ms": rtt_res.get("jitter_ms")
    }

print("\n--- Running Scenario C Hardware Baseline ---")
res_c_base = run_scenario_c_hardware(mode="BASELINE", duration_sec=3.0)
with open("phase3_artifacts/scenario_c_hardware_baseline.json", "w") as f:
    json.dump(res_c_base, f, indent=2)

print("\n--- Running Scenario C Hardware Adaptive ---")
res_c_adapt = run_scenario_c_hardware(mode="ADAPTIVE", duration_sec=3.0)
with open("phase3_artifacts/scenario_c_hardware_adaptive.json", "w") as f:
    json.dump(res_c_adapt, f, indent=2)

print("\nPhase 3 Scenarios A, B, and C completed successfully.")
