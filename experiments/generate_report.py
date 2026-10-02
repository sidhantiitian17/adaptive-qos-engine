"""
Baseline vs Optimized logs parse karke ek comparison report banata hai.
"""
import re

def parse_ping_log(filepath):
    with open(filepath) as f:
        content = f.read()
    match = re.search(r"rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)", content)
    loss_match = re.search(r"(\d+)% packet loss", content)
    if match:
        return {
            "min_ms": float(match.group(1)),
            "avg_ms": float(match.group(2)),
            "max_ms": float(match.group(3)),
            "jitter_ms": float(match.group(4)),
            "packet_loss_pct": int(loss_match.group(1)) if loss_match else None
        }
    return None

def parse_iperf_log(filepath):
    with open(filepath) as f:
        content = f.read()
    match = re.search(r"([\d.]+) Mbits/sec\s+receiver", content)
    if match:
        return float(match.group(1))
    return None

print("=" * 60)
print("BASELINE vs OPTIMIZED — COMPARISON REPORT")
print("=" * 60)

baseline_lat = parse_ping_log("baseline_latency.log")
optimized_lat = parse_ping_log("optimized_latency.log")
baseline_bw = parse_iperf_log("baseline_bulk.log")
optimized_bw = parse_iperf_log("optimized_bulk.log")

print(f"\n{'Metric':<25} {'Baseline':<15} {'Optimized':<15} {'Improvement'}")
print("-" * 70)

if baseline_lat and optimized_lat:
    print(f"{'Avg Latency (ms)':<25} {baseline_lat['avg_ms']:<15} {optimized_lat['avg_ms']:<15} "
          f"{round((baseline_lat['avg_ms']-optimized_lat['avg_ms'])/baseline_lat['avg_ms']*100,1)}% lower")
    print(f"{'Jitter (ms)':<25} {baseline_lat['jitter_ms']:<15} {optimized_lat['jitter_ms']:<15} "
          f"{round((baseline_lat['jitter_ms']-optimized_lat['jitter_ms'])/baseline_lat['jitter_ms']*100,1)}% lower")
    print(f"{'Packet Loss (%)':<25} {baseline_lat['packet_loss_pct']:<15} {optimized_lat['packet_loss_pct']:<15}")

if baseline_bw and optimized_bw:
    print(f"{'Bulk Throughput (Mbps)':<25} {baseline_bw:<15} {optimized_bw:<15}")

print("\n" + "=" * 60)
