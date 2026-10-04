# Phase 3.2: Independent KPI Recalculation & Mathematical Provenance

**Audit Date:** 2026-10-03  
**Evaluation Method:** Deterministic recalculation from raw JSON counters and kernel packet metrics  

## 1. Scenario A — Bulk Congestion vs Interactive Video
### Raw Data Extraction & Run-by-Run Matrix
| Run | Mode | Latency (ms) | Jitter (ms) | Video Thru (Mbps) | Bulk Thru (Mbps) | Loss (%) | Queue (pkts) |
|---|---|---|---|---|---|---|---|
| 1 | BASELINE | 100.120 | 13.5298 | 1.143 | 15.970 | 0.0 | 0 |
| 2 | BASELINE | 102.526 | 13.5909 | 1.142 | 15.995 | 0.0 | 0 |
| 3 | BASELINE | 102.471 | 13.5946 | 1.143 | 16.001 | 0.0 | 0 |
| 1 | ADAPTIVE | 0.821 | 0.2326 | 1.201 | 15.916 | 0.0 | 0 |
| 2 | ADAPTIVE | 0.728 | 0.3205 | 1.201 | 15.907 | 0.0 | 0 |
| 3 | ADAPTIVE | 0.551 | 0.1954 | 0.371 | 5.732 | 0.0 | 0 |

### Statistical Summaries
- **Baseline Latency:** Mean = 101.706 ms (Min: 100.120 ms, Max: 102.526 ms)
- **Adaptive Latency:** Mean = 0.700 ms (Min: 0.551 ms, Max: 0.821 ms)
- **Latency Reduction:** 99.31% reduction in queuing delay under congestion.
- **Baseline Jitter:** Mean = 13.5718 ms
- **Adaptive Jitter:** Mean = 0.2495 ms (Reduction: 98.16%)
- **Baseline Video Throughput:** Mean = 1.143 Mbps
- **Adaptive Video Throughput:** Mean = 0.924 Mbps

> [!NOTE]
> **Throughput Analysis:** Adaptive QoS does NOT inflate video bitrate; video stream bitrate is determined by application video encoder / send rate (~1.2 Mbps). Under congestion, Baseline allows unmanaged bulk traffic to inflate queuing delay to 101.7 ms. Adaptive QoS (CAKE DiffServ4) isolates video packets into the high-priority tin, eliminating bufferbloat (0.700 ms latency).

---
## 2. Scenario B — WAN Collapse & Timestamp Verification
### Monotonic Timestamp Verification
- `condition_changed_at`: 1791057239.975865
- `measurement_started_at`: 1791057239.996123
- `measurement_completed_at`: 1791057240.058659
- `policy_decision_at`: 1791057240.058692
- `tc_command_start`: 1791057240.058692
- `tc_command_end`: 1791057240.080068
- `recovery_condition_at`: 1791057240.580224
- `recovery_enforced_at`: 1791057240.622242

### Recomputed Latency Intervals
- **Detection Latency:** 0.0828 s (Reported: 0.0828 s, Delta: 0.000006 s)
- **Decision Latency:** 0.000033 s (Reported: 0.0000 s)
- **Enforcement Latency:** 0.0214 s (Reported: 0.0214 s, Delta: 0.000025 s)
- **Total Adaptation Latency:** 0.1042 s (Reported: 0.1042 s, Delta: 0.000003 s)
- **Recovery Latency:** 0.0420 s (Reported: 0.0420 s, Delta: 0.000019 s)
- **Bandwidth Shaping:** Nominal = 100.0 Mbps -> Collapsed = 20.0 Mbps -> Adapted = 19 Mbit

---
## 3. Scenario C — TV Stream Contention & Jain Index Verification
### Raw Byte Counters and Jain Index Evaluation
| Run | Mode | TV1 (Bytes) | TV2 (Bytes) | TV3 (Bytes) | Jain Index (Bytes) | Gaming Latency (ms) | Gaming Jitter (ms) |
|---|---|---|---|---|---|---|---|
| 1 | BASELINE | 2674800 | 2682000 | 2678400 | 0.999999 | 139.322 | 56.1370 |
| 2 | BASELINE | 2656800 | 2661600 | 2664000 | 0.999999 | 131.959 | 51.1138 |
| 3 | BASELINE | 2658000 | 2661600 | 2665200 | 0.999999 | 131.629 | 50.5496 |
| 1 | ADAPTIVE | 2301600 | 2301600 | 2302800 | 1.000000 | 15.722 | 0.1875 |
| 2 | ADAPTIVE | 2302800 | 2306400 | 2306400 | 0.999999 | 15.708 | 0.2888 |
| 3 | ADAPTIVE | 2301600 | 2304000 | 2304000 | 1.000000 | 15.744 | 0.1165 |

### Scenario C Summary & Discrepancy Clarification
- **Baseline Mean Jain Index:** 1.0000 (Exact raw byte evaluation: 0.999999)
- **Adaptive Mean Jain Index:** 1.0000 (Exact raw byte evaluation: 1.000000)
- **Baseline Gaming Latency:** Mean = 134.303 ms
- **Adaptive Gaming Latency:** Mean = 15.725 ms (Reduction: 88.29%)
> [!IMPORTANT]
> **Discrepancy Resolution:** Historical reports claimed Baseline Jain = 0.784 based on hypothetical TCP starvation figures (1.82, 0.84, 0.51 Mbps). In actual kernel tests, 3 concurrent UDP TV flows send equal packet rates, resulting in mathematically equal transmission (J = 1.000). The true, verified QoS impact is the complete isolation and latency reduction of interactive gaming (134.3 ms down to 15.7 ms, an 88.29% reduction).

---
## 4. Long-Run Stability & Telemetry Recalculation
- **Test Duration:** 600.6 s (10.01 minutes)
- **Total Autonomous Cycles:** 24646 cycles
- **Cycle Latency:** Mean = 8.027 ms, p95 = 8.567 ms, p99 = 10.826 ms
- **Deadline Misses:** 7 (0.0%)
- **Memory Behavior:** Initial RSS = 163.47 MB, Final RSS = 164.6 MB, Delta = 1.12 MB
- **Total Samples:** 118 samples (every 5 seconds)
- **Time Series Dynamics:** Flat intervals = 107/117, Increases = 9/117, Decreases (GC reclaimed) = 1/117.
- **Unintended Policy Transitions:** 0 transitions (Rate: 0.0 transitions/minute).
