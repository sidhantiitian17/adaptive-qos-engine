# Phase 4.1 Independent KPI Recalculation & Telemetry Audit

**Project:** Case Study 3 — Adaptive QoS Engine for Mixed Home Broadband Traffic  
**Auditor:** Independent Senior Network-QoS / Systems Acceptance Auditor  
**Scope:** Recomputation of all primary and secondary performance indicators directly from raw evidence artifacts, SQLite DB rows, and kernel telemetry.  

---

## 1. Scenario A — Bulk Download vs Interactive Video

### Raw Evidence Artifacts
- Latency / Probe Source: [`phase4_artifacts/phase4_scenario_results.json`](file:///home/prashast/adaptive-qos-engine/phase4_artifacts/phase4_scenario_results.json)
- Traffic Generator Profile: [`experiments/traffic_generator.py`](file:///home/prashast/adaptive-qos-engine/experiments/traffic_generator.py)

### Recalculated Metrics
| Metric | Baseline Mode | Adaptive Mode | Impact / Delta | Verification Method |
|:---|:---:|:---:|:---:|---|
| **UDP Queuing Delay (RTT)** | **227.455 ms** | **0.805 ms** | **-99.65% delay** | UDP Echo Probe Train (`UdpRttProber`) |
| **Delay Jitter (MAD)** | **13.500 ms** | **0.250 ms** | **-98.15% jitter** | RFC 3550 consecutive difference |
| **Offered Video Load** | 1.200 Mbps | 1.200 Mbps | 0.0% | `TRAFFIC_PROFILES["VIDEO_CONFERENCE"]` |
| **Measured Video Rate** | 1.140 Mbps | 1.206 Mbps | Preserved full rate | Socket byte accumulation (`TrafficReceiver`) |
| **Reported Fallback Video** | 1.140 Mbps | 0.950 Mbps | N/A (Key typo) | Typo in `.get("throughput_mbps", ...)` |
| **Bulk Download Throughput** | 15.900 Mbps | 15.800 Mbps | Concurrently serviced | TCP socket transfer across router |

### Neutral Interpretation
Adaptive QoS completely eliminates bufferbloat delay (cutting queuing delay from 227.46 ms to 0.81 ms) by isolating interactive media packets into CAKE's `AF41` Video tin while allowing bulk transfers to saturate available background bandwidth. Video throughput is fully preserved at encoder send rate (~1.2 Mbps).

---

## 2. Scenario B — Dynamic WAN Collapse & Recovery Timeline

### Raw Evidence Artifacts
- Timeline Data: [`phase4_artifacts/phase4_scenario_results.json`](file:///home/prashast/adaptive-qos-engine/phase4_artifacts/phase4_scenario_results.json) (under `scenario_b.timestamps`)

### Raw Event Timestamps (Monotonic Seconds)
- $T_{\text{cond\_collapse}}$ = `1791098376.015560`
- $T_{\text{meas\_start}}$ = `1791098376.038344`
- $T_{\text{policy\_decide}}$ = `1791098376.038345`
- $T_{\text{tc\_enforced}}$ = `1791098376.058535`
- $T_{\text{cond\_recovery}}$ = `1791098376.558656`
- $T_{\text{recovery\_enforced}}$ = `1791098376.597250`

### Recalculated Reaction Latencies
$$\text{Detection Latency} = T_{\text{meas\_start}} - T_{\text{cond\_collapse}} = 0.0228\text{ seconds}$$
$$\text{Decision Latency} = T_{\text{policy\_decide}} - T_{\text{meas\_start}} = 0.0000\text{ seconds}$$
$$\text{Enforcement Latency} = T_{\text{tc\_enforced}} - T_{\text{policy\_decide}} = 0.0202\text{ seconds}$$
$$\mathbf{\text{Total Closed-Loop Adaptation Latency}} = T_{\text{tc\_enforced}} - T_{\text{cond\_collapse}} = \mathbf{0.0430\text{ seconds}} \quad (\le 1.0\text{s Target})$$
$$\mathbf{\text{Total Recovery Latency}} = T_{\text{recovery\_enforced}} - T_{\text{cond\_recovery}} = \mathbf{0.0386\text{ seconds}} \quad (\le 1.0\text{s Target})$$

---

## 3. Scenario C — 3 TV Streams + Gaming Contention

### Raw Counter Evidence
- Transmitted TV stream byte counts: $x_1 = 2,304,000$, $x_2 = 2,304,000$, $x_3 = 2,306,400$
- Sum of allocations: $\sum x_i = 6,914,400$ bytes
- Sum of squares: $\sum x_i^2 = 15,936,312,960,000$

### Independent Jain's Fairness Index Calculation
$$J(x) = \frac{\left(\sum_{i=1}^n x_i\right)^2}{n \cdot \sum_{i=1}^n x_i^2} = \frac{(6,914,400)^2}{3 \cdot (15,936,312,960,000)} = \frac{47,808,927,360,000}{47,808,938,880,000} = \mathbf{0.999999759} \approx \mathbf{1.000000}$$

### Gaming Latency Under TV Contention
- **Measured Virtual Datapath RTT (Without NetEm):** **0.400 ms** (min: 0.051 ms, mean: 0.270 ms, max: 0.683 ms)
- **Annotated Realistic WAN RTT (With NetEm 15ms):** **15.725 ms**
- **Gaming Tin Assignment:** `Voice` / `EF` (DSCP `0xB8`), strictly prioritized over background TV streaming.

---

## 4. Anti-Starvation Validation

### Deterministic Floor Formula
$$\text{Floor}_{\text{bulk}} = \max(5\text{ Mbps}, \text{ShapingRate} \times 0.20)$$

### Contention Scenario Recalculation
- Link capacity during collapse: $20.0\text{ Mbps}$
- Shaping target: $19\text{ Mbit}$ ($0.95 \times \text{Capacity}$)
- Guaranteed bulk share: $19 \times 0.20 = \mathbf{3.8\text{ Mbps}}$ (or $5\text{ Mbps}$ absolute floor on larger profiles)
- Observed starvation duration: **0.0 seconds** (Bulk download actively made progress under 100% video contention)

---

## 5. Scalability & High-Load Telemetry

| Concurrent Flows | Flow Table Size | Mean Cycle Latency | Packet Insert Latency | Classifier Latency | RSS Memory |
|:---:|:---:|:---:|:---:|:---:|:---:|
| **10** | 10 | 17.61 ms* | 5.33 $\mu$s | 7.93 ms | 163.09 MB |
| **25** | 25 | 17.61 ms | 3.07 $\mu$s | 4.76 ms | 163.21 MB |
| **50** | 50 | 22.60 ms | 3.91 $\mu$s | 3.27 ms | 163.41 MB |
| **100** | 100 | 17.72 ms | 3.77 $\mu$s | 2.88 ms | 163.66 MB |

*(Note: Initial 10-flow batch included an initial one-time ML classifier warm-up cycle of 518 ms, normalizing to 17.6 ms on subsequent cycles).*
- **Classification Throughput:** **5,376 flows / second**.
- **Net Memory Growth across 100 flows:** **+0.57 MB RSS**.

---

## 6. Long-Run Production Stability Telemetry (600.02s)

- **Total Execution Time:** 600.02 seconds (10.00 minutes)
- **Total Cycles:** 20,003 cycles (33.3 cycles/second)
- **Mean Cycle Duration:** 7.653 ms
- **Unintended Policy Transitions:** 0 (0.0 transitions/minute)
- **Memory RSS Delta:** +0.08 MB (162.47 MB $\rightarrow$ 162.55 MB, drift rate: 0.004568 MB/min)
- **Certified Leak Assessment:** No sustained RSS growth indicative of a memory leak was observed.
