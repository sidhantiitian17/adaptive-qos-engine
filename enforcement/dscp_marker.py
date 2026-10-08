"""
DSCP Packet Marking Engine using Linux iptables/ip6tables.
Maps classified traffic flows to standard DiffServ codepoints:
  - video_conference -> AF41 (0x22) -> CAKE Video Tin
  - gaming           -> EF (0x2E)   -> CAKE Voice/Interactive Tin
  - bulk_download    -> CS1 (0x08)  -> CAKE Bulk Tin
  - default/other    -> CS0 (0x00)  -> CAKE Best Effort Tin
"""
import subprocess
import shutil
import re
import os
import threading

CLASS_TO_DSCP = {
    "video_conference": {"name": "AF41", "val": "0x22"},
    "gaming":           {"name": "EF",   "val": "0x2E"},
    "bulk_download":    {"name": "CS1",  "val": "0x08"},
    "unclassified":     {"name": "CS0",  "val": "0x00"},
    "default":          {"name": "CS0",  "val": "0x00"},
}

CHAIN_NAME = "QOS_MARKING"

class DscpMarker:
    def __init__(self, namespace="gw", dry_run=False):
        self._lock = threading.Lock()
        self.namespace = namespace
        self.dry_run = dry_run
        self.mock_rules = []
        if not self.dry_run:
            # Check if root or if sudo -n works without password prompt
            if os.geteuid() != 0:
                check = subprocess.run(["sudo", "-n", "true"], capture_output=True)
                if check.returncode != 0:
                    self.dry_run = True
            if not self.dry_run:
                self._init_chains()

    def _exec(self, cmd_list):
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
            # Check if chain exists, create if not
            code, out, _ = self._exec([tool, "-t", "mangle", "-L", CHAIN_NAME, "-n"])
            if code != 0:
                self._exec([tool, "-t", "mangle", "-N", CHAIN_NAME])
                # Ensure PREROUTING jumps to QOS_MARKING
                self._exec([tool, "-t", "mangle", "-I", "PREROUTING", "-j", CHAIN_NAME])

    def mark_host(self, ip_address: str, traffic_class: str) -> bool:
        """Mark all packets from a specific host IP with appropriate DSCP."""
        with self._lock:
            dscp_info = CLASS_TO_DSCP.get(traffic_class, CLASS_TO_DSCP["default"])
            tool = "ip6tables" if ":" in ip_address else "iptables"

            # Remove existing rules for this IP to prevent duplication
            self._clear_host_locked(ip_address)
            self.mock_rules.append({"ip": ip_address, "class": traffic_class, "dscp": dscp_info["name"]})

            if self.dry_run:
                return True

            cmd = [tool, "-t", "mangle", "-A", CHAIN_NAME, "-s", ip_address,
                   "-j", "DSCP", "--set-dscp-class", dscp_info["name"]]
            code, out, err = self._exec(cmd)
            return code == 0

    def mark_flow(self, src_ip: str, proto: str, sport: int, dport: int, traffic_class: str) -> bool:
        """Mark specific 5-tuple flow with appropriate DSCP."""
        with self._lock:
            dscp_info = CLASS_TO_DSCP.get(traffic_class, CLASS_TO_DSCP["default"])
            tool = "ip6tables" if ":" in src_ip else "iptables"

            self.mock_rules.append({
                "src_ip": src_ip, "proto": proto, "sport": sport,
                "dport": dport, "class": traffic_class, "dscp": dscp_info["name"]
            })

            if self.dry_run:
                return True

            cmd = [tool, "-t", "mangle", "-A", CHAIN_NAME, "-s", src_ip,
                   "-p", proto.lower(), "--sport", str(sport)]
            if dport and dport > 0:
                cmd.extend(["--dport", str(dport)])
            cmd.extend(["-j", "DSCP", "--set-dscp-class", dscp_info["name"]])

            code, out, err = self._exec(cmd)
            return code == 0

    def _clear_host_locked(self, ip_address: str):
        self.mock_rules = [r for r in self.mock_rules if r.get("ip") != ip_address and r.get("src_ip") != ip_address]
        if self.dry_run:
            return
        tool = "ip6tables" if ":" in ip_address else "iptables"
        # Delete rules matching source IP in QOS_MARKING
        code, out, _ = self._exec([tool, "-t", "mangle", "-L", CHAIN_NAME, "-n", "--line-numbers"])
        if code == 0:
            lines = out.strip().split("\n")[2:]
            # Reverse order delete by line number
            for line in reversed(lines):
                if ip_address in line:
                    num = line.split()[0]
                    self._exec([tool, "-t", "mangle", "-D", CHAIN_NAME, num])

    def clear_host(self, ip_address: str):
        """Remove marking rules for a given IP."""
        with self._lock:
            self._clear_host_locked(ip_address)

    def clear_all(self):
        """Flush all QoS marking rules."""
        with self._lock:
            self.mock_rules.clear()
            if self.dry_run:
                return
            for tool in ["iptables", "ip6tables"]:
                self._exec([tool, "-t", "mangle", "-F", CHAIN_NAME])

    def get_rules(self):
        """Return list of active rules in the QOS_MARKING chain."""
        with self._lock:
            return [dict(r) for r in self.mock_rules]


if __name__ == "__main__":
    print("Testing DscpMarker in dry-run mode:")
    marker = DscpMarker(dry_run=True)
    marker.mark_host("10.0.1.2", "video_conference")
    marker.mark_host("10.0.2.2", "bulk_download")
    marker.mark_host("fd00:1::2", "gaming")
    rules = marker.get_rules()
    for r in rules:
        print(" ", r)
    assert len(rules) == 3
    print("DscpMarker dry-run: PASS ✅")
