
# End-to-End Implementation Plan: Adaptive QoS Engine (PS3)

**Document Reference:** `IMPLEMENTATION_PLAN.md`  
**Target Specification:** `ps3.md` & `PS3_COMPLIANCE_CRITICAL_ANALYSIS.md`  
**Execution Standard:** Zero-Hallucination, Step-by-Step Verifiable Milestones  

---

## Architecture Overview of Target End-to-End System

```
                  ┌──────────────────────────────────────────────┐
                  │          FastAPI User Intent & UI            │
                  │   (/intent, /override, /status, /dashboard)  │
                  └──────────────┬───────────────────────────────┘
                                 │ Intent & Overrides
                                 ▼
┌──────────────────┐    ┌────────────────────────────────────────┐
│  Online Sniffer  │───►│    Unified QoS Controller Daemon       │
│(IPv4/v6 Headers) │    │  (controller_daemon.py)                │
└────────┬─────────┘    │  - Real-time Flow Table Manager        │
         │ Packets      │  - XGBoost Inference (xgb_model.pkl)   │
         ▼              │  - Passive/Lightweight Link Estimator  │
┌──────────────────┐    │  - Dynamic Policy Engine & Scheduler   │
│  iptables/tc     │◄───│  - Bounded Rollback & QoE Health Check │
│ DSCP Packet Mark │    └──────────────────┬─────────────────────┘
└────────┬─────────┘                       │
         │ Marked packets                  │ tc cake change
         ▼                                 ▼
┌────────────────────────────────────────────────────────────────┐
│             Linux CAKE qdisc (DiffServ4 Tins)                  │
│       [Voice (EF)] [Video (AF41)] [BestEffort] [Bulk (CS1)]    │
└────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Real-Time Flow Classification & Online Inference Pipeline

### Objective
Transition the offline XGBoost model (`classifier/xgb_model.pkl`) into an active, real-time flow classification engine that inspects headers (IPv4 + IPv6), extracts NetMatrix features without inspecting payloads, computes class probabilities, and supports dynamic runtime overrides.

---

### Step 1.1: Multi-Protocol (IPv4 & IPv6) Header Feature Extractor
* **File to Modify/Create:** `classifier/runtime_classifier.py`
* **Implementation Details:**
  - Create a packet capture engine using Scapy or raw sockets on `veth-lan1-gw` and `veth-lan2-gw` (gateway LAN interfaces).
  - Explicitly handle both `scapy.layers.inet.IP` (IPv4) and `scapy.layers.inet6.IPv6` (IPv6).
  - Extract flow 5-tuple: `(src_ip, dst_ip, src_port, dst_port, protocol)`.
  - Maintain a rolling sliding window of the last $N$ packets per flow to compute:
    - Packet total length (bytes)
    - IP TTL / IPv6 Hop Limit
    - Inter-arrival time (milliseconds)
  - Zero payload reading or decryption (strictly enforces Constraint C1).
* **Verification Command:**
  ```bash
  sudo ip netns exec gw python3 -c "
  from classifier.runtime_classifier import test_sniffer
  test_sniffer(duration=5)
  "
  ```
* **Success Criteria:** Captures packets from both IPv4 (`ping 10.0.3.2`) and IPv6 (`ping6 fd00:3::2`) without throwing exceptions, correctly printing 5-tuple, length, and inter-arrival time.

---

### Step 1.2: Online XGBoost Inference & Confidence Scoring
* **File to Modify/Create:** `classifier/runtime_classifier.py`
* **Implementation Details:**
  - Load `classifier/xgb_model.pkl` (containing `model` and `label_encoder`).
  - Implement `classify_flow(flow_features) -> dict`:
    - Computes `predict_proba()` to extract class probabilities.
    - Returns predicted class (`video_conference`, `gaming`, `bulk_download`) and `confidence: float`.
    - If `confidence < 0.70`, flags `needs_confirmation: True` (fulfilling Constraint C5).
* **Verification Command:**
  ```bash
  python3 -c "
  from classifier.runtime_classifier import FlowClassifier
  clf = FlowClassifier('classifier/xgb_model.pkl')
  res = clf.predict_sample(total_length=220, ttl=64, inter_arrival_ms=0.4)
  print('Result:', res)
  assert res['class'] == 'video_conference'
  assert res['confidence'] > 0.7
  print('Inference verification: PASS ✅')
  "
  ```
* **Success Criteria:** Correctly loads pickled model, executes prediction under 5ms per sample, and returns confidence probability.

---

### Step 1.3: Real-Time Flow Table & Override Registry
* **File to Modify/Create:** `classifier/flow_table.py`
* **Implementation Details:**
  - In-memory thread-safe flow table tracking active flows: `flow_id -> {class, confidence, packet_count, last_seen, overridden}`.
  - Expose `override_classification(flow_id, corrected_class)`:
    - Replaces predicted class with manual label immediately.
    - Sets `overridden: True` and confidence to `1.0`.
  - Flow cleanup: Evict flows inactive for $> 30$ seconds.
* **Verification Command:**
  ```bash
  python3 -c "
  from classifier.flow_table import FlowTable
  ft = FlowTable()
  ft.update_flow('10.0.1.2:5201', 'bulk_download', 0.85)
  assert ft.get('10.0.1.2:5201')['class'] == 'bulk_download'
  ft.override('10.0.1.2:5201', 'video_conference')
  assert ft.get('10.0.1.2:5201')['class'] == 'video_conference'
  print('Flow table & override verification: PASS ✅')
  "
  ```
* **Success Criteria:** Flow table correctly updates, overrides take effect instantly, and inactive flows expire gracefully.

---

## Phase 2: Kernel Enforcement & Packet Marking (CAKE DiffServ4 Tins)

### Objective
Enable true priority scheduling across the 4 CAKE tiers (Voice, Video, Best Effort, Bulk) by marking packets dynamically at the gateway using `iptables` / DSCP mangle rules.

---

### Step 2.1: Gateway DSCP Mangle Rule Manager
* **File to Modify/Create:** `enforcement/dscp_marker.py`
* **Implementation Details:**
  - Create dynamic `iptables` / `ip6tables` PREROUTING rules in `gw` namespace:
    - `video_conference` $\rightarrow$ DSCP `AF41` (`0x22`) or `CS5` (maps to CAKE Video tin).
    - `gaming` $\rightarrow$ DSCP `EF` (`0x2E`) (maps to CAKE Voice/Interactive tin).
    - `bulk_download` $\rightarrow$ DSCP `CS1` (`0x08`) (maps to CAKE Bulk tin).
    - default / unclassified $\rightarrow$ DSCP `CS0` (`0x00`) (Best Effort tin).
  - Provide functions `mark_flow(flow_id, traffic_class)` and `clear_all_marks()`.
* **Verification Command:**
  ```bash
  sudo ip netns exec gw iptables -t mangle -F
  sudo python3 -c "
  from enforcement.dscp_marker import DscpMarker
  marker = DscpMarker(namespace='gw')
  marker.mark_ip('10.0.1.2', 'video_conference')
  "
  sudo ip netns exec gw iptables -t mangle -L -n -v | grep -E "DSCP|0x2"
  ```
* **Success Criteria:** `iptables -t mangle` shows rule active with target `DSCP set` matching class AF41/CS5.

---

### Step 2.2: Verification of CAKE DiffServ4 Tin Utilization
* **File to Modify/Create:** `enforcement/verify_tins.sh`
* **Implementation Details:**
  - Generate concurrent flows from `lan1` (marked as video) and `lan2` (marked as bulk).
  - Parse `tc -s qdisc show dev veth-gw-wan` to inspect CAKE's internal per-tin packet and byte counters:
    - Tin 0: Bulk
    - Tin 1: Best Effort
    - Tin 2: Video
    - Tin 3: Voice
* **Verification Command:**
  ```bash
  chmod +x enforcement/verify_tins.sh
  sudo ./enforcement/verify_tins.sh
  ```
* **Success Criteria:** `tc -s qdisc` output displays non-zero packet counts across **both** the Video tin and Bulk tin (proves DiffServ4 classification is actively functioning in the Linux kernel).

---

## Phase 3: Intent API Wiring, Session Scheduler & Starvation Protection

### Objective
Connect the REST API (`api/server.py`) directly to the policy engine, implement a time-bound priority session scheduler with automatic expiration, and enforce starvation prevention for low-priority bulk traffic.

---

### Step 3.1: Wire REST API to QoS Policy Engine
* **File to Modify:** `api/server.py`
* **Implementation Details:**
  - Import `FlowTable`, `PolicyEngine`, and `RollbackManager`.
  - In `POST /intent`:
    - Parse request using Laya (or fallback).
    - If `action == "prioritize"`, register the temporary priority intent in the active policy engine.
    - Trigger immediate DSCP marking and bandwidth reconfiguration.
  - In `POST /override`:
    - Call `flow_table.override(req.flow_id, req.corrected_class)`.
    - Immediately re-mark active flow in `iptables`.
* **Verification Command:**
  ```bash
  # In terminal 1: start server
  # In terminal 2:
  curl -s -X POST http://127.0.0.1:8000/intent -H "Content-Type: application/json" \
    -d '{"text": "prioritize video conference for 10 minutes"}' | jq .
  curl -s http://127.0.0.1:8000/status | jq .
  ```
* **Success Criteria:** `/status` endpoint shows `active_intent: {"class": "video_conference", "action": "prioritize"}` and the gateway's active policy reflects the intent.

---

### Step 3.2: Asynchronous Intent Expiration Scheduler
* **File to Modify/Create:** `policy_engine/intent_scheduler.py`
* **Implementation Details:**
  - Background `asyncio` or threading timer tracking active temporary intents:
    - `intent_id`, `class`, `start_time`, `duration_sec`, `expired_at`.
  - When timer expires:
    - Logs expiration event.
    - Reverts DSCP boost for the prioritized class.
    - Restores default baseline QoS policy safely.
* **Verification Command:**
  ```bash
  python3 -c "
  import time
  from policy_engine.intent_scheduler import IntentScheduler
  s = IntentScheduler()
  s.schedule_intent('video_conference', duration_sec=3)
  assert s.is_active('video_conference') == True
  time.sleep(4)
  assert s.is_active('video_conference') == False
  print('Scheduler expiration verification: PASS ✅')
  "
  ```
* **Success Criteria:** Priority status transitions from active to expired automatically once `duration_sec` has passed.

---

### Step 3.3: Anti-Starvation Guard (Constraint C4 & Evaluation Criteria)
* **File to Modify:** `policy_engine/policy_rules.py`
* **Implementation Details:**
  - CAKE natively enforces DRR++ across flows, but when strict priority tiers are engaged, bulk traffic must retain guaranteed progress.
  - Define minimum bandwidth guarantees:
    - Absolute safety floor of 5 Mbps on total WAN link (already partially present).
    - Ensure Bulk tin allocation never drops below $\min(20\% \times \text{WAN Bandwidth}, 2\text{ Mbps})$.
    - If bulk throughput falls to 0 while active, policy engine drops priority boost to prevent starvation.
* **Verification Command:**
  ```bash
  python3 -c "
  from policy_engine.policy_rules import decide_policy
  decision = decide_policy(available_bandwidth_mbps=10, active_flows=[{'class': 'video_conference'}], user_intent={'action': 'prioritize', 'class': 'video_conference'})
  assert decision['bandwidth_mbit'] >= 5
  assert 'starvation_floor_active' in decision
  print('Starvation guard verification: PASS ✅')
  "
  ```
* **Success Criteria:** Policy calculations strictly preserve the safety floor and calculate fair minimum allocations.

---

## Phase 4: Non-Intrusive Link Estimator & Closed-Loop Controller Daemon

### Objective
Replace destructive link-saturating iperf3 probes with a passive + controlled estimator, and bind all modules into an autonomous closed-loop controller daemon (`controller_daemon.py`).

---

### Step 4.1: Passive Throughput Tracking & Low-Overhead Estimator
* **File to Modify/Create:** `estimator/passive_estimator.py`
* **Implementation Details:**
  - Sample network interface counters (`/proc/net/dev` or `tc -s`) on `veth-gw-wan` every second:
    $$\text{Current Throughput} = \frac{\Delta \text{Bytes} \times 8}{\Delta t}$$
  - Track peak observed rate and link utilization.
  - If link is saturated ($> 90\%$ capacity for $\ge 3$s) and queue backlog grows, detect bottleneck capacity.
  - Keep active probing (`link_estimator.py`) strictly as an on-demand fallback, capped to low-rate bursts (under 500ms) to avoid user-visible bufferbloat.
* **Verification Command:**
  ```bash
  sudo ip netns exec gw python3 -c "
  from estimator.passive_estimator import PassiveEstimator
  import time
  pe = PassiveEstimator('veth-gw-wan')
  time.sleep(2)
  print('Observed rate:', pe.get_current_rate_mbps(), 'Mbps')
  "
  ```
* **Success Criteria:** Accurately reads interface throughput without spawning separate client/server saturation processes.

---

### Step 4.2: Unified Autonomous Controller Daemon
* **File to Modify/Create:** `controller_daemon.py`
* **Implementation Details:**
  - Runs in the background with continuous control loop (every 3–5 seconds):
    1. **Observe:** Polls `PassiveEstimator` for current WAN throughput & `FlowTable` for active flows.
    2. **Detect:** Checks if WAN capacity has dropped (e.g. from 100 Mbps $\rightarrow$ 20 Mbps) or new flows appeared.
    3. **Decide:** Calls `decide_policy()` with link rate, active flows, and active user intents.
    4. **Act (Remediate):** Calls `RollbackManager.apply_policy()` to adjust CAKE shaping bandwidth.
    5. **Verify:** Runs `health_check()`. If unhealthy, triggers `RollbackManager.rollback()` back to last known safe state.
* **Verification Command:**
  ```bash
  sudo python3 controller_daemon.py --test-cycle
  ```
* **Success Criteria:** Single test cycle executes all 5 steps end-to-end, logs transitions, and cleanly leaves qdisc in valid state.

---

### Step 4.3: Closed-Loop QoE Health Check & Bounded Rollback
* **File to Modify:** `policy_engine/rollback_manager.py`
* **Implementation Details:**
  - Upgrade `health_check()` to measure real QoE under current load:
    - Instead of idle ping with rigged 0.05ms threshold:
    - Measures RTT latency (must stay $< 50$ms under load).
    - Measures packet drops on shaped interface (must not exceed $5\%$ loss rate).
    - If health check fails $\ge 2$ consecutive cycles, reverts policy to `last_good_config` and logs rollback event.
* **Verification Command:**
  ```bash
  sudo python3 policy_engine/test_rollback_scenario.py
  ```
* **Success Criteria:** Test fails gracefully when an unviable policy (e.g. 0.5 Mbps during heavy load) is applied, cleanly reverting to previous known-good configuration without user intervention.

---

## Phase 5: Complete 6-Metric Live Dashboard

### Objective
Fulfill the mandatory acceptance requirement in `ps3.md` Section 5 by implementing a live dashboard that displays all 6 specified metrics: **Latency, Jitter, Packet Loss, Throughput, Queue Depth, and Fairness**.

---

### Step 5.1: Multi-Metric Collector Extension
* **File to Modify:** `dashboard/metrics_collector.py`
* **Implementation Details:**
  - Update `get_cake_stats()`: Parse `backlog <bytes>b <packets>p` from `tc -s qdisc show dev veth-gw-wan` to extract **Queue Depth**.
  - Update `get_latency()`: Extract `avg_ms` (**Latency**), `jitter_ms` (**Jitter**), and compute `loss_pct` (**Packet Loss**).
  - Integrate passive throughput: Calculate **Throughput** (Mbps) per interface and per flow.
  - Calculate **Jain's Fairness Index** across active LAN IP throughputs:
    $$\mathcal{J}(x_1, x_2, \dots, x_n) = \frac{\left(\sum x_i\right)^2}{n \sum x_i^2}$$
  - Return complete dictionary containing all 6 metrics in `collect_snapshot()`.
* **Verification Command:**
  ```bash
  sudo python3 -c "
  from dashboard.metrics_collector import collect_snapshot
  snap = collect_snapshot()
  keys = ['latency_ms', 'jitter_ms', 'loss_pct', 'throughput_mbps', 'queue_depth_pkts', 'fairness_index']
  print('Snapshot:', snap)
  for k in keys:
      assert k in snap, f'Missing metric {k}'
  print('All 6 metrics present: PASS ✅')
  "
  ```
* **Success Criteria:** Every snapshot includes all 6 metrics populated with real numbers.

---

### Step 5.2: 6-Chart Responsive Dashboard Frontend
* **File to Modify:** `dashboard/dashboard_server.py`
* **Implementation Details:**
  - Upgrade web interface to a 6-card responsive grid:
    1. **Latency (ms)** — Line chart
    2. **Jitter (ms)** — Line chart
    3. **Packet Loss (%)** — Line chart
    4. **Throughput (Mbps)** — Stacked flow throughput line chart
    5. **Queue Depth (Packets / Bytes)** — Area chart
    6. **Jain's Fairness Index ($0.0 - 1.0$)** — Gauge or line chart
  - Auto-refresh via `/api/metrics` every 2 seconds.
* **Verification Command:**
  ```bash
  # Start dashboard server on port 8001
  python3 dashboard/dashboard_server.py &
  PID=$!
  sleep 2
  curl -s http://127.0.0.1:8001/ | grep -E "latencyChart|jitterChart|lossChart|throughputChart|queueChart|fairnessChart"
  kill $PID
  ```
* **Success Criteria:** HTML payload contains DOM elements and Chart.js initialization logic for all 6 metrics.

---

## Phase 6: Automated Scenarios & Reproducible Benchmark Suite

### Objective
Implement and automate the 3 illustrative scenarios from `ps3.md`, verify the baseline vs. optimized outcomes, and provide a single-command demonstration script.

---

### Step 6.1: Scenario 1 Automated Test (ISO Download vs Video Conference)
* **File to Modify/Create:** `experiments/test_scenario1_bulk_vs_video.sh`
* **Implementation Details:**
  - Launch video conference traffic stream (`traffic_generators.py:generate_video_conference` with 200-byte UDP packets).
  - Launch concurrent ISO bulk download (`iperf3` TCP max rate).
  - Test under:
    1. Baseline (Unmanaged NetEm FIFO queue with bufferbloat)
    2. Optimized (Adaptive QoS Engine with CAKE + DiffServ4 video priority)
  - Measure call latency, jitter, loss, and bulk throughput.
* **Verification Command:**
  ```bash
  chmod +x experiments/test_scenario1_bulk_vs_video.sh
  sudo ./experiments/test_scenario1_bulk_vs_video.sh
  ```
* **Success Criteria:** Output report demonstrates $> 90\%$ reduction in video latency and jitter while bulk download continues to make reasonable progress.

---

### Step 6.2: Scenario 2 Automated Test (Dynamic WAN Drop 100 Mbps $\rightarrow$ 20 Mbps)
* **File to Modify/Create:** `experiments/test_scenario2_wan_drop.sh`
* **Implementation Details:**
  - Start controller daemon with WAN link initialized at 100 Mbps.
  - Induce sudden bandwidth collapse to 20 Mbps via `wan_simulator.py`.
  - Verify that:
    1. Passive/link estimator detects rate collapse within $5$ seconds.
    2. Controller recalculates CAKE shaping rate down to $\approx 19$ Mbps ($0.95 \times \text{capacity}$).
    3. Queue depth stays bounded without building a massive bufferbloat queue.
* **Verification Command:**
  ```bash
  chmod +x experiments/test_scenario2_wan_drop.sh
  sudo ./experiments/test_scenario2_wan_drop.sh
  ```
* **Success Criteria:** Script logs show initial 100Mbit shaping $\rightarrow$ detection of drop $\rightarrow$ automated adjustment to $\le 20$Mbit, with queue depth remaining below 50 packets.

---

### Step 6.3: Scenario 3 Multi-Device Test (3 Video Streams + 1 Gaming Device)
* **File to Modify/Create:** `testbed/setup_topo_scenario3.sh` and `experiments/test_scenario3_multi_device.sh`
* **Implementation Details:**
  - Dynamically instantiate `lan3` and `lan4` namespaces in the testbed (representing 3 TVs + 1 gaming PC).
  - Run 3 concurrent streaming video flows and 1 gaming UDP flow (60-byte high-frequency packets).
  - Compare baseline FIFO vs. QoS Engine:
    - Compute Jain's Fairness Index across all 4 devices.
    - Measure gaming latency and jitter.
* **Verification Command:**
  ```bash
  chmod +x experiments/test_scenario3_multi_device.sh
  sudo ./experiments/test_scenario3_multi_device.sh
  ```
* **Success Criteria:** Gaming latency remains $< 25$ms while all 3 video streams maintain stable throughput; Jain's Fairness Index is $\ge 0.85$.

---

### Step 6.4: Unified Demonstration Script (`demo_all.sh`)
* **File to Create:** `demo_all.sh` (Workspace root)
* **Implementation Details:**
  - Fulfills `ps3.md` Acceptance Evidence [E8]:
    *"Automated or scripted demonstration that can reset the environment, introduce the selected condition, collect evidence and generate a result report."*
  - Automatically executes:
    1. Teardown & clean setup of topology (`setup_topo.sh`).
    2. Start of controller daemon and dashboard server.
    3. Execution of Scenario 1, Scenario 2, and Scenario 3.
    4. Aggregation of metrics into a clean summary markdown report (`FINAL_DEMO_REPORT.md`).
* **Verification Command:**
  ```bash
  chmod +x demo_all.sh
  sudo ./demo_all.sh --dry-run
  ```
* **Success Criteria:** Script validates prerequisites, checks topology, and displays execution plan without errors.

---

## Phase 7: Architecture Diagrams, Documentation & Final Audit

### Objective
Complete all documentation requirements, resolve broken references, provide explicit state-machine and component diagrams, and conduct the final evaluation audit.

---

### Step 7.1: Architecture Diagram Asset Creation
* **File to Create:** `docs/architecture.png` and `docs/architecture.svg`
* **Implementation Details:**
  - Fix broken reference in `README.md` (which currently links to a missing file).
  - Render a clear, publication-quality architecture diagram covering:
    - **Device Layer:** LAN hosts (`lan1`, `lan2`, `lan3`, `lan4`).
    - **Edge / Gateway Layer:** Linux Netfilter/iptables DSCP mangle, CAKE qdisc.
    - **Analytics & AI Layer:** XGBoost inference, NetMatrix feature extractor.
    - **Data Layer:** Metrics collector, flow table, logs.
    - **Control Layer:** Rollback manager, policy rules, scheduler.
    - **User Interface Layer:** FastAPI REST endpoints, live Chart.js dashboard.
* **Verification Command:**
  ```bash
  test -f docs/architecture.png && test -f docs/architecture.svg
  echo "Architecture diagram assets: PASS ✅"
  ```
* **Success Criteria:** Both files exist, are valid image assets, and accurately depict all 6 architectural components specified in `ps3.md` [E6].

---

### Step 7.2: Formal Component Specification in Documentation
* **File to Modify:** `docs/architecture.md`
* **Implementation Details:**
  - Explicitly document for each module:
    - **Inputs:** Schema, data types, and transport.
    - **Outputs:** State changes, return structures.
    - **State Transitions:** Finite state diagram (e.g. Idle $\rightarrow$ Probing $\rightarrow$ Policy Calculated $\rightarrow$ Tentative Applied $\rightarrow$ Permanent / Rolled Back).
    - **Failure Modes:** Timeout handling, invalid rate fallback, kernel error recovery.
    - **Success Conditions:** Quantitative QoE criteria.
* **Verification Command:**
  ```bash
  grep -E "Inputs|Outputs|State Transitions|Failure Handling|Success Conditions" docs/architecture.md
  ```
* **Success Criteria:** All 5 required sections are present and fully articulated for every module.

---

### Step 7.3: Final Dual-Verification Acceptance Audit
* **Implementation Details:**
  - Run `compare_classifiers.py` (AI vs baseline).
  - Run `demo_all.sh` (Full network scenario suite).
  - Check `curl http://127.0.0.1:8001/api/metrics` (Verify 6 dashboard metrics).
  - Verify zero unhandled exceptions, zero secret leaks, and clean teardown.
