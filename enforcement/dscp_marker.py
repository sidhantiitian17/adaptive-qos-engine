"""
DSCP Packet Marking Engine using Linux iptables/ip6tables.
Maps classified traffic flows to standard DiffServ codepoints:
  - gaming           -> EF (0x2E)   -> CAKE Voice/Interactive Tin (Tin 3)
  - video_conference -> AF41 (0x22) -> CAKE Video Tin (Tin 2)
  - bulk_download    -> CS1 (0x08)  -> CAKE Bulk Tin (Tin 0)
  - default/other    -> CS0 (0x00)  -> CAKE Best Effort Tin (Tin 1)

Supports genuine per-flow 5-tuple packet marking with IPv4 and IPv6 dual-stack support.
Host-wide marking is preserved strictly as a backwards-compatible fallback.
"""
import os
import sys
import subprocess
import threading
from typing import Dict, Any, List, Optional, Union

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from classifier.flow_tuple import FlowTuple
from policy_engine.traffic_classes import get_dscp_for_class, normalize_class_name, CLASS_SPECS

CHAIN_NAME = "QOS_MARKING"

# Backwards compatibility export
CLASS_TO_DSCP = {
    "video_conference": {"name": "AF41", "val": "0x22"},
    "gaming":           {"name": "EF",   "val": "0x2E"},
    "bulk_download":    {"name": "CS1",  "val": "0x08"},
    "unclassified":     {"name": "CS0",  "val": "0x00"},
    "default":          {"name": "CS0",  "val": "0x00"},
}


