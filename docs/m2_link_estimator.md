# Module M2 — Link Capacity Estimator Specification & Verification

**Project:** Adaptive QoS Engine for Mixed Home Broadband Traffic  
**Component:** Module M2 (`estimator/`)  
**Methodology:** Self-Loading Periodic Streams (SLoPS) per Jain & Dovrolis (2002/2003, 2004)  
**Status:** Implemented, Integrated, Fully Tested, and Verified

---

## 1. Purpose of Module M2

In modern home broadband environments, access link capacity (the bottleneck) can fluctuate dynamically due to ISP oversubscription, DOCSIS cable contention, cellular fixed wireless (5G) variability, and Wi-Fi interference. When upstream or downstream traffic exceeds the bottleneck rate, packets accumulate in oversized router and modem buffers, causing crippling bufferbloat (latency spikes from ~10 ms up to >1000 ms).

The purpose of **Module M2 (Link Capacity Estimator)** is to:
1. Accurately measure the available bottleneck capacity $A$ without decrypting or inspecting user payloads.
2. Provide a rigorous, bounded range $[R_{\min}, R_{\max}]$ rather than a single fictitious point estimate.
3. Feed the effective capacity to **Module M3 (Policy Engine)** so the controller can shape traffic to $95\%$ of capacity, eliminating queue buildup before bufferbloat occurs.
4. Apply hysteresis damping ($15\%$) to prevent policy thrashing during minor transient fluctuations.
5. Operate with minimal CPU and traffic overhead ($< 0.5\%$ link consumption).

---

## 2. Research Basis & Methodological Foundation

Module M2 employs **SLoPS-style active available-bandwidth estimation based on the Jain–Dovrolis methodology, with engineering adaptations for our Linux namespace testbed**.

The implementation follows the available-bandwidth probing concepts described by Jain and Dovrolis, while adapting packet generation, trend detection, convergence, synchronization, and failure handling for the project's Linux namespace testbed. It does not claim to be the original academic C implementation of Pathload, but rather a purpose-built Python/Netlink integration within the AQE closed-loop control pipeline.

The foundational papers informing this design are:

1. **Manish Jain & Constantine Dovrolis (2002 / 2003):**  
   *"End-to-End Available Bandwidth: Measurement Methodology, Dynamics, and Relation with TCP Throughput"* (IEEE/ACM Transactions on Networking, 2003; earlier ACM SIGCOMM 2002).  
   Introduced the **Self-Loading Periodic Streams (SLoPS)** methodology and the **Pathload** tool. SLoPS establishes that if a periodic stream of packets is sent at rate $R$:
   - If $R > A$ (probing rate exceeds available bandwidth), probe packets accumulate in the bottleneck queue, causing one-way transit delays to monotonically increase.
   - If $R \le A$ (probing rate is within available bandwidth), packets do not accumulate, and one-way delays remain stationary.
   - SLoPS analyzes delay trends using two statistical tests:
     - **Pairwise Comparison Test (PCT):** Measures the fraction of consecutive delay increments.
     - **Pairwise Difference Test (PDT):** Measures the net delay drift normalized by total delay variation.

2. **Manish Jain & Constantine Dovrolis (2004):**  
   *"Ten Fallacies and Pitfalls on End-to-End Available Bandwidth Estimation"* (ACM Internet Measurement Conference IMC 2004).  
   Identifies critical design pitfalls addressed by M2:
   - *Fallacy 1:* Available bandwidth is not a single scalar number; it varies across time scales and should be reported as a range $[R_{\min}, R_{\max}]$.
   - *Fallacy 2:* TCP throughput (iperf) cannot be used as ground truth for available bandwidth (TCP probes capacity aggressively and alters the cross-traffic state).
   - *Fallacy 3:* User-space timers introduce OS scheduling noise; grouping into $G$ intervals with group medians is essential to smooth transient jitter.
   - *Fallacy 7:* Probing must not saturate the link for extended durations or displace legitimate traffic.

---

## 3. System Architecture & Inter-Module Contract

Module M2 operates as the second stage in the AQE closed-loop control pipeline:

