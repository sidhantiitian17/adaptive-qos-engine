"""
Real Packet Traffic Generator:
Generates real UDP/TCP socket traffic across client, gateway, and upstream server nodes.
Supports the 7 required broadband traffic profiles with realistic packet sizing,
inter-arrival cadences, and DiffServ TOS marking. Payloads are generated with random bytes;
packet headers are sniffed and classified without inspecting application payloads.
"""
import socket
import time
import threading
import os
import random
from typing import Dict, Any, Optional

TRAFFIC_PROFILES = {
    "VIDEO_CONFERENCE": {
        "proto": "udp",
        "packet_size": 200,      # Small UDP payload representing RTP media stream
        "target_rate_mbps": 1.2, # ~1.2 Mbps typical 720p/1080p WebRTC/Zoom video
        "tos": 0x88,             # AF41 (0x22 << 2) -> CAKE Video tin
        "port": 5000,
        "dscp": "AF41"
    },
    "GAMING": {
        "proto": "udp",
        "packet_size": 64,       # Small UDP updates representing game-state ticks
        "target_rate_mbps": 0.2, # ~200 Kbps tick updates
        "tos": 0xB8,             # EF (0x2E << 2) -> CAKE Voice/Interactive tin
        "port": 9001,
        "dscp": "EF"
    },
    "VOICE": {
        "proto": "udp",
        "packet_size": 160,      # G.711 / Opus voice frames
        "target_rate_mbps": 0.08,# ~80 Kbps VoIP
        "tos": 0xB8,             # EF (0x2E << 2) -> CAKE Voice tin
        "port": 5060,
        "dscp": "EF"
    },
    "ADAPTIVE_VIDEO": {
        "proto": "tcp",
        "packet_size": 1400,     # Segmented MPEG-DASH / HLS chunks
        "target_rate_mbps": 5.0, # ~5.0 Mbps HD streaming
        "tos": 0x88,             # AF41 -> CAKE Video tin
        "port": 8081,
        "dscp": "AF41"
    },
    "BULK_DOWNLOAD": {
        "proto": "tcp",
        "packet_size": 1460,     # MTU-sized saturated bulk download (ISO, Game patch)
        "target_rate_mbps": 50.0,# Attempts link saturation
        "tos": 0x20,             # CS1 (0x08 << 2) -> CAKE Bulk tin
        "port": 5201,
        "dscp": "CS1"
    },
    "SOFTWARE_UPDATE": {
        "proto": "tcp",
        "packet_size": 1400,     # OS updates in background
        "target_rate_mbps": 15.0,# Burst download
        "tos": 0x20,             # CS1 -> CAKE Bulk tin
        "port": 8082,
        "dscp": "CS1"
    },
    "CLOUD_BACKUP": {
        "proto": "tcp",
        "packet_size": 1440,     # Sustained background upload
        "target_rate_mbps": 10.0,# Sustained rate
        "tos": 0x20,             # CS1 -> CAKE Bulk tin
        "port": 8083,
        "dscp": "CS1"
    }
}

class TrafficReceiver:
    """Lightweight UDP/TCP socket receiver tracking real packet arrivals and bytes."""
    def __init__(self, host: str = "0.0.0.0", port: int = 5000, proto: str = "udp"):
        self.host = host
        self.port = port
        self.proto = proto.lower()
        self.running = False
        self.packets_received = 0
        self.bytes_received = 0
        self.first_packet_time = None
        self.last_packet_time = None
        self._sock = None
        self._thread = None

    def start(self):
        self.running = True
        if self.proto == "udp":
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind((self.host, self.port))
            self._sock.settimeout(0.5)
            self._thread = threading.Thread(target=self._udp_listen, daemon=True)
        else:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind((self.host, self.port))
            self._sock.listen(5)
            self._sock.settimeout(0.5)
            self._thread = threading.Thread(target=self._tcp_listen, daemon=True)
        self._thread.start()

    def _udp_listen(self):
        while self.running:
            try:
                data, _ = self._sock.recvfrom(65535)
                now = time.time()
                self.packets_received += 1
                self.bytes_received += len(data)
                if not self.first_packet_time:
                    self.first_packet_time = now
                self.last_packet_time = now
            except socket.timeout:
                continue
            except Exception:
                break

    def _tcp_listen(self):
        while self.running:
            try:
                conn, _ = self._sock.accept()
                conn.settimeout(1.0)
                while self.running:
                    try:
                        data = conn.recv(65535)
                        if not data:
                            break
                        now = time.time()
                        self.packets_received += 1
                        self.bytes_received += len(data)
                        if not self.first_packet_time:
                            self.first_packet_time = now
                        self.last_packet_time = now
                    except socket.timeout:
                        continue
                    except Exception:
                        break
                conn.close()
            except socket.timeout:
                continue
            except Exception:
                break

    def stop(self):
        self.running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def get_stats(self) -> Dict[str, Any]:
        dt = (self.last_packet_time - self.first_packet_time) if (self.first_packet_time and self.last_packet_time and self.last_packet_time > self.first_packet_time) else 1.0
        achieved_mbps = round((self.bytes_received * 8.0) / (dt * 1e6), 3) if dt > 0 else 0.0
        return {
            "packets_received": self.packets_received,
            "bytes_received": self.bytes_received,
            "duration_sec": round(dt, 2),
            "achieved_mbps": achieved_mbps
        }


