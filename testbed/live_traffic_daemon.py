"""
Continuous Real Traffic Generator Daemon
Runs realistic multi-tin mixed broadband traffic (Gaming, Video, Bulk)
across namespaces lan1/lan2 -> gw -> wanhost so that real measurements
stream continuously into the Adaptive QoS Engine dashboard.
"""
import time
import socket
import threading
import sys
import os

WAN_IP = "10.0.3.2"

def udp_sink(port):
    """Simple UDP sink server running on wanhost."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))
        while True:
            data, _ = s.recvfrom(65535)
    except Exception:
        pass

def stream_udp(target_ip, port, tos, rate_mbps, packet_size, bind_ip=None):
    """Sends steady UDP packets with specific DiffServ TOS."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if bind_ip:
        s.bind((bind_ip, 0))
    s.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, tos)
    payload = b"X" * packet_size
    bytes_per_sec = (rate_mbps * 1e6) / 8.0
    packets_per_sec = max(1.0, bytes_per_sec / packet_size)
    interval = 1.0 / packets_per_sec

    while True:
        try:
            s.sendto(payload, (target_ip, port))
            time.sleep(interval)
        except Exception:
            time.sleep(0.5)

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "client"

    if mode == "server":
        # Run sinks on ports 5000, 9001, 5060
        t1 = threading.Thread(target=udp_sink, args=(5000,), daemon=True)
        t2 = threading.Thread(target=udp_sink, args=(9001,), daemon=True)
        t3 = threading.Thread(target=udp_sink, args=(5060,), daemon=True)
        t1.start()
        t2.start()
        t3.start()
        print("UDP sinks listening on 5000 (Video), 9001 (Gaming), 5060 (Voice)...")
        while True:
            time.sleep(1)

    elif mode == "client":
        # Gaming from lan2 (10.0.2.2) -> EF (0xB8)
        # Video from lan1 (10.0.1.2) -> AF41 (0x88)
        # Bulk from lan1 (10.0.1.2) -> CS1 (0x20)
        print("Starting traffic generator threads...")
        # 1. Gaming: 200 Kbps, 64-byte packets, EF
        tg_gaming = threading.Thread(
            target=stream_udp,
            args=(WAN_IP, 9001, 0xB8, 0.25, 64),
            daemon=True
        )
        # 2. Video Conference: 2.0 Mbps, 300-byte packets, AF41
        tg_video = threading.Thread(
            target=stream_udp,
            args=(WAN_IP, 5000, 0x88, 2.0, 300),
            daemon=True
        )
        # 3. Bulk traffic: 8.0 Mbps, 1400-byte packets, CS1
        tg_bulk = threading.Thread(
            target=stream_udp,
            args=(WAN_IP, 5000, 0x20, 8.0, 1400),
            daemon=True
        )

        tg_gaming.start()
        tg_video.start()
        tg_bulk.start()

        print("Traffic streams active: Gaming (EF, 250k), Video (AF41, 2M), Bulk (CS1, 8M).")
        while True:
            time.sleep(1)

if __name__ == "__main__":
    main()
