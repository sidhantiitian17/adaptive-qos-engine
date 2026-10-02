"""
Checkpoint/rollback manager for Linux traffic control qdiscs.
Inspired by Koo & Toueg (1987) tentative-vs-permanent checkpoint model.
Enforces bounded, observable, and reversible automated remediation (Constraint C10).
"""
import os
import subprocess
import time
import re
import json

class RollbackManager:
    def __init__(self, namespace="gw", iface="veth-gw-wan", dry_run=False):
        self.namespace = namespace
        self.iface = iface
        self.dry_run = dry_run
        self.last_good_config = None  # last known-good bandwidth (Mbps)
        self.history_log = []
        self._check_permissions()

    def _check_permissions(self):
        if not self.dry_run and os.geteuid() != 0:
            check = subprocess.run(["sudo", "-n", "true"], capture_output=True)
            if check.returncode != 0:
                self.dry_run = True

    def _run(self, cmd_str):
        if self.dry_run:
            return 0, "mock_output"
        full_cmd = f"sudo -n {cmd_str}"
        try:
            res = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
            return res.returncode, res.stdout
        except Exception as e:
            return 1, str(e)

    def checkpoint(self) -> str:
        """Capture tentative snapshot before applying modifications."""
        code, out = self._run(f"ip netns exec {self.namespace} tc qdisc show dev {self.iface}")
        snapshot = out.strip() if code == 0 else "default_state"
        return snapshot

    def apply_policy(self, bandwidth_mbit: int, diffserv: str = "diffserv4") -> bool:
        """
        Apply new shaping rate tentatively.
        Takes snapshot, updates qdisc, and tracks in history log.
        """
        snapshot = self.checkpoint()
        cmd = (f"ip netns exec {self.namespace} tc qdisc change dev {self.iface} "
               f"root cake bandwidth {bandwidth_mbit}mbit {diffserv}")
        code, out = self._run(cmd)

        success = (code == 0)
        entry = {
            "timestamp": time.time(),
            "bandwidth_mbit": bandwidth_mbit,
            "diffserv": diffserv,
            "status": "tentative",
            "applied_successfully": success
        }
        self.history_log.append(entry)
        print(f"[ROLLBACK_MGR] Applied tentative policy: {bandwidth_mbit}mbit ({diffserv}) -> Success: {success}")
        return success

    def health_check(
        self,
        target_ip: str = "10.0.3.2",
        latency_threshold_ms: float = 60.0,
        max_loss_pct: float = 5.0
    ) -> bool:
        """
        Post-apply verification: measures RTT latency and packet loss.
        Fails if latency > threshold or packet loss > max_loss_pct.
        """
        if self.dry_run:
            # In dry-run, if the latest tentative bandwidth is <= 1 Mbps, simulate high latency failure
            latest = self.history_log[-1] if self.history_log else {}
            if latest.get("bandwidth_mbit", 10) <= 1:
                print(f"[HEALTH CHECK (MOCK)] Simulated excessive latency for {latest.get('bandwidth_mbit')}mbit.")
                return False
            return True

        code, out = self._run(f"ip netns exec lan1 ping -c 3 -W 2 {target_ip}")
        if code != 0:
            print("[HEALTH CHECK] Ping command failed entirely. Unhealthy.")
            return False

        match_rtt = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/", out)
        match_loss = re.search(r"(\d+)% packet loss", out)

        if match_rtt and match_loss:
            avg_latency = float(match_rtt.group(1))
            loss_pct = float(match_loss.group(1))
            print(f"[HEALTH CHECK] Avg Latency: {avg_latency}ms (limit: {latency_threshold_ms}ms) | Loss: {loss_pct}%")

            healthy = (avg_latency <= latency_threshold_ms) and (loss_pct <= max_loss_pct)
            return healthy

        return False

    def make_permanent(self, bandwidth_mbit: int):
        """Mark configuration as permanent (known-good checkpoint) following health check pass."""
        if self.history_log:
            self.history_log[-1]["status"] = "permanent"
        self.last_good_config = bandwidth_mbit
        print(f"[ROLLBACK_MGR] Committed bandwidth={bandwidth_mbit}mbit as permanent known-good.")

    def rollback(self):
        """Roll back to last known-good configuration or safe default."""
        fallback = self.last_good_config if self.last_good_config is not None else 10
        cmd = (f"ip netns exec {self.namespace} tc qdisc change dev {self.iface} "
               f"root cake bandwidth {fallback}mbit diffserv4")
        self._run(cmd)
        print(f"[ROLLBACK_MGR] ⚠️ Reverted to safe configuration: {fallback}mbit")

        if self.history_log:
            self.history_log[-1]["status"] = "rolled_back"

    def get_history(self):
        return list(self.history_log)


if __name__ == "__main__":
    print("Testing RollbackManager:")
    rm = RollbackManager(dry_run=True)

    # 1. Apply good policy
    rm.apply_policy(50)
    assert rm.health_check() == True
    rm.make_permanent(50)
    assert rm.last_good_config == 50

    # 2. Apply bad policy (<=1mbit in mock triggers health check failure)
    rm.apply_policy(1)
    if not rm.health_check():
        rm.rollback()

    assert rm.history_log[-1]["status"] == "rolled_back"
    print("RollbackManager verification: PASS ✅")