```
[M1 Traffic Classifier]
         │ (Zero-payload classification, FlowTable)
         ▼
[M2 Link Capacity Estimator] ── (SLoPS Probing Range [R_min, R_max], Effective Capacity)
         │
         ▼
[M3 Policy Engine] ────────── (Calculates Target Shaping = 0.95 * Capacity, 20% Bulk Floor)
         │
         ▼
[M4 Enforcement Engine] ───── (Applies Linux CAKE qdisc via Netlink / tc)
         │
         ▼
[M5 Closed-Loop Verifier] ─── (Validates QoE Latency < 60ms, Zero Loss)
         │
         ▼
[M6 Rollback Manager] ─────── (Restores Last-Known-Good Configuration if Health Fails)
```

### Module M2 Contract Definition

```python
@dataclass
class CapacityEstimate:
    estimated_bandwidth_min_mbps: float  # Confirmed uncongested lower bound (R_min)
    estimated_bandwidth_max_mbps: float  # Confirmed congested upper bound (R_max)
    estimated_bandwidth_mid_mbps: float  # Midpoint estimate
    effective_capacity_mbps: float       # Hysteresis-damped capacity fed to M3
    confidence: float                    # Reliability metric [0.0 - 1.0]
    probe_rate_start_mbps: float         # Initial search probe rate
    probe_rate_final_mbps: float         # Terminal search probe rate
    iterations: int                      # Number of bisection iterations (<= 8)
    samples: int                         # Total packets received across probes
    pct: float                           # Pairwise Comparison Test metric
    pdt: float                           # Pairwise Difference Test metric
    converged: bool                      # Whether |R_high - R_low| <= tolerance
    stable: bool                         # Whether confidence >= 0.80 and converged
    timestamp: float                     # UNIX timestamp of measurement
    method: str                          # "slops_active" or "fallback_passive"
    state: str                           # EstimatorState enum string
    status: str                          # "measured", "stabilized", "degraded"
    error: Optional[str]                 # Failure reason if degraded
    overhead: Optional[Dict[str, Any]]   # CPU time ms, probe bytes, probe packets
```

---

## 4. State Transitions & Life-Cycle State Machine

Module M2 transitions deterministically across 10 formal states:

$$\begin{aligned}
\text{IDLE} &\xrightarrow{\text{Trigger Probe}} \text{PROBING} \\
\text{PROBING} &\xrightarrow{\text{Paced UDP Stream Transmitted}} \text{MEASURING} \\
\text{MEASURING} &\xrightarrow{\text{Arrival Timestamps Harvested}} \text{TREND\_ANALYSIS} \\
\text{TREND\_ANALYSIS} &\xrightarrow{\text{PCT/PDT Computed}} \text{BOUND\_UPDATE} \\
\text{BOUND\_UPDATE} &\xrightarrow{\text{Bounds Narrowed}} \text{CONVERGING} \\
\text{CONVERGING} &\xrightarrow{\text{Interval } \le \text{Tol}} \text{STABLE} \\
\text{PROBING} &\xrightarrow{\text{Socket Error / Timeout}} \text{PROBE\_FAILURE} \to \text{DEGRADED}
\end{aligned}$$

- **`IDLE`:** Estimator is standing by; receiver listening on UDP 54321.
- **`PROBING`:** Sender is emitting $K=80$ packets at paced rate $R$ with zero heap allocations.
- **`MEASURING`:** Receiver collects packets and computes relative delays $t_{recv} - t_{send}$.
- **`TREND_ANALYSIS`:** `TrendAnalyzer` computes $G=10$ medians, PCT, PDT, and trend decision.
- **`BOUND_UPDATE`:** Bisection algorithm advances $R_{\min}$ if uncongested or contracts $R_{\max}$ if congested.
- **`CONVERGING`:** Search iterates until $[R_{\min}, R_{\max}] \le 3.0$ Mbps or max iterations reached.
- **`STABLE`:** Convergence achieved with confidence $\ge 0.80$; hysteresis check passed.
- **`DEGRADED`:** Receiver unavailable or socket error; falls back safely to last-known-good capacity.

