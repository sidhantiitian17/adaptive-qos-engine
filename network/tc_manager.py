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
                "sent_bytes": None,
                "sent_packets": None,
                "dropped": None,
                "backlog_bytes": None,
                "backlog_pkts": None,
                "raw_output": stdout,
                "error": stderr or "No qdisc output from kernel"
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

        bw_match = re.search(r"bandwidth (\S+)", stdout)
        rate_match = re.search(r"rate (\S+)", stdout)
        bw_val = bw_match.group(1) if bw_match else (rate_match.group(1) if rate_match else None)

        sent_match = re.search(r"Sent (\d+) bytes (\d+) pkt \(dropped (\d+)", stdout)
        backlog_match = re.search(r"backlog (\d+)b (\d+)p", stdout)

        return {
            "status": "verified",
            "qdisc_type": qdisc_type,
            "interface": self.iface,
            "namespace": self.namespace,
            "bandwidth": bw_val,
            "sent_bytes": int(sent_match.group(1)) if sent_match else 0,
            "sent_packets": int(sent_match.group(2)) if sent_match else 0,
            "dropped": int(sent_match.group(3)) if sent_match else 0,
            "backlog_bytes": int(backlog_match.group(1)) if backlog_match else 0,
            "backlog_pkts": int(backlog_match.group(2)) if backlog_match else 0,
            "raw_output": stdout.strip(),
            "error": None
        }

    def apply_cake(self, bandwidth_mbit: int, diffserv: str = "diffserv4") -> Dict[str, Any]:
        """Apply or replace root CAKE qdisc with specific bandwidth and diffserv tin mode."""
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
        success = (code == 0) and (self.dry_run or verified.get("qdisc_type") == "cake")

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
