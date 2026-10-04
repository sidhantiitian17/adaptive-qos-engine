# Critical End-to-End Compliance Analysis: PS3 Adaptive QoS Engine

**Document Status:** Final Audit Report  
**Target Specification:** `ps3.md` (Adaptive QoS Engine for Mixed Home Broadband Traffic)  
**Evaluation Standard:** Dual Independent Cross-Verification Protocol  
**Repository Working Directory:** `/home/prashast/adaptive-qos-engine`  

---

## 1. Executive Summary & Verdict

### Final Verdict: **NOT COMPLETELY SOLVED END-TO-END (62% Completed / Substantial Disconnects Present)**

While the repository contains high-quality individual prototypes and foundational implementations for several requirements (e.g., custom kernel build for CAKE, synthetic dataset generation, offline XGBoost classifier vs. heuristic baseline, standalone NetEm WAN simulation, and baseline vs. CAKE latency benchmarks), **the codebase does NOT solve the problem completely end-to-end as an autonomous, closed-loop adaptive QoS system**.

### Key Architectural Realities Discovered:
1. **The AI Model is Never Deployed at Runtime:** The trained XGBoost model (`classifier/xgb_model.pkl`) is generated offline and **never loaded anywhere** in the data or control path. The integrated engine (`policy_engine/integrated_engine.py`) explicitly uses hardcoded mock flow dictionaries.
2. **Missing Packet Marking (Inactive DiffServ Tins):** The enforcement module applies CAKE with `diffserv4`, but the codebase contains **zero** packet marking mechanisms (`iptables`, `nftables`, or `tc filter ... pedit/skbedit`). Without DSCP marks, all traffic lands in CAKE's default "Best Effort" tin. The benchmark improvements in `experiments/` are entirely due to CAKE's generic 5-tuple FQ-CoDel fair queuing, not traffic classification or DiffServ prioritization.
3. **Intent API is Severed from Enforcement:** The FastAPI intent endpoint (`api/server.py`) parses natural language into JSON via Laya/fallback, but **never invokes** the policy engine, rollback manager, or Linux `tc`. It is a standalone REST endpoint with zero influence over network queueing.
4. **Dashboard Omits 4 of 6 Required Metrics:** `ps3.md` mandates a dashboard for *"latency, jitter, loss, throughput, queue depth and fairness"*. The implemented dashboard only displays latency and packet drop count; **jitter, throughput, queue depth, and fairness (Jain's index) are completely absent from the UI**.
5. **No Continuous Closed-Loop Controller:** There is no daemon or daemonized control loop linking link estimation, traffic classification, policy decisions, and enforcement. The components exist as fragmented scripts executed manually.
6. **Use Cases 2 and 3 are Incomplete:** The WAN drop scenario (100 Mbps $\rightarrow$ 20 Mbps) is only a standalone simulator function with no automated controller adaptation test, and the multi-TV + gaming scenario (Use Case 3) is completely unbuilt.

---

## 2. Methodology & Dual Cross-Verification Protocol

To ensure 100% rigorous evaluation without false positives or false negatives, every requirement was evaluated through a **three-stage audit process**:

```
[ Stage 1: Initial Requirement Mapping ]
       │ (Map ps3.md line-by-line to codebase files)
       ▼
[ Stage 2: Cross-Verification Pass 1 (Static AST & Traceability Audit) ]
       │ (Inspect imports, function calls, dataflow, shell piping, dead code)
       ▼
[ Stage 3: Cross-Verification Pass 2 (Dynamic & Semantic Operational Audit) ]
       │ (Verify runtime dependencies, kernel qdisc mechanics, testbed fidelity)
       ▼
[ Final Assessment & Remediation Matrix ]
```

---

## 3. Comprehensive Requirement-by-Requirement Audit

### 3.1. Challenge & Core Capabilities

| Requirement (`ps3.md`) | Codebase Location | Pass 1: Static Audit | Pass 2: Dynamic / Integration Audit | Compliance Status |
| :--- | :--- | :--- | :--- | :--- |
| **Classify broad traffic without reading private payloads** | `classifier/feature_extraction.py`, `train_xgboost.py` | Extracts only packet length, TTL, and inter-arrival time via Scapy. No payload inspection. | **Critical Disconnect:** Feature extraction writes to static CSV; model is trained offline. No online sniffer or runtime inference hook exists. `integrated_engine.py` uses hardcoded mock flows. | **PARTIAL** (Compliant on privacy constraint; Failed on runtime execution) |
| **Estimate link capacity** | `estimator/link_estimator.py`, `continuous_monitor.py` | Uses `iperf3 -c target -t 2 -R -J` bursts to estimate capacity. | **Operational Flaw:** Uses active saturation TCP probing, which floods the link (unrealistic for live residential broadband) and requires an `iperf3` server on the remote WAN host. Does not feed into a controller daemon. | **PARTIAL** (Tool exists; not integrated closed-loop, high-overhead probing) |
| **Apply queueing and shaping policies** | `enforcement/apply_cake.sh`, `policy_engine/rollback_manager.py` | Wraps `tc qdisc add/change ... cake bandwidth Xmbit diffserv4`. | **Flaw:** Only alters total root bandwidth. Does not configure per-class queues or set DSCP markers. DiffServ4 tins remain unutilized. | **PARTIAL** (Basic root shaping works; multi-tier class shaping absent) |
| **Verify whether policy improved user experience (Closed-Loop)** | `policy_engine/rollback_manager.py:health_check()` | Pings WAN host 3 times; checks if `avg_latency <= threshold`. | **Flaw:** A 3-packet ICMP ping on an idle link checks connectivity, not QoE improvement. Does not check interactive jitter under load or bulk progress. Line 26 in `test_rollback_scenario.py` admits threshold must be artificially rigged to 0.05ms to trigger rollback. | **PARTIAL** (Crude reachability health check; not true QoE verification) |
| **Support temporary user intent while retaining fairness** | `api/intent_parser.py`, `api/server.py`, `policy_engine/policy_rules.py` | `parse_intent()` parses natural language to dict with `duration_sec`. `policy_rules.py` appends priority metadata. | **Critical Disconnect:** API endpoint `/intent` returns JSON to client but never triggers `tc` or `policy_engine`. `apply_policy()` has no parameter for priority classes. No timer or scheduler exists to revert policy after duration. | **MISSING END-TO-END** (Parser exists; execution, enforcement, and expiry missing) |
| **Modular decomposition (inputs, outputs, states, failure, success)** | Code structure: `classifier/`, `estimator/`, `policy_engine/`, `api/` | Directories are modular. `rollback_manager.py` implements tentative/permanent states. | **Flaw:** No formal documentation of state machines, module contracts, or failure conditions across components in `docs/architecture.md`. | **PARTIAL** |
| **AI vs. Deterministic Baseline (measurable outcome)** | `classifier/compare_classifiers.py`, `baseline_heuristic.py` | Compares heuristic rule (93.7%) vs. XGBoost (99.1%) on CSV data. | **Flaw:** Measurable outcome is strictly offline classification accuracy. In the actual network experiment (`experiments/`), the AI model is **not running**. Latency reduction is purely from CAKE vs NetEm FIFO. Laya serves purely as a conversational interface. | **PARTIALLY COMPLIANT** (Comparison exists offline; does not drive network outcome) |

---

### 3.2. Illustrative Use Cases & Test Scenarios

| Scenario (`ps3.md`) | Implemented? | Codebase Evidence | Findings & Gaps |
| :--- | :--- | :--- | :--- |
| **Scenario 1: Large ISO download during video conference (limit bulk, protect call)** | **Partially** | `experiments/run_baseline.sh`, `run_optimized.sh` | Compares `iperf3` bulk TCP + ICMP `ping` under NetEm FIFO vs. CAKE. **Gap:** Uses synthetic ping rather than real video conference traffic (`generate_video_conference` from `traffic_generators.py` was not used in the experiment). Bulk queue is not explicitly limited; CAKE handles it via general flow isolation. |
| **Scenario 2: WAN bandwidth drops 100 Mbps $\rightarrow$ 20 Mbps (recalculate shaping)** | **No (Incomplete)** | `testbed/wan_simulator.py:simulate_bandwidth_drop()` | `wan_simulator.py` contains the function to drop the link rate via NetEm. **Gap:** There is no automated test or controller script that monitors this drop, recalculates shaping, and applies it to prevent queue buildup. |
| **Scenario 3: 3 TVs streaming video + 1 low-latency gaming device** | **No (Missing)** | None | **Gap:** Completely missing. The testbed only instantiates 2 LAN namespaces (`lan1`, `lan2`). There is no multi-stream simulation script or test case for this scenario. |

---

### 3.3. Constraints and Design Boundaries

| Constraint | Requirement | Status | Detailed Finding |
| :--- | :--- | :--- | :--- |
| **C1** | **Do not decrypt application traffic** | **COMPLIANT** | Feature extraction inspects only IP header fields (`total_length`, `ttl`, `inter_arrival_ms`). Zero payload parsing. |
| **C2** | **Use Linux traffic control or inspectable mechanism** | **COMPLIANT** | Utilizes Linux `tc` with `sch_cake` and `sch_netem`. |
| **C3** | **Support IPv4 and, where available, IPv6** | **PARTIALLY COMPLIANT** | Testbed (`setup_topo.sh`) configures IPv6 and default routes. Connectivity test pings IPv6. **Gaps:** `feature_extraction.py` line 19 checks `if IP in pkt:` (Scapy IPv4 only; drops IPv6 packets). `link_estimator.py`, `rollback_manager.py`, and `metrics_collector.py` hardcode IPv4 `10.0.3.2`. |
| **C4** | **Provide policy rollback and prevent starvation** | **PARTIALLY COMPLIANT** | `rollback_manager.py` implements checkpointing and fallback. `policy_rules.py` enforces a 5 Mbps safety floor. **Gaps:** Rollback health check is simplistic; no per-class minimum bandwidth guarantees to prevent bulk starvation under strict priority. |
| **C5** | **Classifiers expose confidence and allow correction** | **PARTIALLY COMPLIANT** | Laya exposes confidence scores; `/override` endpoint exists in `server.py`. **Gaps:** `/override` only appends to an in-memory Python list. It does not retrain XGBoost, update flow rules, or modify packet handling. |
| **C6** | **Document third-party licenses** | **COMPLIANT** | `THIRD_PARTY_LICENSES.md` documents all libraries and tools (GPLv2, Apache 2.0, BSD-3, MIT). |
| **C7** | **Include generated data and impairment settings** | **COMPLIANT** | `training_data.csv`, `traffic_generators.py`, and NetEm settings in `wan_simulator.py` are present. |
| **C8** | **Label emulated hardware and explain limitations** | **COMPLIANT** | Explicitly labeled and explained in `docs/known_limitations.md`. |
| **C9** | **No credentials or private keys committed** | **COMPLIANT** | Repository contains zero API keys, certificates, or credentials. |
| **C10** | **Automated remediation bounded, observable, reversible** | **PARTIALLY COMPLIANT** | `rollback_manager.py` provides bounded, logged, reversible state rollback. **Gap:** Not running autonomously in an active control loop. |

---

### 3.4. Expected Outputs & Acceptance Evidence

| Output Item (`ps3.md`) | Status | Verification Detail |
| :--- | :--- | :--- |
| **E1: Traffic-class and link-capacity estimator** | **Partial** | Offline classifier + active iperf3 estimator. Not connected to live flows. |
| **E2: Dynamic QoS policy engine and enforcement** | **Partial** | Modules exist, but operate statically or via single-shot manual runs. |
| **E3: Dashboard for latency, jitter, loss, throughput, queue depth, fairness** | **FAILED (Major Gaps)** | **Missing 4 of 6 metrics:** Dashboard HTML/JS renders only `latencyChart` and `dropChart`. Jitter, throughput, queue depth, and Jain's fairness index are not rendered. |
| **E4: Automated baseline-vs-optimized experiments** | **COMPLIANT** | `experiments/run_baseline.sh`, `run_optimized.sh`, `generate_report.py` provide a clean comparison. |
| **E5: API or UI for temporary service intent** | **Partial** | API exists at `api/server.py`, but has no UI and is disconnected from enforcement. |
| **E6: Architecture diagram (device, edge, network, data, analytics, UI)** | **Partial** | Minimal ASCII diagram in `docs/architecture.md`. `README.md` references `docs/architecture.png` which **does not exist** on disk. |
| **E7: Setup guide (prerequisites, versions, commands, verification)** | **COMPLIANT** | `README.md`, `requirements.txt`, and `docs/kernel_build.md` are well-documented. |
| **E8: Automated or scripted demonstration (reset, condition, evidence, report)** | **Partial** | Fragmented across `start_all.sh` and `experiments/run_baseline.sh`. No single unified demo script. |
| **E9: Known-limitations section** | **COMPLIANT** | `docs/known_limitations.md` is thorough and accurately details WSL2, NetEm, and emulation constraints. |

---

### 3.5. Evaluation Criteria Audit

1. **Accuracy of classification and link estimation:**
   - Classification accuracy: 99.1% on synthetic dataset (`training_data.csv`). Real-time classification accuracy on live, un-shaped traffic is unverified.
   - Link estimation accuracy: High in testbed via iperf3, but operationally problematic due to active bandwidth saturation.
2. **Reduction in interactive latency, jitter, packet loss:**
   - **Demonstrated successfully** in `experiments/generate_report.py`:
     - Average Latency: 965.6 ms $\rightarrow$ 20.5 ms (**97.9% reduction**)
     - Jitter: 566.9 ms $\rightarrow$ 0.18 ms (**100% reduction**)
     - *Caveat:* This reduction is entirely the property of Linux CAKE FQ-CoDel vs. unmanaged NetEm FIFO bufferbloat, not the adaptive policy engine.
3. **Fairness and absence of starvation:**
   - CAKE ensures per-flow fairness via DRR++.
   - However, the codebase does not measure, chart, or report Jain's Fairness Index during experiments, despite having a helper function in `metrics_collector.py`.
4. **Adaptation speed and policy stability:**
   - **Unmeasured & Unimplemented:** Because there is no continuous feedback loop running between the estimator and policy engine, adaptation speed (time to re-shape when link degrades) is never tested or benchmarked.
5. **CPU overhead, reproducibility, and clarity:**
   - High reproducibility for the offline and benchmark scripts.
   - CPU overhead of active iperf3 probing every few seconds is severe; passive or lightweight probing was not implemented.

---

## 4. Deep-Dive: The 6 Core Architectural Disconnects

### Disconnect 1: The Orphaned XGBoost Model (`xgb_model.pkl`)
* **Code Location:** `classifier/train_xgboost.py` (lines 56–58) vs `policy_engine/integrated_engine.py` (lines 22–27).
* **The Reality:** `train_xgboost.py` saves `xgb_model.pkl`. A search across the entire repository for `xgb_model.pkl`, `pickle.load`, or `joblib.load` reveals **zero** occurrences outside the training script itself.
* **Impact:** In `policy_engine/integrated_engine.py`, the active flows are hardcoded:
  ```python
  # Line 22 of policy_engine/integrated_engine.py
  # Step 2: Mock classifier output (real version would use trained XGBoost model
  # on live captured packets; for this integration test we use a fixed scenario)
  active_flows = [
      {"flow_id": "f1", "class": "video_conference", "confidence": 0.9},
      {"flow_id": "f2", "class": "bulk_download", "confidence": 0.85},
  ]
  ```
  The trained classifier is completely disconnected from the engine.

### Disconnect 2: No Packet Marking for CAKE DiffServ4 Tins
* **Code Location:** `enforcement/apply_cake.sh`, `policy_engine/rollback_manager.py`.
* **The Reality:** CAKE is configured with `diffserv4`. In Linux networking, CAKE uses DiffServ tins by inspecting the DSCP field in the IP header (CS1=Bulk, CS0=Best Effort, AF4x=Video, EF=Voice).
* **Impact:** Grepping for `iptables`, `nftables`, `dscp`, `tos`, or `skbedit` yields **zero results**. Since standard application traffic has DSCP = 0, **100% of packets enter the Best Effort tin**. The DiffServ tiers are never utilized, rendering the priority classification logic ineffective in the data plane.

### Disconnect 3: The Severed Intent API
* **Code Location:** `api/server.py` (lines 29–39).
* **The Reality:** The `/intent` route calls `parse_intent(req.text)` and simply returns the dictionary response to the HTTP client:
  ```python
  @app.post("/intent")
  def submit_intent(req: IntentRequest):
      try:
          result = parse_intent(req.text)
          result["source"] = "laya"
      except Exception as e:
          ...
      return result
  ```
* **Impact:** It never interacts with `policy_rules.py`, `rollback_manager.py`, or `tc`. Furthermore, there is no scheduler or asynchronous worker to expire the requested temporary intent after `duration_sec` expires.

### Disconnect 4: Deficient Dashboard Implementation
* **Code Location:** `dashboard/dashboard_server.py` (lines 38–39, 46–52) and `dashboard/metrics_collector.py` (lines 65–72).
* **The Requirement:** `ps3.md` Section 5 explicitly demands:
  > *"Dashboard for latency, jitter, loss, throughput, queue depth and fairness."*
* **The Reality:**
  - `dashboard_server.py` defines only two canvases:
    ```html
    <div class="chart-box"><canvas id="latencyChart"></canvas></div>
    <div class="chart-box"><canvas id="dropChart"></canvas></div>
    ```
  - `metrics_collector.py` defines `jains_fairness_index()` and `get_throughput()`, but `collect_snapshot()` **never calls them**.
  - Queue depth (`backlog` in `tc -s qdisc`) is never extracted.
  - Jitter is extracted in `get_latency()`, but omitted from the dashboard charts.
  - Packet loss percentage is not calculated in the collector.

### Disconnect 5: Active Saturation Probing as Link Estimator
* **Code Location:** `estimator/link_estimator.py` (lines 20–30).
* **The Reality:** The estimator executes `iperf3 -c 10.0.3.2 -t 2 -R -J`.
* **Impact:** Active TCP saturation probing attempts to max out the link. If run every 8 seconds on an active home network, the estimator itself creates severe bufferbloat and packet drops for user applications. SLoPS/Pathload methodology was cited in the docstring, but the actual implementation is standard full-blast iperf3. Furthermore, it requires an `iperf3` server daemon running on the remote ISP endpoint.

### Disconnect 6: IPv6 Blindness in Traffic Classifier and Health Check
* **Code Location:** `classifier/feature_extraction.py` (line 19) and `policy_engine/rollback_manager.py` (line 58).
* **The Reality:**
  ```python
  # classifier/feature_extraction.py
  def process_packet(pkt):
      if IP in pkt: # Scapy IP class is IPv4 ONLY!
          ...
  ```
* **Impact:** While the network topology supports IPv6, any IPv6 packets crossing the gateway are completely dropped by the feature extraction logic (`IPv6 in pkt` is never checked). Similarly, `health_check()` and `metrics_collector.py` hardcode IPv4 `10.0.3.2`.

---

## 5. Dual Cross-Verification Summary Matrix

| PS3 Requirement Area | Requirement Detail | Cross-Verification 1 (Code AST / Logic) | Cross-Verification 2 (Runtime / System Context) | Final Grade |
| :--- | :--- | :--- | :--- | :---: |
| **Traffic Classifier** | Non-DPI classification | Verified: Only IP headers used. | Verified: Offline only; zero runtime inference. | **Yellow (60%)** |
| **AI vs Baseline** | Compare AI to heuristic | Verified: +5.5% accuracy gain shown. | Verified: Model never executed in network test. | **Yellow (65%)** |
| **Link Estimator** | Dynamic capacity estimation | Verified: iperf3 wrapper functions exist. | Verified: Saturation probing; open-loop. | **Yellow (50%)** |
| **Policy Enforcement**| Linux `tc` / CAKE shaping | Verified: Root bandwidth shaping works. | Verified: No DSCP marking; DiffServ unused. | **Yellow (50%)** |
| **User Intent** | Temporary service intent | Verified: NLP parsing works. | Verified: Disconnected from network data plane. | **Red (25%)** |
| **Rollback / Safety** | Safe state rollback | Verified: `rollback_manager.py` functional. | Verified: Health check threshold rigged in test. | **Yellow (70%)** |
| **Illustrative Tests** | 3 scenarios from ps3.md | Verified: Scenario 1 tested. | Verified: Scenario 2 unintegrated; Scenario 3 absent. | **Red (30%)** |
| **Dashboard** | 6 specific metrics | Verified: Only 2 metrics logged and charted. | Verified: Jitter, throughput, queue depth, fairness missing. | **Red (33%)** |
| **Documentation** | Licenses, limits, setup | Verified: All MD files present. | Verified: `architecture.png` link broken. | **Green (90%)** |

---

## 6. Actionable Remediation Plan (To Achieve 100% Completion)

To bring the codebase to full end-to-end completion, the following engineering steps are required:

### Step 1: Deploy Runtime Classifier & Packet Marker
1. In `classifier/`, write an online packet classifier daemon (`runtime_classifier.py`):
   - Sniff packets continuously (supporting both Scapy `IP` and `IPv6`).
   - Group packets into 5-tuple flows.
   - Load `xgb_model.pkl` and predict traffic class with probability confidence.
   - Set DSCP marks on matching flows using `iptables -t mangle -A PREROUTING ... -j DSCP --set-dscp-class ...` (e.g., `EF` for voice, `AF41` for video, `CS1` for bulk).

### Step 2: Wire Intent API to Policy Engine & DSCP Rules
1. In `api/server.py`:
   - Connect `/intent` to `policy_rules.py` and an active scheduler.
   - When an intent is submitted (e.g., "prioritize video"), dynamically inject a priority rule or boost the video DSCP tier.
   - Start an `asyncio` background task to automatically expire the rule and revert after `duration_sec`.

### Step 3: Upgrade Dashboard to Render All 6 Mandated Metrics
1. In `dashboard/metrics_collector.py`:
   - Parse `backlog` from `tc -s qdisc show dev veth-gw-wan` for queue depth.
   - Include `jitter_ms` and calculate `packet_loss_pct`.
   - Calculate passive throughput from byte delta over time.
   - Calculate Jain's Fairness Index across LAN flows.
2. In `dashboard/dashboard_server.py`:
   - Add frontend Chart.js canvases for Jitter, Throughput, Queue Depth, and Fairness Index.

### Step 4: Implement Closed-Loop Autonomous Controller Daemon
1. Create `controller_daemon.py`:
   - Periodically check link metrics and passive throughput.
   - If congestion or bandwidth drop is detected, calculate new shaping target.
   - Apply policy via `RollbackManager`.
   - Perform post-apply health check; rollback if jitter/latency exceeds threshold under load.

### Step 5: Implement Scenarios 2 and 3
1. **Scenario 2 Test Script:** Automatically trigger `wan_simulator.py drop_test` while competing traffic is active, and verify that `controller_daemon.py` throttles CAKE within 10 seconds to eliminate queue buildup.
2. **Scenario 3 Test Script:** Add `lan3` and `lan4` to `testbed/setup_topo.sh`, generate 3 video streams and 1 gaming stream, and demonstrate balanced fairness.