---

## 5. Detailed Algorithms

### 5.1 Zero-Allocation Microsecond Pacing

Sender uses busy-wait microsecond timing with preallocated buffers and in-place binary serialization (`struct.pack_into`) to prevent OS scheduling interruptions:

$$\Delta t = \frac{P \times 8}{R_{\text{bps}}}$$

Every packet carries the magic header `SLOP`, stream sequence ID, send timestamp, and rate metadata.

### 5.2 Group Median Filtering & Trend Tests (PCT / PDT)

One-way delays $D_1 \dots D_K$ are split into $G=10$ groups ($N = K/G = 8$ packets per group). The group median $\bar{D}_g = \text{median}(\{D_{(g-1)N + 1} \dots D_{gN}\})$ eliminates OS context-switch spikes.

1. **Pairwise Comparison Test (PCT):**
   $$\text{PCT} = \frac{\sum_{i=1}^{G-1} I(\bar{D}_{i+1} > \bar{D}_i)}{G - 1}$$
   - Measures the fraction of consecutive group intervals exhibiting delay growth.
   - Threshold: $\text{PCT} > 0.55 \implies$ positive trend.

2. **Pairwise Difference Test (PDT):**
   $$\text{PDT} = \frac{\bar{D}_G - \bar{D}_1}{\sum_{i=1}^{G-1} |\bar{D}_{i+1} - \bar{D}_i|}$$
   - Quantifies the directional drift normalized by total absolute variation.
   - Threshold: $\text{PDT} > 0.40 \implies$ strong monotonic queue expansion.

3. **Trend Classification:**
   - **`CONGESTED`:** $(\text{PCT} > 0.55 \land \text{PDT} > 0.40) \lor (\text{PDT} > 0.45 \land \Delta_{\text{diff}} > 0.4\text{ms}) \lor (\Delta_{\text{diff}} > 1.0\text{ms})$.
   - **`UNCONGESTED`:** $\text{PCT} \le 0.58 \land \text{PDT} \le 0.25 \land \Delta_{\text{diff}} \le 0.3\text{ms}$.
   - **`UNCERTAIN`:** Gray region; upper bound $R_{\max}$ is contracted to prevent overestimating capacity.

### 5.3 Iterative Bisection Search

Searches available bandwidth within $[R_{\min}=2\text{M}, R_{\max}=150\text{M}]$:
- Next probe rate: $R = \frac{R_{\min} + R_{\max}}{2}$.
- If `UNCONGESTED`: $R_{\min} \leftarrow R$.
- If `CONGESTED` or `UNCERTAIN`: $R_{\max} \leftarrow R$.
- Terminates when $R_{\max} - R_{\min} \le 3.0$ Mbps or 8 iterations elapse.

### 5.4 Hysteresis Damping (15% Threshold)

To prevent oscillation in CAKE shaping rules:
$$\Delta_{\%} = \frac{|R_{\text{new}} - R_{\text{last\_good}}|}{R_{\text{last\_good}}} \times 100\%$$
- If $\Delta_{\%} \ge 15\%$: `detect_change()` returns `True`, triggering policy recalculation in M3.
- If $\Delta_{\%} < 15\%$: capacity update is filtered as transient jitter, preserving policy stability.

---

## 6. Failure Handling & Degraded Fallback

Module M2 handles faults deterministically without crashing or stalling the control loop:

1. **Receiver Unreachable / UDP Loss:**
   If probe packets receive no response within `timeout_sec=2.5s`, state transitions to `DEGRADED`.
   The estimator logs the failure reason and outputs `last_known_good_capacity` (default 100 Mbps) to avoid disrupting active traffic.

2. **Severe Link Congestion During Probing:**
   If packet loss exceeds $20\%$, the probe stream is immediately classified as `CONGESTED`, contracting $R_{\max}$ downward without requiring further delay measurements.

3. **Multi-Thread Concurrency:**
   All probing invocations are guarded by `threading.Lock()`. Concurrent calls serialize safely without corrupting socket buffers.

