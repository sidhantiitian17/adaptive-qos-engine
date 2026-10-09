"""
Typed 5-tuple flow identifier and normalization engine.
Represents: (source IP, destination IP, source port, destination port, transport protocol).
Supports both IPv4 and IPv6, direction inversion, validation, and safe string serialization.
"""
from dataclasses import dataclass
import ipaddress
import re
from typing import Optional


@dataclass(frozen=True)
class FlowTuple:
    src_ip: str
    dst_ip: str
    sport: int
    dport: int
    proto: str
    ip_version: int

    @classmethod
    def create(cls, src_ip: str, dst_ip: str, sport: int, dport: int, proto: str) -> "FlowTuple":
        """
        Create and validate a normalized FlowTuple.
        Raises ValueError if addresses, ports, or protocol are invalid or mismatched.
        """
        # Validate and normalize IP addresses
        clean_src = src_ip.strip("[]")
        clean_dst = dst_ip.strip("[]")

        try:
            src_addr = ipaddress.ip_address(clean_src)
        except ValueError as e:
            raise ValueError(f"Invalid source IP address '{src_ip}': {e}") from e

        try:
            dst_addr = ipaddress.ip_address(clean_dst)
        except ValueError as e:
            raise ValueError(f"Invalid destination IP address '{dst_ip}': {e}") from e

        if src_addr.version != dst_addr.version:
            raise ValueError(
                f"Address family mismatch: source {src_ip} is IPv{src_addr.version}, "
                f"destination {dst_ip} is IPv{dst_addr.version}"
            )

        # Validate ports
        if not (0 <= sport <= 65535):
            raise ValueError(f"Invalid source port {sport}: must be between 0 and 65535")
        if not (0 <= dport <= 65535):
            raise ValueError(f"Invalid destination port {dport}: must be between 0 and 65535")

        # Validate protocol
        clean_proto = str(proto).strip().lower()
        if not re.match(r"^[a-z0-9_-]+$", clean_proto):
            raise ValueError(f"Invalid transport protocol '{proto}'")

        return cls(
            src_ip=str(src_addr),
            dst_ip=str(dst_addr),
            sport=int(sport),
            dport=int(dport),
            proto=clean_proto,
            ip_version=src_addr.version
        )

    @classmethod
    def from_string(cls, flow_id: str) -> "FlowTuple":
        """
        Parse flow ID string in format:
        - IPv4: "10.0.1.2:5201->10.0.3.2:80/tcp"
        - IPv6: "[fd00:1::2]:5201->[fd00:3::2]:80/tcp" or "fd00:1::2:5201->fd00:3::2:80/tcp"
        """
        if not flow_id or "->" not in flow_id:
            raise ValueError(f"Malformed flow identifier '{flow_id}': missing '->'")

        left, right = flow_id.split("->", 1)

        # Parse protocol from right part
        if "/" in right:
            right_ep, proto = right.rsplit("/", 1)
        else:
            right_ep, proto = right, "ip"

        def _parse_endpoint(ep_str: str):
            ep_str = ep_str.strip()
            # Bracketed format [ip]:port
            if ep_str.startswith("[") and "]:" in ep_str:
                ip_part, port_part = ep_str[1:].split("]:", 1)
                return ip_part, int(port_part)
            # Standard rsplit on ':'
            if ":" in ep_str:
                ip_part, port_part = ep_str.rsplit(":", 1)
                try:
                    return ip_part, int(port_part)
                except ValueError:
                    # In case of bare IPv6 without port
                    return ep_str, 0
            return ep_str, 0

        src_ip, sport = _parse_endpoint(left)
        dst_ip, dport = _parse_endpoint(right_ep)

        return cls.create(src_ip, dst_ip, sport, dport, proto)

    @classmethod
    def parse_or_none(cls, flow_id: str) -> Optional["FlowTuple"]:
        """Safe parsing factory that returns None on invalid input."""
        try:
            return cls.from_string(flow_id)
        except Exception:
            return None

    def to_string(self) -> str:
        """Format canonical flow string."""
        if self.ip_version == 6:
            return f"[{self.src_ip}]:{self.sport}->[{self.dst_ip}]:{self.dport}/{self.proto}"
        return f"{self.src_ip}:{self.sport}->{self.dst_ip}:{self.dport}/{self.proto}"

    def reverse(self) -> "FlowTuple":
        """Return return-path / reverse direction tuple."""
        return FlowTuple(
            src_ip=self.dst_ip,
            dst_ip=self.src_ip,
            sport=self.dport,
            dport=self.sport,
            proto=self.proto,
            ip_version=self.ip_version
        )

    def is_ipv6(self) -> bool:
        return self.ip_version == 6

    def is_ipv4(self) -> bool:
        return self.ip_version == 4
