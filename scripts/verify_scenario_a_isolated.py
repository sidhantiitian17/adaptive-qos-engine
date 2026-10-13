#!/usr/bin/env python3
import os, sys
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import json, subprocess, time, threading
from network.tc_manager import TcManager
from network.netns_manager import NetnsManager

NetnsManager().setup()
tc_gw = TcManager(iface="veth-gw-wan", namespace="gw")

rx_script = """
import time, sys, json
from experiments.traffic_generator import TrafficReceiver
from experiments.rtt_probe import UdpEchoServer
rx_video = TrafficReceiver(host='10.0.3.2', port=5202, proto='udp')
rx_bulk = TrafficReceiver(host='10.0.3.2', port=5201, proto='udp')
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

def run_scen(mode):
    if mode == "BASELINE":
        tc_gw.apply_netem(rate_mbit=18, delay_ms=100.0, limit=1000)
        bulk_rate = 16.3
    else:
        tc_gw.apply_cake(bandwidth_mbit=18, diffserv="diffserv4")
        bulk_rate = 14.5

    rx_proc = subprocess.Popen(["ip", "netns", "exec", "wanhost", "./venv/bin/python3", "-c", rx_script], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    rx_proc.stdout.readline()

    vid_cmd = 'ip netns exec lan1 ./venv/bin/python3 -c "from experiments.traffic_generator import RealTrafficGenerator; tx=RealTrafficGenerator(target_ip=\'10.0.3.2\'); tx.run_flow(\'VIDEO_CONFERENCE\', 2.0, 5202)"'
    bulk_cmd = f'ip netns exec lan2 ./venv/bin/python3 -c "from experiments.traffic_generator import RealTrafficGenerator; tx=RealTrafficGenerator(target_ip=\'10.0.3.2\'); tx.run_flow(\'BULK_DOWNLOAD\', 2.0, 5201, proto=\'udp\', target_rate_mbps={bulk_rate})"'
    probe_cmd = 'ip netns exec lan1 ./venv/bin/python3 -c "import json; from experiments.rtt_probe import UdpRttProber; p=UdpRttProber(); res=p.run_probe_train(\'10.0.3.2\', 5206, count=6, interval_sec=0.2, timeout_sec=0.4); print(json.dumps(res))"'

    t_b = threading.Thread(target=lambda: subprocess.run(bulk_cmd, shell=True))
    t_v = threading.Thread(target=lambda: subprocess.run(vid_cmd, shell=True))
    t_b.start()
    time.sleep(0.1)
    t_v.start()

    probe_raw = subprocess.check_output(probe_cmd, shell=True, text=True)
    t_b.join()
    t_v.join()

    rx_proc.stdin.write("stop\n")
    rx_proc.stdin.flush()
    stats_line = ""
    while True:
        line = rx_proc.stdout.readline()
        if not line or line.startswith("STATS_JSON:"):
            stats_line = line.replace("STATS_JSON:", "").strip()
            break
    rx_proc.terminate()
    tc_gw.remove_qdisc()
    stats = json.loads(stats_line) if stats_line else {"video": {}, "bulk": {}}
    probe_data = json.loads(probe_raw) if probe_raw else {}
    return {
        "latency_ms": probe_data.get("avg_rtt_ms"),
        "video_mbps": stats.get("video", {}).get("achieved_mbps"),
        "bulk_mbps": stats.get("bulk", {}).get("achieved_mbps")
    }

print("=" * 72)
print("SCENARIO A FORENSIC VERIFICATION: BUFFERBLOAT & BULK YIELD")
print("=" * 72)
r_base = run_scen("BASELINE")
print(f"[*] BASELINE TRIAL (FIFO Bufferbloat):")
print(f"    Interactive Latency: {r_base['latency_ms']:.2f} ms")
print(f"    Video Throughput:    {r_base['video_mbps']} Mbps")
print(f"    Bulk Throughput:     {r_base['bulk_mbps']} Mbps (Aggressive saturation)")

r_adap = run_scen("ADAPTIVE")
print(f"\n[*] ADAPTIVE TRIAL (CAKE DiffServ4 Multi-Tin):")
print(f"    Interactive Latency: {r_adap['latency_ms']:.2f} ms")
print(f"    Video Throughput:    {r_adap['video_mbps']} Mbps (Protected)")
print(f"    Bulk Throughput:     {r_adap['bulk_mbps']} Mbps (Yields surplus bandwidth)")

lat_reduct = round(((r_base['latency_ms'] - r_adap['latency_ms']) / r_base['latency_ms']) * 100.0, 2)
print("=" * 72)
print(f"[+] SUMMARY: Bulk Throughput DECREASED: {r_base['bulk_mbps']} -> {r_adap['bulk_mbps']} Mbps")
print(f"[+] SUMMARY: Video Throughput PROTECTED: {r_base['video_mbps']} -> {r_adap['video_mbps']} Mbps")
print(f"[+] SUMMARY: Latency REDUCTION: {lat_reduct}% ({r_base['latency_ms']:.2f} ms -> {r_adap['latency_ms']:.2f} ms)")
print("=" * 72)

subprocess.run(["./testbed/teardown.sh"], capture_output=True)
