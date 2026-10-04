# Phase 6 KPI Recalculation & Mathematical Validation

**Project:** Case Study 3 — Adaptive QoS Engine for Mixed Home Broadband Traffic  
**Date:** 2026-10-04  
**Audit Purpose:** Independent recomputation of all Phase 6 KPIs directly from raw packet counters, nanosecond timestamps, and socket measurements.

---

## 1. Scenario A: Bufferbloat Mitigation Recomputation

### Raw Measured Data:
- **Baseline Run (Unshaped link under TCP bulk load):**
  - Probe packets sent: 6
  - Probe packets received: 6 (0% loss)
  - Raw RTT samples (ms): `[128.85, 129.12, 129.98, 130.04, 129.45]`
  - $\text{Mean RTT}_{\text{baseline}} = \frac{128.85 + 129.12 + 129.98 + 130.04 + 129.45}{5} = \mathbf{129.488\text{ ms}}$
  - Measured bulk TCP throughput: 13.559 Mbps
  - Measured video UDP throughput: 1.154 Mbps

- **Adaptive Run (CAKE 18 Mbps DiffServ4 shaping):**
  - Probe packets sent: 6
  - Probe packets received: 6 (0% loss)
  - Raw RTT samples (ms): `[0.64, 0.59, 0.62, 0.61, 0.62]`
  - $\text{Mean RTT}_{\text{adaptive}} = \frac{0.64 + 0.59 + 0.62 + 0.61 + 0.62}{5} = \mathbf{0.616\text{ ms}}$
  - Measured bulk TCP throughput: 15.966 Mbps
  - Measured video UDP throughput: 1.201 Mbps

### KPI Recomputations:
1. **Bufferbloat Reduction Percentage:**
   $$\Delta\% = \frac{\text{RTT}_{\text{baseline}} - \text{RTT}_{\text{adaptive}}}{\text{RTT}_{\text{baseline}}} \times 100$$
   $$\Delta\% = \frac{129.488 - 0.616}{129.488} \times 100 = \frac{128.872}{129.488} \times 100 = \mathbf{99.524\%} \approx \mathbf{99.52\%}$$
   - *Target:* $> 80.0\%$
   - *Status:* **EXCEEDED**

2. **Video Throughput Preservation:**
   $$\text{Preservation Ratio} = \frac{\text{Achieved Video Mbps}}{\text{Offered Video Mbps}} = \frac{1.201}{1.200} = \mathbf{100.08\%}$$
   - *Target:* $\ge 90.0\%$
   - *Status:* **EXCEEDED**

---

## 2. Scenario B: Dynamic Reaction & Recovery Timeline Recomputation

### Monotonic Event Timestamps:
- **Capacity Collapse (100 Mbps -> 20 Mbps):**
  - $t_0$ (WAN NetEm 20 Mbps injection initiated): `1791103930.1204`
  - $t_1$ (Rate change verified in netlink): `1791103930.1221`
  - $t_2$ (CAKE updated to 19 Mbps and verified): `1791103930.1688`
  - $\text{Adaptation Latency} = t_2 - t_0 = 1791103930.1688 - 1791103930.1204 = \mathbf{0.0484\text{ seconds}}$
  - *Target:* $\le 1.00\text{ s}$
  - *Status:* **EXCEEDED (20x faster than requirement)**

- **Capacity Recovery (20 Mbps -> 100 Mbps):**
  - $t_3$ (NetEm impairment removed): `1791103930.5692`
  - $t_4$ (CAKE updated to 95 Mbps and verified): `1791103930.6038`
  - $\text{Recovery Latency} = t_4 - t_3 = 1791103930.6038 - 1791103930.5692 = \mathbf{0.0346\text{ seconds}}$
  - *Target:* $\le 1.00\text{ s}$
  - *Status:* **EXCEEDED (28x faster than requirement)**

---

## 3. Scenario C: Contention & Multi-Stream Fairness Recomputation

### Raw Transferred Byte Counters:
- Stream 1 ($x_1$): `2,304,000 bytes`
- Stream 2 ($x_2$): `2,304,000 bytes`
- Stream 3 ($x_3$): `2,306,400 bytes`

### Jain's Fairness Index Formula:
$$J(x_1, x_2, \dots, x_n) = \frac{\left( \sum_{i=1}^n x_i \right)^2}{n \sum_{i=1}^n x_i^2}$$

### Step-by-Step Calculation:
1. $\sum x_i = 2304000 + 2304000 + 2306400 = 6,914,400$
2. $\left( \sum x_i \right)^2 = (6,914,400)^2 = 47,808,927,360,000$
3. $\sum x_i^2 = 2304000^2 + 2304000^2 + 2306400^2 = 5,308,416,000,000 + 5,308,416,000,000 + 5,319,480,960,000 = 15,936,312,960,000$
4. $n \sum x_i^2 = 3 \times 15,936,312,960,000 = 47,808,938,880,000$
5. $J = \frac{47,808,927,360,000}{47,808,938,880,000} = \mathbf{0.99999975904} \approx \mathbf{0.9999998}$
- *Target:* $\ge 0.95$
- *Status:* **EXCEEDED**

### Gaming Probe Latency under Impairment:
- Raw RTT samples (ms): `[15.48, 15.45, 15.52, 15.47, 15.53]`
- $\text{Mean RTT}_{\text{gaming}} = \mathbf{15.489\text{ ms}}$
- Min RTT: `15.447 ms`
- Median Absolute Deviation (MAD) Jitter: `0.029 ms`
- *Target:* $15.0 - 20.0\text{ ms}$
- *Status:* **VERIFIED**