---

## 7. Baseline Comparison (Passive vs SLoPS)

| Dimension | Passive Estimator Baseline (`/proc/net/dev`) | SLoPS Active Probing Estimator (M2) | Advantage |
| :--- | :--- | :--- | :--- |
| **Methodology** | Passive byte counter polling | Jain & Dovrolis SLoPS (PCT/PDT) | Non-heuristic, physics-based |
| **20 Mbps Estimation Error** | $400.0\%$ (Reports 100 Mbps nominal default) | $8.2\%$ (Reports 21.65 Mbps midpoint) | **+391.8 pp accuracy advantage** |
| **Behavior on Idle Link** | Completely blind (assumes 100M nominal) | Measures true capacity in $< 0.6$s | Discovers bottleneck before saturation |
| **Bandwidth Range** | Single scalar point estimate | Bounded range $[R_{\min}, R_{\max}]$ | Honest representation of uncertainty |
| **Hysteresis Damping** | None (flaps with byte counter bursts) | $15\%$ delta threshold | Eliminates policy oscillation |
| **CPU Overhead** | $\sim 0.5$ ms | $\sim 187$ ms total search | Negligible impact on gateway CPU |
| **Traffic Overhead** | $0$ KB | $< 0.6$ MB total per full search | $< 0.5\%$ link consumption |

---

## 8. Ground-Truth Experimental Verification Results

All tests executed automatically using Linux `tc netem` bottleneck emulation in `experiments/run_m2_evaluation.py` (canonical run recorded in `results/m2/summary.csv` and `results/m2/report.md`):

| Test ID | Ground Truth | Estimated Range (Mbps) | Point Estimate (Mbps) | Metric Type | Error (%) | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **TEST 1: Static 100M** | 100.0 Mbps | [87.5, 89.8] | 88.65 | Range Midpoint | 11.3% | **PASS** |
| **TEST 2: Static 20M** | 20.0 Mbps | [18.1, 20.5] | 19.30 | Range Midpoint | 3.5% | **PASS** |
| **TEST 3: Dynamic Adaptation (100 -> 20M)** | 20.0 Mbps | [18.1, 20.5] | 19.30 | Range Midpoint | 3.5% | **PASS** |
| **TEST 4: Dynamic Recovery (20 -> 100M)** | 100.0 Mbps | [99.2, 101.5] | 100.35 | Range Midpoint | 0.3% | **PASS** |
| **TEST 5: Bursty Cross-Traffic** | 50.0 Mbps | [49.35, 51.7] | 50.13 | Sample Mean (Midpoint: 50.525) | 0.3% | **PASS** |
| **TEST 6: Multiple Competing Flows** | 60.0 Mbps | [55.2, 57.5] | 56.35 | Range Midpoint | 6.1% | **PASS** |

> **Distinction on Test 5 (Bursty Cross-Traffic):**
> Under dynamic UDP cross-traffic bursts, SLoPS recorded 3 consecutive sample estimates: `[49.35, 51.7, 49.35]` Mbps, exhibiting a sample spread of **2.35 Mbps** ($\max - \min$). The reported representative point estimate of **50.13 Mbps is the arithmetic mean** of these samples ($|50.13 - 50.0|/50.0 = 0.3\%$ relative error). The midpoint of the sample spread range $[49.35, 51.7]$ Mbps is **50.525 Mbps** ($|50.525 - 50.0|/50.0 = 1.05\%$ relative error).
>
> **Technical Delineation of 20 Mbps Evaluations (Test 2 vs Baseline Comparison):**
> - In **Test 2 (Standalone Static 20M)**, evaluated at the beginning of the suite on an uncontended cold link, SLoPS converged to $[18.1, 20.5]$ Mbps (midpoint **19.30 Mbps, 3.5% relative error**).
> - In **Test 3 (Dynamic Adaptation 100 $\to$ 20M)**, SLoPS detected the sudden throttle and stabilized at $[18.1, 20.5]$ Mbps (midpoint **19.30 Mbps, 3.5% relative error**).
> - In the **Comparative Baseline Benchmark** (Section 7), evaluated in a separate run after Test 6 on an idle link, SLoPS terminated at the adjacent bracket $[20.5, 22.8]$ Mbps (midpoint **21.65 Mbps, 8.2% relative error**) due to SLoPS bisection step granularity (`convergence_tolerance_mbps = 3.0`). While Test 2's interval $[18.1, 20.5]$ Mbps directly bounds 20.0 Mbps ($18.1 \le 20.0 \le 20.5$), the baseline bracket $[20.5, 22.8]$ Mbps sits just above ground truth ($20.0 < 20.5$ Mbps) and does not contain 20.0 Mbps; its midpoint 21.65 Mbps nevertheless satisfies the $\le 20\%$ point-estimate error threshold. In contrast, the passive estimator exhibited **400.0% error** (defaulting to 100 Mbps because the idle link provided no byte transitions), demonstrating a **+391.8 percentage point accuracy advantage** for SLoPS.

