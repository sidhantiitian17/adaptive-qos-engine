"""
Synthetic traffic generators jo teen broad categories simulate karte hain:
- video_conference: chhote UDP packets, consistent rate, low jitter
- bulk_download: bade TCP packets, max-throughput, bursty
- gaming: bahut chhote UDP packets, low-rate, high-frequency
"""
import subprocess
import time
import random

def generate_video_conference(target_ip, duration=10, port=5202):
    """Chhote UDP packets, ~1 Mbps constant rate, jaisa video call hota hai"""
    cmd = [
        "iperf3", "-c", target_ip, "-p", str(port), "-u",
        "-b", "1M", "-l", "200",  # 200-byte packets (RTP-jaisa)
        "-t", str(duration)
    ]
    subprocess.run(cmd, capture_output=True)

def generate_bulk_download(target_ip, duration=10, port=5203):
    """Max-throughput TCP, bade packets"""
    cmd = [
        "iperf3", "-c", target_ip, "-p", str(port),
        "-t", str(duration)
    ]
    subprocess.run(cmd, capture_output=True)

def generate_gaming(target_ip, duration=10, port=5204):
    """Bahut chhote UDP packets, low-rate, high-frequency (jaisa game-state updates)"""
    cmd = [
        "iperf3", "-c", target_ip, "-p", str(port), "-u",
        "-b", "150K", "-l", "60",  # 60-byte packets, bahut chhoti
        "-t", str(duration)
    ]
    subprocess.run(cmd, capture_output=True)

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "10.0.3.2"
    traffic_type = sys.argv[2] if len(sys.argv) > 2 else "video"

    if traffic_type == "video":
        print("Generating video_conference traffic...")
        generate_video_conference(target)
    elif traffic_type == "bulk":
        print("Generating bulk_download traffic...")
        generate_bulk_download(target)
    elif traffic_type == "gaming":
        print("Generating gaming traffic...")
        generate_gaming(target)
