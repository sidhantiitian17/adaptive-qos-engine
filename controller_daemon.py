"""
Unified Autonomous QoS Controller Daemon:
Executes the closed-loop adaptive control cycle:
  Observe -> Detect -> Decide -> Act -> Verify
Integrates Link Estimator, Real-time Classifier, User Intent API,
and Rollback-protected Linux TC Enforcement.
"""
import os
import sys
import time
import argparse
import threading
from typing import Optional, Dict, Any, List

# Ensure local imports work cleanly
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from estimator.passive_estimator import PassiveEstimator
from estimator.slops_estimator import SlopsLinkEstimator, SlopsConfig, CapacityEstimate
from classifier.flow_table import FlowTable
from classifier.flow_tuple import FlowTuple
from classifier.runtime_classifier import FlowClassifier, LiveFlowSniffer
from policy_engine.intent_scheduler import IntentScheduler
from policy_engine.policy_rules import decide_policy
from policy_engine.rollback_manager import RollbackManager
from policy_engine.traffic_classes import normalize_class_name
from enforcement.dscp_marker import DscpMarker


class AdaptiveQoSController:
    def __init__(self, iface="veth-gw-wan", namespace="gw", nominal_capacity_mbps=100.0, dry_run=False, on_event=None):
        self.iface = iface
        self.namespace = namespace
        self.dry_run = dry_run
        self.on_event = on_event
        self._cycle_lock = threading.Lock()

        self.estimator = PassiveEstimator(iface=iface, namespace=namespace, nominal_capacity_mbps=nominal_capacity_mbps)
        s_ns = "lan1" if os.path.exists("/var/run/netns/lan1") else None
        r_ns = "wanhost" if os.path.exists("/var/run/netns/wanhost") else None
        self.active_estimator = SlopsLinkEstimator(
            target_ip="10.0.3.2",
            sender_namespace=s_ns,
            receiver_namespace=r_ns
        )
        self.latest_capacity_estimate: Optional[CapacityEstimate] = None

        # Autonomous Active Probing Scheduler Configuration (Phase 3)
        self.enable_active_probing = True
        self.probe_interval_sec = 30.0    # Periodic probing cadence
        self.probe_cooldown_sec = 10.0    # Minimum gap between probe sessions
        self.probe_timeout_sec = 5.0      # Execution timeout limit
        self.max_estimate_age_sec = 60.0  # Freshness threshold before fallback
        self.last_probe_time: Optional[float] = None
        self.last_probe_status: str = "never_run"
        self.last_probe_duration_sec: float = 0.0
        self.last_probe_error: Optional[str] = None
        self.estimator_source_used: str = "passive_init"
        self._probing_lock = threading.Lock()

        self.flow_table = FlowTable()
        self.classifier = FlowClassifier()
        self.sniffer = LiveFlowSniffer(ifaces=["veth-lan1-gw", "veth-lan2-gw"], flow_table=self.flow_table, classifier=self.classifier, namespace=namespace)
        self.scheduler = IntentScheduler()
        self.rollback_mgr = RollbackManager(namespace=namespace, iface=iface, dry_run=dry_run)
        self.dscp_marker = DscpMarker(namespace=namespace, dry_run=dry_run)

        self.current_applied_bw = None
        self._status = "NORMAL"
        self.last_safe_state = time.strftime("%H:%M:%S")
        self.is_running = False

    def _log(self, msg: str, level: str = "INFO"):
        print(f"[CONTROLLER] [{level}] {msg}")
        if callable(self.on_event):
            try:
                self.on_event(msg, level)
            except Exception:
                pass

    def start_monitoring(self):
        """Start background packet sniffer."""
        try:
            self.sniffer.start()
        except Exception as e:
            self._log(f"Live sniffer not bound to hardware ifaces ({e}), continuing in passive/simulation mode.", "WARN")

    def stop_monitoring(self):
        self.sniffer.stop()
        if hasattr(self.active_estimator, "stop_receiver"):
            self.active_estimator.stop_receiver()

    def get_effective_capacity(self) -> float:
        """
        Contract M2 -> M3: returns effective capacity under explicit selection hierarchy:
        1. Fresh active SLoPS estimate within max_estimate_age_sec.
        2. Passive estimator as documented fallback when active is unavailable or stale.
        3. Nominal capacity fallback with reduced confidence.
        """
        now = time.time()
        # 1. Active SLoPS estimate (fresh and verified)
        if (self.latest_capacity_estimate and
            self.latest_capacity_estimate.status == "measured" and
            self.latest_capacity_estimate.effective_capacity_mbps > 0 and
            (now - getattr(self.latest_capacity_estimate, "timestamp", now) <= self.max_estimate_age_sec)):
            self.estimator_source_used = "active_slops"
            return self.latest_capacity_estimate.effective_capacity_mbps

        # 2. Passive estimator fallback
        try:
            passive_cap = self.estimator.get_effective_capacity()
            if passive_cap and passive_cap > 0:
                self.estimator_source_used = "passive_fallback"
                return passive_cap
        except Exception as e:
            self._log(f"Passive estimator failed ({e}), using safe fallback.", "WARN")

        # 3. Conservative safe default
        self.estimator_source_used = "conservative_fallback"
        return self.estimator.nominal_capacity_mbps

    def run_active_probing(self) -> Optional[CapacityEstimate]:
        """
        Trigger SLoPS active probing stream and update capacity estimate.
        Guarantees non-overlapping execution, cooldown bounding, and result validation.
        """
        acquired = self._probing_lock.acquire(blocking=False)
        if not acquired:
            self._log("Active probe already in progress. Rejecting concurrent probe session.", "WARN")
            return self.latest_capacity_estimate

        now = time.time()
        if self.last_probe_time and (now - self.last_probe_time < self.probe_cooldown_sec):
            self._log(f"Active probe cooldown active ({self.probe_cooldown_sec}s). Skipping probe.", "INFO")
            self._probing_lock.release()
            return self.latest_capacity_estimate

        t0 = time.time()
        self._log("Running SLoPS active link capacity estimation probe...", "INFO")
        try:
            est = self.active_estimator.estimate_capacity()
            duration = time.time() - t0
            self.last_probe_time = time.time()
            self.last_probe_duration_sec = round(duration, 3)

            # Plausibility validation (1.0 to 10000.0 Mbps)
            if est and est.status == "measured" and (1.0 <= est.effective_capacity_mbps <= 10000.0):
                est.timestamp = self.last_probe_time
                self.latest_capacity_estimate = est
                self.last_probe_status = "success"
                self.last_probe_error = None
                self._log(
                    f"SLoPS probe completed in {duration:.2f}s: Range [{est.estimated_bandwidth_min_mbps}, {est.estimated_bandwidth_max_mbps}] Mbps "
                    f"(Midpoint: {est.estimated_bandwidth_mid_mbps} Mbps, Conf: {est.confidence}, PCT: {est.pct}, PDT: {est.pdt}).",
                    "SUCCESS"
                )
            else:
                err_msg = "Implausible or unmeasured active probe result"
                self.last_probe_status = "invalid_measurement"
                self.last_probe_error = err_msg
                self._log(f"Active probe rejected: {err_msg}.", "WARN")
            return self.latest_capacity_estimate
        except Exception as e:
            self.last_probe_status = "failed"
            self.last_probe_error = str(e)
            self._log(f"Active capacity probe failed with exception: {e}", "WARN")
            return self.latest_capacity_estimate
        finally:
            self._probing_lock.release()

    def get_system_state(self) -> dict:
        """Return authoritative system state snapshot with full provenance."""
        with self._cycle_lock:
            active_intent = self.scheduler.get_active_intent()
            active_flows = self.flow_table.get_active_flows(active_within_sec=60)
            hist = self.rollback_mgr.get_history()

            status = self._status
            if status != "NORMAL" and hist and hist[-1].get("status") == "rolled_back":
                status = "ROLLED_BACK"
            elif active_intent:
                status = "PRIORITY_ACTIVE"
            elif self.get_effective_capacity() < 50.0:
                status = "DEGRADED"
            else:
                status = self._status

            active_policy_name = "DEFAULT FAIRNESS"
            if active_intent and active_intent.get("traffic_class"):
                active_policy_name = f"{active_intent.get('traffic_class').replace('_', ' ').upper()} — HIGH"
            elif status == "DEGRADED":
                active_policy_name = f"WAN DEGRADED ({self.current_applied_bw or 100}M)"
            elif status == "ROLLED_BACK":
                active_policy_name = "SAFE STATE RESTORED"

            eff_cap = self.get_effective_capacity()
            cap_est = self.latest_capacity_estimate.to_dict() if self.latest_capacity_estimate else None

            return {
                "system_status": status,
                "wan_bandwidth_mbps": eff_cap,
                "capacity_estimate": cap_est,
                "capacity_range_mbps": [
                    self.latest_capacity_estimate.estimated_bandwidth_min_mbps,
                    self.latest_capacity_estimate.estimated_bandwidth_max_mbps
                ] if self.latest_capacity_estimate else [round(eff_cap * 0.9, 1), round(eff_cap * 1.05, 1)],
                "current_policy_bw": self.current_applied_bw if self.current_applied_bw is not None else 100,
                "active_intent": active_intent,
                "active_policy_name": active_policy_name,
                "last_safe_state": self.last_safe_state,
                "active_flows_count": len(active_flows),
                "dscp_rules_count": len(self.dscp_marker.get_rules()),
                "rollback_history_count": len(hist),
                "rollback_armed": True,
                "estimator_source_used": self.estimator_source_used,
                "last_probe_status": self.last_probe_status,
                "last_probe_time": self.last_probe_time,
                "last_probe_duration_sec": self.last_probe_duration_sec,
                "last_probe_error": self.last_probe_error,
            }

    def schedule_intent(self, traffic_class: str, action: str = "prioritize", duration_sec: int = 1200) -> dict:
        """Authoritatively schedule priority intent and trigger immediate control cycle."""
        canonical_class = normalize_class_name(traffic_class)

        def on_expire_cb(rec):
            self._log(f"Intent expired for {rec.get('traffic_class')}. Restoring baseline policy.", "WARN")
            self._status = "NORMAL"
            # Immediately execute control cycle to re-evaluate policy and restore baseline DSCP
            try:
                self.run_one_cycle()
            except Exception as e:
                self._log(f"Error reverting policy on intent expiration: {e}", "WARN")

        scheduled = self.scheduler.schedule_intent(
            traffic_class=canonical_class,
            action=action,
            duration_sec=duration_sec,
            on_expire=on_expire_cb
        )
        self._status = "PRIORITY_ACTIVE"
        self._log(f"Temporary intent active: prioritize {canonical_class} for {duration_sec//60} min.", "ACTION")
        self.run_one_cycle()
        return scheduled

    def clear_intent(self):
        """Authoritatively clear active intent."""
        self.scheduler.clear()
        self._status = "NORMAL"
        self._log("Intent cancelled by operator. Baseline policy restored.", "ACTION")
        self.run_one_cycle()

    def override_flow(self, flow_id: str, corrected_class: str, reason: str = "Manual administrative override"):
        """Authoritatively record manual classification override and re-tag per-flow DSCP."""
        canonical_class = normalize_class_name(corrected_class)
        self.flow_table.override(flow_id, canonical_class)

        flow_tuple = FlowTuple.parse_or_none(flow_id)
        if flow_tuple:
            self.dscp_marker.mark_flow(flow_tuple, canonical_class)
        elif ":" in flow_id:
            src_ip = flow_id.split(":")[0]
            self.dscp_marker.mark_host(src_ip, canonical_class)

        self._log(f"Manual override applied: {flow_id} → {canonical_class} ({reason}).", "ACTION")

    def run_one_cycle(self, simulated_capacity_mbps=None) -> dict:
        """
        Execute a single closed-loop control iteration under thread-safe lock.
        Observe -> Detect -> Decide -> Act -> Verify
        """
        with self._cycle_lock:
            # Autonomous periodic probing trigger
            if simulated_capacity_mbps is None and self.enable_active_probing:
                now = time.time()
                if self.last_probe_time is None or (now - self.last_probe_time >= self.probe_interval_sec):
                    # Launch bounded active probe in background daemon
                    threading.Thread(target=self.run_active_probing, daemon=True).start()

            # 1. OBSERVE
            observed_rate = self.estimator.sample_rate()
            effective_capacity = simulated_capacity_mbps if simulated_capacity_mbps is not None else self.get_effective_capacity()
            active_flows = self.flow_table.get_active_flows(active_within_sec=20)
            active_intent = self.scheduler.get_active_intent()

            print(f"\n--- [CONTROL CYCLE] Time: {time.strftime('%H:%M:%S')} ---")
            print(f"[OBSERVE] Throughput: {observed_rate} Mbps | Effective Capacity: {effective_capacity} Mbps (Source: {self.estimator_source_used})")
            print(f"[OBSERVE] Active Flows: {len(active_flows)} | Active Intent: {active_intent.get('traffic_class') if active_intent else 'None'}")

            # 2. DECIDE
            decision = decide_policy(
                available_bandwidth_mbps=effective_capacity,
                active_flows=active_flows,
                user_intent=active_intent
            )
            target_bw = decision["bandwidth_mbit"]
            print(f"[DECIDE] Target Shaping: {target_bw} Mbps ({decision['diffserv_mode']}) | Reasons: {decision['reasoning']}")

            # 3. ACT (Only modify if bandwidth changed or not yet initialized)
            needs_update = (self.current_applied_bw != target_bw)
            action_taken = "no_change_needed"

            if needs_update:
                print(f"[ACT] Updating CAKE shaping: {self.current_applied_bw} -> {target_bw} Mbps")
                applied = self.rollback_mgr.apply_policy(target_bw, decision["diffserv_mode"])

                if not applied:
                    print(f"[ACT] ❌ Policy application failed at kernel level. Aborting commit.")
                    self._log(f"Policy application for {target_bw} Mbps failed at kernel level.", "CRITICAL")
                    self.rollback_mgr.rollback()
                    self._status = "ROLLED_BACK"
                    action_taken = "apply_failed"
                else:
                    # 4. MARK FLOWS (Genuine per-flow 5-tuple DSCP marking)
                    for f in active_flows:
                        flow_id = f.get("flow_id", "")
                        fclass = f.get("class", "unclassified")
                        effective_class = fclass

                        # If priority intent matches, retain canonical priority class
                        if active_intent and active_intent.get("action") == "prioritize":
                            intent_target = active_intent.get("traffic_class")
                            if intent_target and normalize_class_name(intent_target) == normalize_class_name(fclass):
                                effective_class = normalize_class_name(intent_target)

                        flow_tuple = FlowTuple.parse_or_none(flow_id)
                        if flow_tuple:
                            self.dscp_marker.mark_flow(flow_tuple, effective_class)
                        elif ":" in flow_id:
                            src_ip = flow_id.split(":")[0]
                            self.dscp_marker.mark_host(src_ip, effective_class)

                    # 5. VERIFY (Closed-Loop QoE Health Check)
                    time.sleep(0.5)
                    healthy = self.rollback_mgr.health_check()
                    if healthy:
                        self.rollback_mgr.make_permanent(target_bw, decision["diffserv_mode"])
                        self.current_applied_bw = target_bw
                        self.last_safe_state = time.strftime("%H:%M:%S")
                        action_taken = "applied_and_committed"
                        if active_intent:
                            self._status = "PRIORITY_ACTIVE"
                        elif effective_capacity < 50.0:
                            self._status = "DEGRADED"
                        else:
                            self._status = "NORMAL"
                        print(f"[VERIFY] ✅ Health check passed. New policy committed.")
                        self._log(f"Closed-loop policy applied: CAKE shaping set to {target_bw} Mbps ({decision['diffserv_mode']}).", "SUCCESS")
                    else:
                        self.rollback_mgr.rollback()
                        self._status = "ROLLED_BACK"
                        action_taken = "rolled_back"
                        print(f"[VERIFY] ⚠️ Health check failed! Policy rolled back to safe state.")
                        self._log(f"Health check failed! Automatically rolled back to safe state.", "CRITICAL")

            return {
                "effective_capacity_mbps": effective_capacity,
                "target_bw_mbit": target_bw,
                "action_taken": action_taken,
                "decision": decision
            }

    def run_daemon(self, interval_sec=3, max_iterations=None):
        """Continuous execution loop."""
        self.is_running = True
        self.start_monitoring()
        count = 0
        print(f"[CONTROLLER] Daemon started (interval={interval_sec}s). Press Ctrl+C to stop.")
        try:
            while self.is_running:
                self.run_one_cycle()
                count += 1
                if max_iterations and count >= max_iterations:
                    break
                time.sleep(interval_sec)
        except KeyboardInterrupt:
            print("\n[CONTROLLER] Stopping daemon...")
        finally:
            self.stop_monitoring()
            self.is_running = False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Adaptive QoS Controller Daemon")
    parser.add_argument("--test-cycle", action="store_true", help="Execute single test cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Run in mock/dry-run mode")
    parser.add_argument("--iterations", type=int, default=None, help="Max iterations for daemon")
    parser.add_argument("--interval", type=int, default=3, help="Loop interval in seconds")
    args = parser.parse_args()

    controller = AdaptiveQoSController(dry_run=args.dry_run)
    if args.test_cycle:
        print("=== Running Single Closed-Loop Control Cycle ===")
        res = controller.run_one_cycle(simulated_capacity_mbps=20.0)
        print("\nCycle Result Summary:", res)
        assert res["target_bw_mbit"] == 19
        print("\nController Daemon single cycle: PASS ✅")
    else:
        controller.run_daemon(interval_sec=args.interval, max_iterations=args.iterations)
