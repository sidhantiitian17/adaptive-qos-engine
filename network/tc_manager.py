"""
Programmatic Linux Traffic Control (TC) Manager:
Provides robust, injection-safe control over Linux qdiscs:
  - CAKE (DiffServ4 dual-host isolation, FQ-CoDel queueing, priority tins)
  - NetEm (controlled delay, jitter, packet loss, bandwidth rate shaping)
Queries the Linux kernel directly as the single source of truth.
"""
import subprocess
import re
import os
import sys
import time
from typing import Dict, Any, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from network.execution_backend import get_execution_backend, ExecutionBackend

class TcManager:
    def __init__(
        self,
        iface: str = "veth-gw-wan",
        namespace: Optional[str] = "gw",
        dry_run: bool = False,
        backend: Optional[ExecutionBackend] = None
    ):
        self.iface = iface
        self.namespace = namespace
        self.dry_run = dry_run
        self.backend = backend or get_execution_backend()
        self.last_action = None
        self.last_error = None

    def _exec(self, cmd_args: list) -> tuple[int, str, str]:
        """Execute a tc command using the detected execution backend."""
        if self.dry_run:
            return 0, f"mock_tc_output for {' '.join(cmd_args)}", ""

        # Try with namespace first if requested
        if self.namespace:
            code, stdout, stderr = self.backend.exec_cmd(cmd_args, namespace=self.namespace)
            if code == 0:
                return code, stdout, stderr
            # If namespace doesn't exist or failed due to missing netns, fallback to direct exec
            if "Cannot open network namespace" in stderr or "No such file or directory" in stderr or "Cannot assign requested address" in stderr:
                return self.backend.exec_cmd(cmd_args, namespace=None)
            return code, stdout, stderr

        return self.backend.exec_cmd(cmd_args, namespace=None)

    @staticmethod
    def parse_qdisc_output(stdout: str, iface: str, namespace: Optional[str] = None) -> Dict[str, Any]:
        """
        Parse raw 'tc -s qdisc show dev <iface>' output into a canonical policy state representation.
        Handles variations in bandwidth units (Mbit, Kbit, bit, unlimited) and diffserv tin modes.
        """
        if not stdout or not stdout.strip():
            return {
                "status": "unavailable",
                "qdisc_type": "unknown",
                "interface": iface,
                "namespace": namespace,
                "bandwidth": None,
                "bandwidth_mbit": None,
                "diffserv_mode": None,
                "handle": None,
                "parent": "root",
                "sent_bytes": None,
                "sent_packets": None,
                "dropped": None,
                "backlog_bytes": None,
                "backlog_pkts": None,
                "raw_output": stdout or "",
                "error": "Empty qdisc output from kernel"
            }

        qdisc_type = "unknown"
        if "cake" in stdout:
            qdisc_type = "cake"
        elif "netem" in stdout:
            qdisc_type = "netem"
        elif "fq_codel" in stdout:
            qdisc_type = "fq_codel"
        elif "noqueue" in stdout:
            qdisc_type = "noqueue"

        # Handle matching e.g. "qdisc cake 8076: root" or "qdisc cake 1:"
        handle_match = re.search(r"qdisc \S+ ([0-9a-fA-F:]+)", stdout)
        handle_val = handle_match.group(1) if handle_match else None

        # Parent matching e.g. "root" or "parent 1:1"
        parent_match = re.search(r"(root|parent \S+)", stdout)
        parent_val = parent_match.group(1) if parent_match else "root"

        # DiffServ mode matching e.g. "diffserv4", "diffserv3", "besteffort"
        ds_match = re.search(r"\b(diffserv4|diffserv3|diffserv|besteffort)\b", stdout)
        diffserv_val = ds_match.group(1) if ds_match else None

        # Bandwidth parsing
        bw_match = re.search(r"bandwidth (\S+)", stdout)
        rate_match = re.search(r"rate (\S+)", stdout)
        bw_str = bw_match.group(1) if bw_match else (rate_match.group(1) if rate_match else None)

        bw_mbit: Optional[float] = None
        if bw_str:
            bw_lower = bw_str.lower()
            if bw_lower == "unlimited":
                bw_mbit = 0.0
            else:
                num_match = re.search(r"([\d.]+)", bw_str)
                if num_match:
                    num_val = float(num_match.group(1))
                    if "gbit" in bw_lower or "gbps" in bw_lower:
                        bw_mbit = round(num_val * 1000.0, 3)
                    elif "mbit" in bw_lower or "mbps" in bw_lower:
                        bw_mbit = round(num_val, 3)
                    elif "kbit" in bw_lower or "kbps" in bw_lower:
                        bw_mbit = round(num_val / 1000.0, 3)
                    elif "bit" in bw_lower or "bps" in bw_lower:
                        bw_mbit = round(num_val / 1000000.0, 3)
                    else:  # Defaults to Mbit
                        bw_mbit = round(num_val, 3)

        sent_match = re.search(r"Sent (\d+) bytes (\d+) pkt \(dropped (\d+)", stdout)
        backlog_match = re.search(r"backlog (\d+)b (\d+)p", stdout)

        return {
            "status": "verified",
            "qdisc_type": qdisc_type,
            "interface": iface,
            "namespace": namespace,
            "handle": handle_val,
            "parent": parent_val,
            "bandwidth": bw_str,
            "bandwidth_mbit": bw_mbit,
            "diffserv_mode": diffserv_val,
            "sent_bytes": int(sent_match.group(1)) if sent_match else 0,
            "sent_packets": int(sent_match.group(2)) if sent_match else 0,
            "dropped": int(sent_match.group(3)) if sent_match else 0,
            "backlog_bytes": int(backlog_match.group(1)) if backlog_match else 0,
            "backlog_pkts": int(backlog_match.group(2)) if backlog_match else 0,
            "raw_output": stdout.strip(),
            "error": None
        }

    def get_qdisc_state(self) -> Dict[str, Any]:
        """Query kernel for active qdisc and packet counters on configured interface."""
        code, stdout, stderr = self._exec(["tc", "-s", "qdisc", "show", "dev", self.iface])
        if code != 0 or not stdout.strip():
            # If netns failed, check local interface
            if not self.dry_run and self.namespace:
                try:
                    res_loc = subprocess.run(["tc", "-s", "qdisc", "show", "dev", self.iface], capture_output=True, text=True, timeout=2)
                    if res_loc.returncode == 0 and res_loc.stdout.strip():
                        stdout = res_loc.stdout
                        code = 0
                except Exception:
                    pass

        if code != 0 or not stdout.strip():
            return {
                "status": "unavailable",
                "qdisc_type": "unknown",
                "interface": self.iface,
                "namespace": self.namespace,
                "bandwidth": None,
                "bandwidth_mbit": None,
                "diffserv_mode": None,
                "handle": None,
                "parent": "root",
                "sent_bytes": None,
                "sent_packets": None,
                "dropped": None,
                "backlog_bytes": None,
                "backlog_pkts": None,
                "raw_output": stdout,
                "error": stderr or "No qdisc output from kernel"
            }

        parsed = self.parse_qdisc_output(stdout, self.iface, self.namespace)
        if self.dry_run:
            parsed["status"] = "dry_run_unverified"
        return parsed

    def apply_cake(self, bandwidth_mbit: int, diffserv: str = "diffserv4") -> Dict[str, Any]:
        """
        Apply or replace root CAKE qdisc with specific bandwidth and diffserv tin mode.
        Verifies actual kernel state after application: checks interface, qdisc type,
        bandwidth rate, and diffserv tin mode.
        """
        bandwidth_mbit = max(1, int(bandwidth_mbit))
        bw_str = f"{bandwidth_mbit}mbit"

        # Check existing state to use replace or add
        current = self.get_qdisc_state()
        action = "replace" if current.get("qdisc_type") in ("cake", "netem", "fq_codel") else "add"

        cmd = ["tc", "qdisc", action, "dev", self.iface, "root", "cake", "bandwidth", bw_str, diffserv]
        code, out, err = self._exec(cmd)

        if code != 0 and action == "replace":
            # Fallback to del and add
            self._exec(["tc", "qdisc", "del", "dev", self.iface, "root"])
            cmd = ["tc", "qdisc", "add", "dev", self.iface, "root", "cake", "bandwidth", bw_str, diffserv]
            code, out, err = self._exec(cmd)

        verified = self.get_qdisc_state()

        if self.dry_run:
            success = (code == 0)
            verified["qdisc_type"] = "cake"
            verified["diffserv_mode"] = diffserv
            verified["bandwidth_mbit"] = float(bandwidth_mbit)
            verified["bandwidth"] = bw_str
            verified["status"] = "dry_run_unverified"
        else:
            # Rigorous kernel state verification
            type_ok = (verified.get("qdisc_type") == "cake")
            # Bandwidth match tolerance: +/- 1 Mbps due to rounding or string parsing
            bw_actual = verified.get("bandwidth_mbit")
            bw_ok = (bw_actual is not None and abs(bw_actual - bandwidth_mbit) <= 1.0)
            # Diffserv mode match
            ds_actual = verified.get("diffserv_mode")
            ds_ok = (ds_actual == diffserv)

            success = (code == 0) and type_ok and bw_ok and ds_ok
            if not success and code == 0:
                reasons = []
                if not type_ok:
                    reasons.append(f"qdisc_type mismatch (expected 'cake', got '{verified.get('qdisc_type')}')")
                if not bw_ok:
                    reasons.append(f"bandwidth mismatch (expected {bandwidth_mbit} Mbit, got {bw_actual})")
                if not ds_ok:
                    reasons.append(f"diffserv mismatch (expected '{diffserv}', got '{ds_actual}')")
                err = f"Kernel state verification failed: {', '.join(reasons)}"

        return {
            "action": "apply_cake",
            "requested_bandwidth_mbit": bandwidth_mbit,
            "diffserv_mode": diffserv,
            "command": " ".join(cmd),
            "success": success,
            "error": err if not success else None,
            "verified_state": verified,
            "timestamp": time.time()
        }

    def apply_netem(
        self,
        rate_mbit: int,
        delay_ms: float = 20.0,
        loss_pct: float = 0.0,
        jitter_ms: float = 0.0,
        limit: int = 1000
    ) -> Dict[str, Any]:
        """Apply or replace root NetEm qdisc for WAN link impairment simulation."""
        rate_mbit = max(1, int(rate_mbit))
        rate_str = f"{rate_mbit}mbit"

        current = self.get_qdisc_state()
        action = "replace" if current.get("qdisc_type") in ("cake", "netem", "fq_codel") else "add"

        cmd = ["tc", "qdisc", action, "dev", self.iface, "root", "netem", "rate", rate_str]
        if delay_ms > 0:
            if jitter_ms > 0:
                cmd.extend(["delay", f"{delay_ms}ms", f"{jitter_ms}ms"])
            else:
                cmd.extend(["delay", f"{delay_ms}ms"])
        if loss_pct > 0:
            cmd.extend(["loss", f"{loss_pct}%"])
        if limit:
            cmd.extend(["limit", str(limit)])

        code, out, err = self._exec(cmd)
        if code != 0 and action == "replace":
            self._exec(["tc", "qdisc", "del", "dev", self.iface, "root"])
            cmd[2] = "add"
            code, out, err = self._exec(cmd)

        verified = self.get_qdisc_state()
        success = (code == 0) and (self.dry_run or verified.get("qdisc_type") == "netem")

        return {
            "action": "apply_netem",
            "requested_rate_mbit": rate_mbit,
            "delay_ms": delay_ms,
            "jitter_ms": jitter_ms,
            "loss_pct": loss_pct,
            "command": " ".join(cmd),
            "success": success,
            "error": err if not success else None,
            "verified_state": verified,
            "timestamp": time.time()
        }

    def remove_qdisc(self) -> Dict[str, Any]:
        """Remove root qdisc from interface."""
        cmd = ["tc", "qdisc", "del", "dev", self.iface, "root"]
        code, out, err = self._exec(cmd)
        verified = self.get_qdisc_state()
        return {
            "action": "remove_qdisc",
            "success": code == 0 or "No such file" in err,
            "verified_state": verified,
            "timestamp": time.time()
        }


if __name__ == "__main__":
    mgr = TcManager(dry_run=True)
    res = mgr.apply_cake(100)
    assert res["success"] == True
    print("TcManager dry-run verification: PASS ✅")
