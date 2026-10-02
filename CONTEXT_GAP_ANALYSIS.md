# CONTEXT (1).md vs Codebase — Gap Analysis

**Date:** 2026-10-02  
**Source:** [CONTEXT (1).md](file:///home/prashast/adaptive-qos-engine/CONTEXT%20%281%29.md) — a planning/advisory document with recommendations for building the prototype.

---

## Summary

The CONTEXT file contains **advisory recommendations**, not additional requirements beyond ps3.md. Most recommendations have been implemented. Below are the items that are **missing or differ** from the CONTEXT's suggestions.

---

## 🔴 Actually Missing (Should Implement)

### 1. `.env` not in `.gitignore`
**CONTEXT says (Line 115):** Add `.env` to `.gitignore`.  
**Current state:** `.gitignore` only has `venv/`. The `.env.example` exists and is correct, but `.env` itself isn't gitignored.  
**Risk:** If someone creates a real `.env`, it could be accidentally committed.  
**Fix:** One line addition to `.gitignore`.

### 2. No `inject_failure.sh` — Explicit Bad-Policy Test Script
**CONTEXT says (Lines 101-111):** Create a script that deliberately injects a bad tc config and shows the engine auto-reverting, so judges can see "failure → auto-revert" is REAL, not just claimed.  
**Current state:** `RollbackManager` has this logic and it's tested programmatically (T6 in verification), but there's no standalone shell script a judge can run to see it happen live with real kernel operations.  
**Risk:** Judges can't one-command-verify rollback behavior.

### 3. No `reset_env.sh` — Environment Reset Script
**CONTEXT says (Line 65):** A `reset_env.sh` that restores known-safe state before experiments.  
**Current state:** `testbed/teardown.sh` exists (deletes namespaces) and `testbed/setup_topo.sh` recreates them, but there's no single `reset_env.sh` that cleans QoS rules + resets CAKE + clears metrics logs in one command.  
**Risk:** Minor. Judges must run teardown + setup separately.

### 4. No BibTeX/References File
**CONTEXT says (Lines 596-611, 929-944, 1458-1472, etc.):** Provide proper academic citations (BibTeX) for all referenced papers.  
**Current state:** Paper names are mentioned in `README.md` and `docs/architecture.md` (e.g., "SLoPS-inspired", "NetMatrix-style", "Koo & Toueg") but there is NO `references.bib` or `REFERENCES.md` file with proper citations.  
**Risk:** Judges expect academic rigor. Missing proper citations.

### 5. No Downstream QoS Effect Comparison for Classifier
**CONTEXT says (Line 192):** Show "downstream effect — QoS improvement (latency reduction %) when ML classifier is used vs heuristic."  
**Current state:** `classifier/compare_classifiers.py` compares accuracy only (93.7% vs 99.1%). It does NOT measure how classification accuracy translates to actual QoS improvement (e.g., latency reduction when XGBoost-classified flows get correct DSCP vs when heuristic misclassifies them).  
**Risk:** Judges may ask "okay, accuracy improved, but did it actually make the network better?" — no evidence for that.

### 6. No Framing Statement About Laya vs Core AI
**CONTEXT says (Lines 342-344):** README should explicitly state: "Laya is used for structured intent extraction only... The core measurable AI contribution evaluated in this project is [traffic classification]..."  
**Current state:** `docs/known_limitations.md` §5 mentions Laya confidence calibration, but there's NO explicit framing statement in README or architecture docs that separates "Laya = UX convenience" from "XGBoost classifier = measurable AI contribution."  
**Risk:** Judges may think Laya IS the AI contribution, which the ps3.md warns against ("rather than merely adding a conversational interface").

---

## 🟡 Acceptable Differences (Implemented Differently, Not Missing)

### 7. Mininet-HiFi Not Used — Raw netns Instead
**CONTEXT recommends:** Mininet-HiFi for the testbed.  
**Current state:** Uses raw `ip netns` + veth pairs + NetEm via shell scripts (`testbed/setup_topo.sh`).  
**Verdict:** ✅ **Acceptable.** The raw netns approach achieves the same result (real kernel code, real qdiscs) without the Mininet dependency. Actually simpler and more transparent.

### 8. No Prometheus/Grafana — Custom Dashboard Instead
**CONTEXT recommends (Line 77-83):** Prometheus + Grafana via docker-compose.  
**Current state:** Custom Chart.js dashboard via FastAPI (`dashboard/dashboard_server.py`) with 6 metrics.  
**Verdict:** ✅ **Acceptable.** Custom dashboard is lighter, has no Docker dependency, and shows exactly the 6 required metrics. Less impressive visually but more portable.

### 9. No Flent/irtt — Uses iperf3/ping Instead
**CONTEXT recommends (Lines 87-93):** Flent RRUL test for fairness verification.  
**Current state:** Uses `iperf3` for throughput, `ping` for latency/jitter/loss, Jain's fairness formula in code.  
**Verdict:** ✅ **Acceptable.** iperf3+ping are more widely available and still measure the same metrics. Flent would be nicer but isn't required.

### 10. Passive Estimator vs Active Probing in Controller
**CONTEXT recommends (Lines 621-735):** Active iperf3-based probing for the controller's runtime loop.  
**Current state:** `controller_daemon.py` uses `PassiveEstimator` (reads `/proc/net/dev` byte counters) for the runtime loop. The `link_estimator.py` (SLoPS/active probing) exists but is a standalone verification tool, not wired into the daemon.  
**Verdict:** ✅ **Acceptable.** Passive estimation is actually BETTER for runtime (non-intrusive, no probe traffic overhead). Active probing is used for verification only. The CONTEXT itself acknowledges this as "Option B" (Line 652-656).

### 11. SLoPS Algorithm Not Fully Implemented
**CONTEXT provides (Lines 1001-1230):** Detailed SLoPS/Pathload algorithm (fleet sending, PCT/PDT trend detection, binary search).  
**Current state:** `estimator/link_estimator.py` uses simplified active probing (iperf3 bursts + smoothing), not the full SLoPS PCT/PDT/fleet mechanism. It's documented as "SLoPS-inspired."  
**Verdict:** ✅ **Acceptable.** The simplified approach works for the prototype. Full SLoPS would be over-engineering for a home gateway demo.

---

## 🟢 Already Implemented (No Gap)

| CONTEXT Recommendation | Status | Implementation |
|---|---|---|
| netns+veth testbed topology | ✅ | `testbed/setup_topo.sh` |
| `teardown.sh` for cleanup | ✅ | `testbed/teardown.sh` |
| IPv4+IPv6 addresses on namespaces | ✅ | `fd00:X::/64` addresses in setup script |
| Link estimator with ground truth verification | ✅ | `estimator/assert_within_tolerance.py` |
| Classifier uses only L3/L4 headers, no payload | ✅ | `runtime_classifier.py` — IP header fields only |
| Confidence exposure in classifier output | ✅ | Returns `confidence` + `needs_confirmation` |
| `POST /override` for misclassification correction | ✅ | `api/server.py` endpoint |
| CAKE DiffServ4 enforcement | ✅ | `enforcement/apply_cake.sh` |
| `tc qdisc show` for judge verification | ✅ | Documented in README verification steps |
| Automated baseline vs optimized experiments | ✅ | `experiments/run_baseline.sh` + `run_optimized.sh` |
| Dashboard with all 6 metrics | ✅ | `dashboard/dashboard_server.py` — Chart.js |
| Jain's Fairness Index | ✅ | `dashboard/metrics_collector.py` |
| Adaptation speed (mid-test bandwidth drop) | ✅ | `experiments/test_scenario2_wan_drop.sh` |
| Rollback with checkpoint/tentative/permanent | ✅ | `policy_engine/rollback_manager.py` — Koo & Toueg inspired |
| `.env.example` with dummy creds | ✅ | `.env.example` exists with placeholders |
| `THIRD_PARTY_LICENSES.md` | ✅ | 10 components documented |
| XGBoost vs heuristic baseline comparison | ✅ | `compare_classifiers.py` — 93.7% vs 99.1% |
| Laya for NLP intent parsing | ✅ | `api/intent_parser.py` + fallback |
| Confidence-gated intent handling | ✅ | `intent_parser.py` uses 0.70 threshold + `needs_confirmation` |
| NetMatrix-style features (total_length, ttl, inter_arrival_ms) | ✅ | `runtime_classifier.py` + `training_data.csv` |
| Timer-based auto-expiry for temporary intents | ✅ | `policy_engine/intent_scheduler.py` |
| One-command system startup | ✅ | `start_all.sh` |
| Architecture diagram | ✅ | `docs/architecture.svg` + `.png` + `.md` |
| Known limitations section | ✅ | `docs/known_limitations.md` (8 items) |

---

## Priority-Ordered Action Items

| # | Item | Effort | Impact |
|---|---|---|---|
| 1 | Add `.env` to `.gitignore` | 30 sec | Prevents accidental secret commit |
| 2 | Add explicit AI framing statement to README | 5 min | Prevents judges from misunderstanding AI contribution |
| 3 | Create `REFERENCES.md` with BibTeX citations | 15 min | Academic rigor; shows research awareness |
| 4 | Create `inject_failure.sh` script | 10 min | Lets judges verify rollback is real |
| 5 | Create `reset_env.sh` script | 5 min | One-command environment reset |
| 6 | Add downstream QoS effect comparison | 30-60 min | Shows classifier accuracy → real latency improvement |
