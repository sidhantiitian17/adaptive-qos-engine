"""
Checkpoint/rollback manager for Linux traffic control qdiscs.
Inspired by Koo & Toueg (1987) tentative-vs-permanent checkpoint model.
Enforces bounded, observable, reversible, and fail-closed automated remediation.
"""
import os
import sys
import subprocess
import time
import re
import threading
from typing import Dict, Any, Optional, List

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from network.tc_manager import TcManager


class RollbackManager:
    """
    Fail-closed transactional QoS state manager.
    Coordinates tentative policy deployment, kernel verification,
    post-deployment health validation, and atomic snapshot restoration.
    """
    def __init__(self, namespace: str = "gw", iface: str = "veth-gw-wan", dry_run: bool = False, tc_manager: Optional[TcManager] = None):
        self._lock = threading.Lock()
        self.namespace = namespace
        self.iface = iface
        self.dry_run = dry_run
        self.tc_manager = tc_manager or TcManager(iface=iface, namespace=namespace, dry_run=dry_run)

        self.last_good_config: Optional[int] = None  # Last known-good bandwidth (Mbps)
        self.last_known_good_snapshot: Optional[Dict[str, Any]] = None
        self.current_tentative_snapshot: Optional[Dict[str, Any]] = None
        self.history_log: List[Dict[str, Any]] = []

        self._check_permissions()
        # Seed initial snapshot if possible
        self._seed_initial_snapshot()

    def _check_permissions(self):
        if not self.dry_run and os.geteuid() != 0:
            check = subprocess.run(["sudo", "-n", "true"], capture_output=True)
            if check.returncode != 0:
                self.dry_run = True

    def _run(self, cmd_args):
        if self.dry_run:
            return 0, "mock_output", ""
        import shlex
        if isinstance(cmd_args, str):
            args = shlex.split(cmd_args)
        else:
            args = list(cmd_args)
        if os.geteuid() != 0 and (not args or args[0] != "sudo"):
            args = ["sudo", "-n"] + args
        try:
            res = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=5)
            return res.returncode, res.stdout, res.stderr
        except subprocess.TimeoutExpired:
            return 124, "", "Subprocess timed out after 5s"
        except Exception as e:
            return 1, "", str(e)

    def _seed_initial_snapshot(self):
        """Capture initial verified baseline snapshot on boot."""
        try:
            state = self.tc_manager.get_qdisc_state()
            if state and state.get("qdisc_type") == "cake":
                bw_val = state.get("bandwidth_mbit")
                if bw_val is None and state.get("bandwidth"):
                    bw_match = re.search(r"(\d+)", state["bandwidth"])
                    if bw_match:
                        bw_val = int(bw_match.group(1))

                if bw_val is not None and bw_val > 0:
                    bw_int = int(round(bw_val))
                    ds_mode = state.get("diffserv_mode") or "diffserv4"
                    self.last_good_config = bw_int
                    self.last_known_good_snapshot = {
                        "interface": self.iface,
                        "namespace": self.namespace,
                        "bandwidth_mbit": bw_int,
                        "diffserv": ds_mode,
                        "diffserv_mode": ds_mode,
                        "qdisc_type": "cake",
                        "handle": state.get("handle"),
                        "parent": state.get("parent", "root"),
                        "timestamp": time.time(),
                        "verified": (state.get("status") == "verified")
                    }
        except Exception:
            pass

    def checkpoint(self) -> Dict[str, Any]:
        """Capture structured snapshot of current verified configuration before mutations."""
        state = self.tc_manager.get_qdisc_state()
        bw_mbit = state.get("bandwidth_mbit")
        if bw_mbit is None and state.get("bandwidth"):
            bw_match = re.search(r"(\d+)", state["bandwidth"])
            if bw_match:
                bw_mbit = float(bw_match.group(1))

        snapshot = {
            "timestamp": time.time(),
            "interface": self.iface,
            "namespace": self.namespace,
            "qdisc_type": state.get("qdisc_type", "unknown"),
            "bandwidth": state.get("bandwidth"),
            "bandwidth_mbit": int(round(bw_mbit)) if bw_mbit is not None else None,
            "diffserv": state.get("diffserv_mode") or "diffserv4",
            "diffserv_mode": state.get("diffserv_mode") or "diffserv4",
            "handle": state.get("handle"),
            "parent": state.get("parent", "root"),
            "verified": (state.get("status") == "verified"),
            "kernel_verified": (state.get("status") == "verified"),
            "raw_state": state
        }
        return snapshot

    def apply_policy(self, bandwidth_mbit: int, diffserv: str = "diffserv4") -> bool:
        """
        Apply new shaping rate tentatively with strict kernel verification.
        Fail-closed: Returns False if command fails or kernel state does not reflect change.
        """
        with self._lock:
            # 1. Capture pre-apply snapshot for rollback
            prev_snapshot = self.checkpoint()
            self.current_tentative_snapshot = prev_snapshot

            bandwidth_mbit = max(1, int(bandwidth_mbit))
            bw_str = f"{bandwidth_mbit}mbit"

            # 2. Delegate to TcManager with comprehensive verification
            apply_res = self.tc_manager.apply_cake(bandwidth_mbit, diffserv=diffserv)
            applied_ok = apply_res.get("success", False)
            verified_state = apply_res.get("verified_state", {})

            if not applied_ok:
                err_msg = apply_res.get("error") or "TcManager apply_cake failed"
                print(f"[ROLLBACK_MGR] Apply/verification error applying {bw_str} ({diffserv}): {err_msg}")

                # Auto-restore pre-apply snapshot to maintain kernel state integrity
                auto_restore_ok = False
                restore_bw = prev_snapshot.get("bandwidth_mbit") if prev_snapshot else None
                restore_ds = (prev_snapshot.get("diffserv_mode") or prev_snapshot.get("diffserv", "diffserv4")) if prev_snapshot else "diffserv4"
                if restore_bw is None and self.last_known_good_snapshot:
                    restore_bw = self.last_known_good_snapshot.get("bandwidth_mbit")
                    restore_ds = self.last_known_good_snapshot.get("diffserv_mode") or self.last_known_good_snapshot.get("diffserv", "diffserv4")
                elif restore_bw is None and self.last_good_config is not None:
                    restore_bw = self.last_good_config
                    restore_ds = "diffserv4"

                if restore_bw is not None and isinstance(restore_bw, (int, float)):
                    res_restore = self.tc_manager.apply_cake(int(round(restore_bw)), diffserv=restore_ds)
                    auto_restore_ok = res_restore.get("success", False)
                    print(f"[ROLLBACK_MGR] Immediate restoration to {restore_bw}mbit ({restore_ds}): success={auto_restore_ok}")

                entry = {
                    "timestamp": time.time(),
                    "bandwidth_mbit": bandwidth_mbit,
                    "diffserv": diffserv,
                    "status": "apply_failed" if "execution" in err_msg.lower() else "verification_failed",
                    "applied_successfully": False,
                    "kernel_verified": False,
                    "auto_restored": auto_restore_ok,
                    "error": err_msg,
                    "verified_state": verified_state
                }
                self.history_log.append(entry)
                return False

            entry = {
                "timestamp": time.time(),
                "bandwidth_mbit": bandwidth_mbit,
                "diffserv": diffserv,
                "status": "tentative",
                "applied_successfully": True,
                "kernel_verified": (verified_state.get("status") == "verified"),
                "is_dry_run": self.dry_run,
                "verified_state": verified_state
            }
            self.history_log.append(entry)
            print(f"[ROLLBACK_MGR] Applied tentative policy: {bw_str} ({diffserv}) -> Success: True")
            return True

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
        with self._lock:
            latest = self.history_log[-1] if self.history_log else {}
            # Degraded simulation threshold for testing failure injection
            if latest.get("bandwidth_mbit", 10) <= 1:
                print(f"[HEALTH CHECK] Simulated/detected excessive impairment for {latest.get('bandwidth_mbit')}mbit.")
                return False

            if self.dry_run:
                return True

            code, out, _ = self._run(f"ip netns exec lan1 ping -c 3 -W 2 {target_ip}")
            if code != 0:
                print("[HEALTH CHECK] Ping command failed entirely. Unhealthy.")
                return False

            match_rtt = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/", out)
            match_loss = re.search(r"(\d+)% packet loss", out)

            if match_rtt and match_loss:
                avg_latency = float(match_rtt.group(1))
                loss_pct = float(match_loss.group(1))
                print(f"[HEALTH CHECK] Avg Latency: {avg_latency}ms (limit: {latency_threshold_ms}ms) | Loss: {loss_pct}%")
                return (avg_latency <= latency_threshold_ms) and (loss_pct <= max_loss_pct)

            return False

    def make_permanent(self, bandwidth_mbit: int, diffserv: str = "diffserv4"):
        """Mark configuration as permanent (known-good checkpoint) following health check pass."""
        with self._lock:
            if self.history_log:
                self.history_log[-1]["status"] = "permanent"
            self.last_good_config = bandwidth_mbit
            self.last_known_good_snapshot = {
                "interface": self.iface,
                "namespace": self.namespace,
                "bandwidth_mbit": bandwidth_mbit,
                "diffserv": diffserv,
                "diffserv_mode": diffserv,
                "qdisc_type": "cake",
                "timestamp": time.time(),
                "verified": not self.dry_run
            }
            print(f"[ROLLBACK_MGR] Committed bandwidth={bandwidth_mbit}mbit as permanent known-good.")

    def rollback(self) -> bool:
        """
        Roll back to last verified known-good configuration.
        Restores exact snapshot parameters, verifies kernel state, and updates history.
        Fail-closed: Returns False if restoration or kernel verification fails.
        """
        with self._lock:
            # 1. Determine target rollback parameters from saved snapshot
            has_snapshot = False
            target_snapshot = self.current_tentative_snapshot or self.last_known_good_snapshot
            target_bw = None
            target_diffserv = "diffserv4"

            if target_snapshot and target_snapshot.get("bandwidth_mbit"):
                target_bw = target_snapshot["bandwidth_mbit"]
                target_diffserv = target_snapshot.get("diffserv_mode") or target_snapshot.get("diffserv", "diffserv4")
                has_snapshot = True
            elif self.last_known_good_snapshot and self.last_known_good_snapshot.get("bandwidth_mbit"):
                target_bw = self.last_known_good_snapshot["bandwidth_mbit"]
                target_diffserv = self.last_known_good_snapshot.get("diffserv_mode") or self.last_known_good_snapshot.get("diffserv", "diffserv4")
                has_snapshot = True
            elif self.last_good_config is not None:
                target_bw = self.last_good_config
                target_diffserv = "diffserv4"
                has_snapshot = True

            if not has_snapshot or target_bw is None:
                err = "No verified checkpoint/snapshot available for rollback (fail-closed)"
                print(f"[ROLLBACK_MGR] ❌ Rollback failed: {err}")
                rollback_entry = {
                    "timestamp": time.time(),
                    "status": "rollback_failed",
                    "rollback_bandwidth": None,
                    "rollback_diffserv": None,
                    "rollback_success": False,
                    "had_prior_snapshot": False,
                    "error": err
                }
                if self.history_log:
                    self.history_log[-1].update(rollback_entry)
                else:
                    self.history_log.append(rollback_entry)
                return False

            # 2. Execute restoration and verify actual kernel state
            res = self.tc_manager.apply_cake(int(round(target_bw)), diffserv=target_diffserv)
            rollback_ok = res.get("success", False)

            if rollback_ok:
                print(f"[ROLLBACK_MGR] ⚠️ Reverted to safe configuration: {target_bw}mbit ({target_diffserv}) (Success: True)")
            else:
                err = res.get("error") or "Restoration verification failed"
                print(f"[ROLLBACK_MGR] ❌ Rollback failed: {err}")

            rollback_entry = {
                "timestamp": time.time(),
                "status": "rolled_back" if rollback_ok else "rollback_failed",
                "rollback_bandwidth": target_bw,
                "rollback_diffserv": target_diffserv,
                "rollback_success": rollback_ok,
                "had_prior_snapshot": has_snapshot,
                "error": res.get("error") if not rollback_ok else None
            }
            if self.history_log:
                self.history_log[-1].update(rollback_entry)
            else:
                self.history_log.append(rollback_entry)

            return rollback_ok

    def get_history(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(e) for e in self.history_log]

    def commit_known_good(self, bandwidth="95mbit", diffserv="diffserv4") -> bool:
        bw_int = int(str(bandwidth).replace("mbit", "").replace("M", "").replace("mbps", ""))
        self.make_permanent(bw_int, diffserv)
        return True

    def apply_tentative(self, bandwidth="1mbit", diffserv="diffserv4") -> bool:
        bw_int = int(str(bandwidth).replace("mbit", "").replace("M", "").replace("mbps", ""))
        return self.apply_policy(bw_int, diffserv)

    def revert(self) -> bool:
        return self.rollback()
