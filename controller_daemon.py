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

# Ensure local imports work cleanly
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from estimator.passive_estimator import PassiveEstimator
from classifier.flow_table import FlowTable
from classifier.runtime_classifier import FlowClassifier, LiveFlowSniffer
from policy_engine.intent_scheduler import IntentScheduler
from policy_engine.policy_rules import decide_policy
from policy_engine.rollback_manager import RollbackManager
from enforcement.dscp_marker import DscpMarker

import threading

class AdaptiveQoSController:
    def __init__(self, iface="veth-gw-wan", namespace="gw", nominal_capacity_mbps=100.0, dry_run=False, on_event=None):
        self.iface = iface
        self.namespace = namespace
        self.dry_run = dry_run
        self.on_event = on_event
        self._cycle_lock = threading.Lock()

        self.estimator = PassiveEstimator(iface=iface, namespace=namespace, nominal_capacity_mbps=nominal_capacity_mbps)
        self.flow_table = FlowTable()
        self.classifier = FlowClassifier()
        self.sniffer = LiveFlowSniffer(ifaces=["veth-lan1-gw", "veth-lan2-gw"], flow_table=self.flow_table, classifier=self.classifier)
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

    def get_system_state(self) -> dict:
        """Return authoritative system state snapshot."""
        with self._cycle_lock:
            active_intent = self.scheduler.get_active_intent()
            active_flows = self.flow_table.get_active_flows(active_within_sec=60)
            hist = self.rollback_mgr.get_history()

            status = self._status
            if status != "NORMAL" and hist and hist[-1].get("status") == "rolled_back":
                status = "ROLLED_BACK"
            elif active_intent:
                status = "PRIORITY_ACTIVE"
            elif self.estimator.get_effective_capacity() < 50.0:
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

            return {
                "system_status": status,
                "wan_bandwidth_mbps": self.estimator.get_effective_capacity(),
                "current_policy_bw": self.current_applied_bw if self.current_applied_bw is not None else 100,
                "active_intent": active_intent,
                "active_policy_name": active_policy_name,
                "last_safe_state": self.last_safe_state,
                "active_flows_count": len(active_flows),
                "dscp_rules_count": len(self.dscp_marker.get_rules()),
                "rollback_history_count": len(hist),
                "rollback_armed": True,
            }

    def schedule_intent(self, traffic_class: str, action: str = "prioritize", duration_sec: int = 1200) -> dict:
        """Authoritatively schedule priority intent and trigger immediate control cycle."""
        def on_expire_cb(rec):
            self._log(f"Intent expired for {rec.get('traffic_class')}. Restored to baseline policy.", "WARN")
            self._status = "NORMAL"

        scheduled = self.scheduler.schedule_intent(
            traffic_class=traffic_class,
            action=action,
            duration_sec=duration_sec,
            on_expire=on_expire_cb
        )
        self._status = "PRIORITY_ACTIVE"
        self._log(f"Temporary intent active: prioritize {traffic_class} for {duration_sec//60} min.", "ACTION")
        self.run_one_cycle()
        return scheduled

    def clear_intent(self):
        """Authoritatively clear active intent."""
        self.scheduler.clear()
        self._status = "NORMAL"
        self._log("Intent cancelled by operator. Baseline policy restored.", "ACTION")
        self.run_one_cycle()

    def override_flow(self, flow_id: str, corrected_class: str, reason: str = "Manual administrative override"):
        """Authoritatively record manual classification override and re-tag DSCP."""
        self.flow_table.override(flow_id, corrected_class)
        if "->" in flow_id and ":" in flow_id:
            src_ip = flow_id.split(":")[0]
            self.dscp_marker.mark_host(src_ip, corrected_class)
        self._log(f"Manual override applied: {flow_id} → {corrected_class} ({reason}).", "ACTION")

    def run_one_cycle(self, simulated_capacity_mbps=None) -> dict:
        """
        Execute a single closed-loop control iteration under thread-safe lock.
        """
        with self._cycle_lock:
            # 1. OBSERVE
            observed_rate = self.estimator.sample_rate()
            effective_capacity = simulated_capacity_mbps if simulated_capacity_mbps is not None else self.estimator.get_effective_capacity()
            active_flows = self.flow_table.get_active_flows(active_within_sec=20)
            active_intent = self.scheduler.get_active_intent()

            print(f"\n--- [CONTROL CYCLE] Time: {time.strftime('%H:%M:%S')} ---")
            print(f"[OBSERVE] Throughput: {observed_rate} Mbps | Effective Capacity: {effective_capacity} Mbps")
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

                # 4. MARK FLOWS (Ensure classified flows are tagged with proper DSCP)
                for f in active_flows:
                    flow_id = f.get("flow_id", "")
                    fclass = f.get("class", "unclassified")
                    # If priority intent matches, boost DSCP
                    if active_intent and active_intent.get("traffic_class") == fclass:
                        fclass = "video_conference"  # ensure priority tin
                    if ":" in flow_id:
                        src_ip = flow_id.split(":")[0]
                        self.dscp_marker.mark_host(src_ip, fclass)

                # 5. VERIFY (Closed-Loop QoE Health Check)
                time.sleep(0.5)
                healthy = self.rollback_mgr.health_check()
                if healthy:
                    self.rollback_mgr.make_permanent(target_bw)
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