* **Verification Command:**
  ```bash
  sudo ./testbed/teardown.sh
  sudo ./start_all.sh
  sudo ./testbed/verify_connectivity.sh
  ```
* **Success Criteria:** 100% pass across all connectivity, classification, shaping, rollback, and API verification tests.

---

## Phase Execution Dependency & Tracking Matrix

| Phase | Description | Prerequisite | Verification Milestone |
| :---: | :--- | :---: | :--- |
| **Phase 1** | Real-Time Flow Classifier (XGBoost Online) | Existing venv & model | `classifier/runtime_classifier.py` classifies live packets with confidence |
| **Phase 2** | Kernel DSCP Marking & CAKE DiffServ4 | Phase 1 | `tc -s qdisc` shows packet counters incrementing across multiple tins |
| **Phase 3** | Intent API Wiring & Session Scheduler | Phase 2 | `POST /intent` changes DSCP marking and reverts automatically after timer |
| **Phase 4** | Closed-Loop Autonomous Controller Daemon | Phases 1–3 | `controller_daemon.py` detects link changes and applies safe shaping |
| **Phase 5** | Complete 6-Metric Live Dashboard | Phase 4 | Dashboard renders 6 Chart.js graphs populated from live traffic |
| **Phase 6** | Automated Scenarios 1, 2, 3 & Demo Script | Phases 1–5 | `demo_all.sh` runs all 3 scenarios and outputs comparative markdown report |
| **Phase 7** | Diagrams, Formal Docs & Final Audit | Phases 1–6 | `docs/architecture.png` exists; 100% compliance on all ps3.md items |

---

## Guidelines for Next Steps
Proceed linearly through Phase 1 through Phase 7. Execute the verification command after **each step** before moving to the next.