class DscpMarker:
    """
    Thread-safe Linux DSCP packet marking controller.
    Applies flow-specific (5-tuple) and host-wide DiffServ markings via netfilter mangle tables.
    """
    def __init__(self, namespace: str = "gw", dry_run: bool = False):
        self._lock = threading.Lock()
        self.namespace = namespace
        self.dry_run = dry_run
        self.mock_rules: List[Dict[str, Any]] = []
        self._flow_rules: Dict[str, Dict[str, Any]] = {}
        self._host_rules: Dict[str, Dict[str, Any]] = {}

        if not self.dry_run:
            if os.geteuid() != 0:
                check = subprocess.run(["sudo", "-n", "true"], capture_output=True)
                if check.returncode != 0:
                    self.dry_run = True
            if not self.dry_run:
                self._init_chains()

    def _exec(self, cmd_list: List[str]):
        """Execute command in netns with non-blocking sudo or log if dry-run."""
        if self.dry_run:
            return 0, "", ""
        full_cmd = ["sudo", "-n", "ip", "netns", "exec", self.namespace] + cmd_list
        try:
            res = subprocess.run(full_cmd, capture_output=True, text=True)
            return res.returncode, res.stdout, res.stderr
        except Exception as e:
            return 1, "", str(e)

    def _init_chains(self):
        """Initialize dedicated QoS mangle chains for IPv4 and IPv6."""
        for tool in ["iptables", "ip6tables"]:
            code, out, _ = self._exec([tool, "-t", "mangle", "-L", CHAIN_NAME, "-n"])
            if code != 0:
                self._exec([tool, "-t", "mangle", "-N", CHAIN_NAME])
                self._exec([tool, "-t", "mangle", "-I", "PREROUTING", "-j", CHAIN_NAME])

    def mark_flow(
        self,
        flow_or_src: Union[FlowTuple, str],
        *args,
        traffic_class: str = "default",
        **kwargs
    ) -> bool:
        """
        Mark specific 5-tuple flow with appropriate DSCP.
        Supports:
          mark_flow(flow_tuple, traffic_class="gaming")
          mark_flow(src_ip, dst_ip, sport, dport, proto, traffic_class)
          mark_flow(src_ip, proto, sport, dport, traffic_class)  # legacy signature
        """
        with self._lock:
            # 1. Resolve FlowTuple
            if isinstance(flow_or_src, FlowTuple):
                flow = flow_or_src
                target_class = kwargs.get("traffic_class", traffic_class)
                if args:
                    target_class = args[0]
            elif isinstance(flow_or_src, str):
                if len(args) == 5:
                    # (src_ip, dst_ip, sport, dport, proto, class)
                    dst_ip, sport, dport, proto, target_class = args
                    flow = FlowTuple.create(flow_or_src, dst_ip, int(sport), int(dport), proto)
                elif len(args) == 4:
                    # legacy: (src_ip, proto, sport, dport, class)
                    proto, sport, dport, target_class = args
                    # dummy / wildcard destination
                    dst_ip = "::1" if ":" in flow_or_src else "10.0.3.2"
                    flow = FlowTuple.create(flow_or_src, dst_ip, int(sport), int(dport), proto)
                elif "->" in flow_or_src:
                    flow = FlowTuple.from_string(flow_or_src)
                    target_class = args[0] if args else traffic_class
                else:
                    raise ValueError(f"Insufficient arguments to construct FlowTuple from '{flow_or_src}'")
            else:
                raise TypeError(f"Invalid flow specification type: {type(flow_or_src)}")

            # Normalize class
            canonical_class = normalize_class_name(target_class)
            dscp_info = get_dscp_for_class(canonical_class)
            flow_key = flow.to_string()

            # 2. If a rule already exists for this exact flow, clear it first
            if flow_key in self._flow_rules:
                self._delete_flow_rule_locked(self._flow_rules[flow_key])

            # 3. Build netfilter command
            tool = "ip6tables" if flow.is_ipv6() else "iptables"
            cmd = [tool, "-t", "mangle", "-A", CHAIN_NAME, "-s", flow.src_ip]
            if flow.dst_ip and flow.dst_ip not in ("0.0.0.0", "::"):
                cmd.extend(["-d", flow.dst_ip])
            cmd.extend(["-p", flow.proto.lower()])

            # Ports only valid for protocols like tcp, udp, sctp, dccp
            if flow.proto.lower() in ("tcp", "udp", "sctp", "dccp"):
                if flow.sport > 0:
                    cmd.extend(["--sport", str(flow.sport)])
                if flow.dport > 0:
                    cmd.extend(["--dport", str(flow.dport)])

            cmd.extend(["-j", "DSCP", "--set-dscp-class", dscp_info["name"]])

            rule_entry = {
                "rule_type": "flow",
                "flow_id": flow_key,
                "flow_tuple": flow,
                "src_ip": flow.src_ip,
                "dst_ip": flow.dst_ip,
                "proto": flow.proto,
                "sport": flow.sport,
                "dport": flow.dport,
                "class": canonical_class,
                "dscp": dscp_info["name"],
                "dscp_hex": dscp_info["val"],
                "tool": tool,
                "cmd": cmd
            }

            self._flow_rules[flow_key] = rule_entry
            self._sync_mock_rules_locked()

            if self.dry_run:
                return True

            code, out, err = self._exec(cmd)
            if code != 0:
                print(f"[DSCP_MARKER] Failed to install flow rule for {flow_key}: {err.strip()}")
                return False
            return True

    def clear_flow(self, flow_or_id: Union[FlowTuple, str]) -> bool:
        """Remove marking rule for a specific 5-tuple flow."""
        with self._lock:
            flow_key = flow_or_id.to_string() if isinstance(flow_or_id, FlowTuple) else str(flow_or_id)
            if flow_key in self._flow_rules:
                rule = self._flow_rules.pop(flow_key)
                self._sync_mock_rules_locked()
                return self._delete_flow_rule_locked(rule)
            return True

    def _delete_flow_rule_locked(self, rule: Dict[str, Any]) -> bool:
        """Execute netfilter deletion for a specific flow rule."""
        if self.dry_run:
            return True
        cmd = list(rule["cmd"])
        # Replace -A with -D
        try:
            a_idx = cmd.index("-A")
            cmd[a_idx] = "-D"
            code, _, _ = self._exec(cmd)
            return code == 0
        except Exception:
            return False

    def mark_host(self, ip_address: str, traffic_class: str) -> bool:
        """
        [FALLBACK] Mark all packets from a specific host IP with appropriate DSCP.
        Preserved strictly for backwards compatibility when a 5-tuple cannot be formed.
        Does NOT alter distinct per-flow rules for other flows on this host.
        """
        with self._lock:
            canonical_class = normalize_class_name(traffic_class)
            dscp_info = get_dscp_for_class(canonical_class)
            tool = "ip6tables" if ":" in ip_address else "iptables"

            # Clear any previous host-wide rule for this IP
            self._clear_host_rule_locked(ip_address)

            cmd = [tool, "-t", "mangle", "-A", CHAIN_NAME, "-s", ip_address,
                   "-j", "DSCP", "--set-dscp-class", dscp_info["name"]]

            rule_entry = {
                "rule_type": "host",
                "ip": ip_address,
                "src_ip": ip_address,
                "class": canonical_class,
                "dscp": dscp_info["name"],
                "dscp_hex": dscp_info["val"],
                "tool": tool,
                "cmd": cmd
            }

            self._host_rules[ip_address] = rule_entry
            self._sync_mock_rules_locked()

            if self.dry_run:
                return True

            code, out, err = self._exec(cmd)
            return code == 0

    def _clear_host_rule_locked(self, ip_address: str):
        if ip_address in self._host_rules:
            rule = self._host_rules.pop(ip_address)
            if not self.dry_run:
                cmd = list(rule["cmd"])
                try:
                    a_idx = cmd.index("-A")
                    cmd[a_idx] = "-D"
                    self._exec(cmd)
                except Exception:
                    pass
            self._sync_mock_rules_locked()

    def clear_host(self, ip_address: str):
        """Remove host-wide marking rules for a given IP."""
        with self._lock:
            self._clear_host_rule_locked(ip_address)

    def _sync_mock_rules_locked(self):
        """Keep self.mock_rules synchronized for introspection and testing."""
        all_rules = []
        for r in self._host_rules.values():
            all_rules.append({
                "type": "host",
                "ip": r["ip"],
                "src_ip": r["src_ip"],
                "class": r["class"],
                "dscp": r["dscp"]
            })
        for r in self._flow_rules.values():
            all_rules.append({
                "type": "flow",
                "flow_id": r["flow_id"],
                "ip": r["src_ip"],
                "src_ip": r["src_ip"],
                "dst_ip": r["dst_ip"],
                "proto": r["proto"],
                "sport": r["sport"],
                "dport": r["dport"],
                "class": r["class"],
                "dscp": r["dscp"]
            })
        self.mock_rules = all_rules

    def clear_all(self):
        """Flush all QoS marking rules (both per-flow and host-wide)."""
        with self._lock:
            self._flow_rules.clear()
            self._host_rules.clear()
            self.mock_rules.clear()
            if self.dry_run:
                return
            for tool in ["iptables", "ip6tables"]:
                self._exec([tool, "-t", "mangle", "-F", CHAIN_NAME])

    def get_rules(self) -> List[Dict[str, Any]]:
        """Return list of active rules in the QOS_MARKING chain."""
        with self._lock:
            return [dict(r) for r in self.mock_rules]

    def get_flow_rule(self, flow_key: str) -> Optional[Dict[str, Any]]:
        """Query active rule for a specific flow."""
        with self._lock:
            rule = self._flow_rules.get(flow_key)
            return dict(rule) if rule else None
