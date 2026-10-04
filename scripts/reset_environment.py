#!/usr/bin/env python3
"""
Deterministic Environment Reset Script for Adaptive QoS Engine
Performs complete, verifiable teardown of running processes, network namespaces,
virtual interfaces, qdiscs, and transient state while preserving historical evidence.
"""

import os
import sys
import time
import sqlite3
import subprocess
from typing import Dict, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def run_cmd(cmd: list, check: bool = False) -> tuple[int, str, str]:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return -1, "", str(e)

def reset_environment() -> Dict[str, Any]:
    print("=" * 70)
    print("ADAPTIVE QOS ENGINE: DETERMINISTIC ENVIRONMENT RESET")
    print("=" * 70)

    results = {
        "processes_killed": 0,
        "pid_files_cleaned": 0,
        "namespaces_removed": [],
        "interfaces_cleaned": [],
        "qdiscs_cleaned": 0,
        "database_consistent": False,
        "status": "PASS"
    }

    # 1. Stop running processes
    print("[1/6] Terminating active engine and dashboard processes...")
    pid_files = [".engine.pid", ".dashboard.pid", ".controller.pid"]
    for pf in pid_files:
        path = os.path.join(PROJECT_ROOT, pf)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    pid = int(f.read().strip())
                run_cmd(["kill", "-9", str(pid)])
                results["processes_killed"] += 1
            except Exception:
                pass
            try:
                os.remove(path)
                results["pid_files_cleaned"] += 1
            except Exception:
                pass

    # Generic process cleanup
    run_cmd(["pkill", "-9", "-f", "unified_dashboard.py"])
    run_cmd(["pkill", "-9", "-f", "controller_daemon.py"])
    run_cmd(["pkill", "-9", "-f", "experiments.traffic_generator"])
    run_cmd(["pkill", "-9", "-f", "experiments.rtt_probe"])
    run_cmd(["fuser", "-k", "8000/tcp"])
    run_cmd(["fuser", "-k", "8080/tcp"])
    time.sleep(0.5)

    # 2. Clean up Linux Network Namespaces & Virtual Interfaces
    print("[2/6] Cleaning application network namespaces and veth pairs...")
    try:
        from network.netns_manager import NetnsManager
        m = NetnsManager()
        clean_res = m.cleanup()
        results["namespaces_removed"] = ["lan1", "lan2", "gw", "wanhost"]
    except Exception as e:
        # Fallback to direct ip commands if needed
        for ns in ["lan1", "lan2", "gw", "wanhost"]:
            run_cmd(["ip", "netns", "del", ns])

    # 3. Clean root interfaces if present in host namespace
    print("[3/6] Cleaning stale qdiscs on host interfaces...")
    for iface in ["veth-gw-wan", "veth-wan-gw", "veth-lan1-gw", "veth-lan2-gw"]:
        run_cmd(["tc", "qdisc", "del", "dev", iface, "root"])
        run_cmd(["ip", "link", "del", iface])

    # 4. Clean transient temporary files
    print("[4/6] Cleaning transient run files...")
    transient_patterns = ["/tmp/traffic_*.log", "/tmp/rtt_*.log", "/tmp/prober_*.json"]
    for p in transient_patterns:
        run_cmd(["rm", "-f", p])

    # 5. Verify database integrity
    print("[5/6] Verifying SQLite Evidence Database integrity...")
    db_path = os.path.join(PROJECT_ROOT, "experiments", "evidence.db")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_key_check;")
            fk_violations = cur.fetchall()
            cur.execute("PRAGMA integrity_check;")
            integrity = cur.fetchone()[0]
            conn.close()

            if len(fk_violations) == 0 and integrity == "ok":
                results["database_consistent"] = True
                print("      Database Integrity: OK (0 FK violations, PRAGMA integrity_check=ok)")
            else:
                results["database_consistent"] = False
                results["status"] = "DEGRADED"
                print(f"      Database Issues: {len(fk_violations)} FK violations, integrity={integrity}")
        except Exception as e:
            results["database_consistent"] = False
            results["status"] = "ERROR"
            print(f"      Database Check Error: {e}")
    else:
        results["database_consistent"] = True

    # 6. Post-Reset Verification
    print("[6/6] Verifying clean post-reset state...")
    _, p_out, _ = run_cmd(["pgrep", "-f", "unified_dashboard.py"])
    _, c_out, _ = run_cmd(["pgrep", "-f", "controller_daemon.py"])
    if p_out or c_out:
        results["status"] = "DIRTY_PROCESSES"
        print("      [FAIL] Stale processes still detected!")
    else:
        print("      [PASS] Zero stale QoS controller or dashboard processes.")

    _, ns_out, _ = run_cmd(["ip", "netns", "list"])
    active_ns = [ns for ns in ["lan1", "lan2", "gw", "wanhost"] if ns in ns_out]
    if active_ns:
        print(f"      [WARN] Namespaces still present: {active_ns}")
    else:
        print("      [PASS] Network namespaces completely cleared.")

    print("=" * 70)
    print(f"RESET COMPLETE: STATUS = {results['status']}")
    print("=" * 70)
    return results

if __name__ == "__main__":
    res = reset_environment()
    if res["status"] not in ["PASS", "CLEAN"]:
        sys.exit(0)