class RealTrafficGenerator:
    """Generates actual packet traffic with configurable rates, sizes, and DiffServ DSCP."""
    def __init__(self, target_ip: str = "127.0.0.1"):
        self.target_ip = target_ip

    def run_flow(
        self,
        profile_name: str,
        duration_sec: float = 5.0,
        target_port: Optional[int] = None,
        source_bind_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        profile = TRAFFIC_PROFILES.get(profile_name.upper(), TRAFFIC_PROFILES["VIDEO_CONFERENCE"])
        proto = profile["proto"]
        pkt_size = profile["packet_size"]
        target_rate = profile["target_rate_mbps"]
        port = target_port or profile["port"]
        tos_val = profile["tos"]

        # Payload initialization
        payload = b"QOS" + os.urandom(max(0, pkt_size - 3))

        start_time = time.time()
        end_time = start_time + duration_sec
        packets_sent = 0
        bytes_sent = 0

        # Calculate pacing interval
        bytes_per_sec = (target_rate * 1e6) / 8.0
        packets_per_sec = max(1.0, bytes_per_sec / pkt_size)
        interval = 1.0 / packets_per_sec

        src_port = 0
        if proto == "udp":
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, tos_val)
            except Exception:
                pass
            if source_bind_ip:
                try:
                    sock.bind((source_bind_ip, 0))
                except Exception:
                    pass
            src_port = sock.getsockname()[1] if sock.getsockname() else 0

            next_send = time.time()
            while time.time() < end_time:
                try:
                    sock.sendto(payload, (self.target_ip, port))
                    packets_sent += 1
                    bytes_sent += len(payload)
                except Exception:
                    break
                next_send += interval
                sleep_time = next_send - time.time()
                if sleep_time > 0:
                    time.sleep(min(sleep_time, 0.05))
            sock.close()

        else: # tcp
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, tos_val)
            except Exception:
                pass
            if source_bind_ip:
                try:
                    sock.bind((source_bind_ip, 0))
                except Exception:
                    pass
            try:
                sock.connect((self.target_ip, port))
                src_port = sock.getsockname()[1]
                next_send = time.time()
                while time.time() < end_time:
                    sock.sendall(payload)
                    packets_sent += 1
                    bytes_sent += len(payload)
                    next_send += interval
                    sleep_time = next_send - time.time()
                    if sleep_time > 0:
                        time.sleep(min(sleep_time, 0.05))
            except Exception:
                pass
            finally:
                sock.close()

        actual_duration = max(0.1, time.time() - start_time)
        actual_mbps = round((bytes_sent * 8.0) / (actual_duration * 1e6), 3)

        flow_id = f"{source_bind_ip or '127.0.0.1'}:{src_port}->{self.target_ip}:{port}/{proto}"

        return {
            "flow_id": flow_id,
            "profile": profile_name.upper(),
            "protocol": proto,
            "target_ip": self.target_ip,
            "target_port": port,
            "source_port": src_port,
            "configured_rate_mbps": target_rate,
            "actual_rate_mbps": actual_mbps,
            "packets_sent": packets_sent,
            "bytes_sent": bytes_sent,
            "duration_sec": round(actual_duration, 2),
            "dscp_marked": profile.get("dscp"),
            "start_time": start_time,
            "end_time": time.time()
        }


if __name__ == "__main__":
    print("Testing RealTrafficGenerator with local receiver...")
    rx = TrafficReceiver(port=5999, proto="udp")
    rx.start()

    tx = RealTrafficGenerator(target_ip="127.0.0.1")
    tx_stats = tx.run_flow("GAMING", duration_sec=1.0, target_port=5999)
    time.sleep(0.2)
    rx.stop()
    rx_stats = rx.get_stats()

    print("TX Stats:", tx_stats)
    print("RX Stats:", rx_stats)
    assert tx_stats["packets_sent"] > 0
    assert rx_stats["packets_received"] > 0
    print("RealTrafficGenerator verification: PASS ✅")
