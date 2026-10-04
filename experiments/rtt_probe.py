"""
Real Two-Way UDP Echo RTT and Jitter Measurement Protocol:
Provides genuine, nanosecond-precision round-trip time (RTT) measurements
over real UDP sockets using an explicit echo protocol.

Constraint: Never uses one-way sendto() duration as latency.
Enforces:
  - Magic signature validation (b"AQE_PROBE\\x00")
  - Unique probe UUID and monotonic sequence numbering
  - Monotonic nanosecond timestamping (time.monotonic_ns())
  - Explicit echo server reflection
  - Consecutive RTT Mean Absolute Difference (MAD) deterministic jitter
"""
import os
import time
import uuid
import struct
import socket
import select
import threading
import statistics
from typing import Dict, Any, List, Optional, Tuple

MAGIC_HEADER = b"AQE_PROBE\x00"
HEADER_FMT = "!10s16sId"  # magic(10), uuid(16), seq(4), timestamp_ns(8)
HEADER_SIZE = struct.calcsize(HEADER_FMT)


class UdpEchoServer:
    """
    Dedicated UDP echo server that reflects valid AQE probe packets.
    Listens asynchronously on specified host and port.
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 5206):
        self.host = host
        self.port = port
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self.packets_reflected = 0

    def start(self):
        self._stop_event.clear()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.settimeout(0.2)

        def _worker():
            while not self._stop_event.is_set():
                try:
                    data, addr = self._sock.recvfrom(2048)
                    if data.startswith(MAGIC_HEADER):
                        # Reflect exact packet back to sender
                        self._sock.sendto(data, addr)
                        self.packets_reflected += 1
                except socket.timeout:
                    continue
                except Exception:
                    break

        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None


class UdpRttProber:
    """
    Client for dispatching UDP probes and measuring genuine 2-way RTT and jitter.
    """
    def __init__(self, bind_host: str = "0.0.0.0", bind_port: int = 0):
        self.bind_host = bind_host
        self.bind_port = bind_port

    @staticmethod
    def calculate_jitter(rtts: List[float]) -> Optional[float]:
        """
        Calculates RFC 3550 / deterministic consecutive RTT Mean Absolute Difference:
        Jitter = (1 / (N - 1)) * sum(|RTT_i - RTT_{i-1}|)
        """
        if len(rtts) < 2:
            return 0.0 if len(rtts) == 1 else None
        diffs = [abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))]
        return round(sum(diffs) / len(diffs), 4)

    def probe_once(
        self,
        target_host: str,
        target_port: int,
        seq: int = 1,
        timeout_sec: float = 0.5,
        dscp_tos: Optional[int] = None
    ) -> Optional[float]:
        """
        Sends a single UDP echo probe and returns round-trip time in milliseconds.
        Returns None if timed out or packet lost.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout_sec)
        if dscp_tos is not None:
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, dscp_tos)
            except Exception:
                pass

        try:
            probe_uuid = uuid.uuid4().bytes
            t0_ns = time.monotonic_ns()
            payload = struct.pack(HEADER_FMT, MAGIC_HEADER, probe_uuid, seq, float(t0_ns))

            sock.sendto(payload, (target_host, target_port))
            data, _ = sock.recvfrom(2048)
            t1_ns = time.monotonic_ns()

            if len(data) >= HEADER_SIZE:
                magic, rx_uuid, rx_seq, rx_t0 = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
                if magic == MAGIC_HEADER and rx_uuid == probe_uuid and rx_seq == seq:
                    rtt_ms = (t1_ns - t0_ns) / 1_000_000.0
                    return round(rtt_ms, 3)
            return None
        except socket.timeout:
            return None
        except Exception:
            return None
        finally:
            sock.close()

    def run_probe_train(
        self,
        target_host: str,
        target_port: int,
        count: int = 10,
        interval_sec: float = 0.1,
        timeout_sec: float = 0.5,
        dscp_tos: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Executes a sequence of UDP echo probes and computes comprehensive metrics.
        """
        rtts: List[float] = []
        lost = 0

        for seq in range(1, count + 1):
            rtt = self.probe_once(
                target_host=target_host,
                target_port=target_port,
                seq=seq,
                timeout_sec=timeout_sec,
                dscp_tos=dscp_tos
            )
            if rtt is not None:
                rtts.append(rtt)
            else:
                lost += 1

            if seq < count and interval_sec > 0:
                time.sleep(interval_sec)

        samples_recv = len(rtts)
        loss_pct = round((lost / count) * 100.0, 2) if count > 0 else 0.0

        if samples_recv == 0:
            return {
                "status": "timeout",
                "samples_sent": count,
                "samples_received": 0,
                "loss_pct": 100.0,
                "avg_rtt_ms": None,
                "min_rtt_ms": None,
                "max_rtt_ms": None,
                "median_rtt_ms": None,
                "jitter_ms": None,
                "jitter_method": "consecutive_rtt_mad",
                "raw_rtts": []
            }

        avg_rtt = round(sum(rtts) / samples_recv, 3)
        min_rtt = round(min(rtts), 3)
        max_rtt = round(max(rtts), 3)
        med_rtt = round(statistics.median(rtts), 3)
        jitter = self.calculate_jitter(rtts)

        return {
            "status": "success",
            "samples_sent": count,
            "samples_received": samples_recv,
            "loss_pct": loss_pct,
            "avg_rtt_ms": avg_rtt,
            "min_rtt_ms": min_rtt,
            "max_rtt_ms": max_rtt,
            "median_rtt_ms": med_rtt,
            "jitter_ms": jitter,
            "jitter_method": "consecutive_rtt_mad",
            "raw_rtts": rtts
        }


if __name__ == "__main__":
    print("Testing UdpEchoServer and UdpRttProber...")
    server = UdpEchoServer(host="127.0.0.1", port=5299)
    server.start()
    time.sleep(0.1)

    prober = UdpRttProber()
    res = prober.run_probe_train(target_host="127.0.0.1", target_port=5299, count=5, interval_sec=0.05)
    print("Prober result:", res)
    server.stop()

    assert res["status"] == "success"
    assert res["samples_received"] == 5
    assert res["avg_rtt_ms"] is not None
    assert res["jitter_ms"] is not None
    print("UdpEchoServer + UdpRttProber verification: PASS ✅")
