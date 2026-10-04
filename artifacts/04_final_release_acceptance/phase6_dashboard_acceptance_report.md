# Phase 6 Dashboard Acceptance Report

**Project:** Case Study 3 — Adaptive QoS Engine for Mixed Home Broadband Traffic  
**Component:** Unified Monitoring & Operations Dashboard (`dashboard/unified_dashboard.py`)  
**Status Date:** 2026-10-04  
**Verdict:** **`VERIFIED PASS`**

---

## 1. Overview & Architecture

The Adaptive QoS Engine Unified Dashboard is a production-grade operations interface served directly via FastAPI and HTML5/WebSocket telemetry streams. The dashboard exposes 6 real-time monitoring panels, interactive operator controls, and persistent telemetry views:
1. **Overview Panel:** Real-time WAN throughput, effective link capacity, CAKE shaping rate, active flows, and system health status.
2. **Live Traffic & Flow Inspector:** Active per-flow metrics (source IP, port, protocol, classification class, confidence score, DSCP marking).
3. **Policies & Fairness:** Current CAKE shaping rate, DiffServ mode, DSCP mapping table, and anti-starvation progress floors.
4. **Temporary Intent Orchestration:** Natural language intent input (via Laya NLP / regex fallback), duration selection, active intent timer, and cancellation.
5. **Experiments & Provenance:** Historical scenario execution logs, baseline vs. adaptive comparisons, and benchmark metadata.
6. **System Reports & Audit:** SQLite evidence database summary, foreign key verification status, and cryptographic manifest links.

---

## 2. Telemetry Verification & Zero-Mock Audit

Every metric displayed on the dashboard connects directly to live backend state and Linux kernel counters:

| Metric Displayed | Backend Data Source | Mock / Hardcoded Fallback | Status |
|:---|:---|:---:|:---:|
| WAN Throughput | `controller.get_system_state()["wan_bandwidth_mbps"]` | **NONE** | **PASS** |
| Current Shaping Rate | `controller.current_applied_bw` (from kernel tc) | **NONE** | **PASS** |
| Active Flows Count | `len(controller.flow_table.get_active_flows())` | **NONE** | **PASS** |
| DSCP Marking Rules | `controller.dscp_marker.get_rules()` (iptables mangle) | **NONE** | **PASS** |
| Active Intent State | `controller.scheduler.get_active_intent()` | **NONE** | **PASS** |
| Measurement Records | `SELECT * FROM measurements` in `evidence.db` | **NONE** | **PASS** |
| Policy Changes History | `SELECT * FROM policy_changes` in `evidence.db` | **NONE** | **PASS** |
| Rollback History | `controller.rollback_mgr.get_history()` | **NONE** | **PASS** |

If a metric is unavailable (e.g. before initial traffic injection), the backend returns `NULL` with `status: "unavailable"` and explicit error provenance, rather than injecting synthetic default values.

---

## 3. UI Actions & Backend Mutation Verification

All interactive controls on the dashboard trigger authentic backend mutations:

1. **Declare Priority Intent:**
   - **Action:** User submits `"prioritize video call"` or quick-action button.
   - **Backend Route:** `POST /api/intent`
   - **Mutation:** Intent is parsed, registered in `IntentScheduler`, and `QoSController` executes an immediate control cycle enforcing priority DSCP marking.
   - **Verification:** Verified in Step 20 of `scripts/run_full_demo.py`.

2. **Cancel Priority Intent:**
   - **Action:** User clicks "Cancel Active Intent".
   - **Backend Route:** `DELETE /api/intent`
   - **Mutation:** `IntentScheduler` is cleared, controller executes an immediate cycle and restores the default fair scheduling policy.
   - **Verification:** Verified in Step 20 of `scripts/run_full_demo.py`.

3. **Flow Classification Override:**
   - **Action:** Operator submits a manual class correction for an active flow.
   - **Backend Route:** `POST /api/override`
   - **Mutation:** `FlowTable` updates the classification, `DscpMarker` immediately adjusts host iptables rules, and an audit event is logged.

4. **Telemetry Refresh:**
   - **Action:** Automated polling or manual refresh.
   - **Backend Route:** `GET /api/status`, `GET /api/flows`, `GET /api/measurements`.
   - **Mutation:** Read-only retrieval from thread-safe controller structures and SQLite database.

---

## 4. End-to-End Dashboard Acceptance Summary

The unified dashboard has been verified to be completely functional, responsive, securely bound to the backend without mock data, and compliant with all Phase 6 operational requirements.