### Dynamic Adaptation Timeline ($T_0 \dots T_5$)

During Test 3 (abrupt bottleneck throttling from 100 Mbps to 20 Mbps):
- **$T_0$ (Bottleneck throttled to 20M):** `1791471013.071s`
- **$T_1$ (Estimator detected new capacity):** `1791471014.131s` (Detection latency: `1.060s`)
- **$T_2$ (Hysteresis & stability verified):** `1791471014.131s`
- **$T_3$ (M3 Policy Engine computed shaping):** `1791471014.131s` (Target CAKE rate: `18 Mbps`)
- **$T_4$ (M4 Kernel CAKE enforcement applied):** `1791471014.150s` (Adaptation latency: `1.079s`)
- **$T_5$ (M5 Closed-loop health check confirmed):** `1791471016.220s` (Latency $< 60$ ms, loss $0.0\%$, Verification latency: `3.150s`)

---

## 9. Known Limitations & Production Considerations

1. **Two-Point Deployment Requirement:**
   SLoPS requires an active reflector or receiver on the target endpoint (e.g. ISP edge router, cloud reflector, or WAN host). In single-ended environments where no remote reflector is deployed, AQE falls back to passive counter analysis and RTT dispersion probes.

2. **Cellular / Wireless Scheduling Jitter:**
   In 5G and LTE networks, base station scheduling intervals (TTI of 1 ms) can create multi-millisecond delay discretization. In such deployments, $K$ should be increased to 120 packets and group size $G$ adjusted accordingly.

3. **Asymmetric Links:**
   SLoPS one-way delay measurement specifically isolates the path under test (forward path). Probe return traffic requires minimal ACK bandwidth ($< 1$ KB).

4. **SQLite Evidence Database & Result Artifact Scope Limitation:**
   The SQLite relational database (`experiments/evidence.db`) persists experiment runs and key summary scalar evaluation metrics (`static_100_error_pct`, `static_20_error_pct`, `adaptation_time_sec`). Evaluation artifacts in `results/m2/*.json` and `results/m2/summary.csv` store structured experiment summaries, per-scenario validation metrics, and sampled capacity estimates (including convergence status, iteration counts, aggregate PCT/PDT trend scores, resource overhead, and sample ranges). Microsecond-level packet arrival timestamps are analyzed in-memory during SLoPS execution and are not persisted to disk in either SQLite or the summary files.

---

## 10. Prototype vs Production Boundary

| Dimension | Current Prototype Implementation | Production Router Target |
| :--- | :--- | :--- |
| **Runtime Environment** | Python 3.12 with busy-wait pacing and Netlink | C / Rust daemon with `io_uring` or eBPF pacing |
| **Network Namespaces** | Linux `veth` network namespaces (`gw`, `wanhost`) | Physical WAN interface (`eth0`, `pppoe-wan`) |
| **Reflector** | Python UDP socket in `wanhost` | Lightweight eBPF / XDP reflector at edge POP |
| **Probing Schedule** | Event-driven (daemon cycle + API trigger) | Continuous low-rate background probing (every 10s) |
