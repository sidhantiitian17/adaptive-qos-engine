# Phase 3.2: Critical Discrepancy & Forensic Resolution Log

**Audit Scope:** Rigorous forensic audit of all historical narrative claims vs. bit-for-bit raw artifacts.  

## Discrepancy 1: Scenario C Jain Fairness Index Narrative vs Counter Data
- **Historical Claim (Phase 3 Report):** Baseline Jain = 0.784 (with claimed TV throughputs 1.820, 0.840, 0.510 Mbps); Adaptive Jain = 1.000.
- **Raw Artifact Finding (`phase3_1_scenario_c_raw.json`):**
  - Baseline Run 1 Bytes: `[2674800, 2682000, 2678400]` -> $J = 0.9999988$
  - Baseline Run 2 Bytes: `[2656800, 2661600, 2664000]` -> $J = 0.9999987$
  - Baseline Run 3 Bytes: `[2658000, 2661600, 2665200]` -> $J = 0.9999988$
  - Adaptive Run 1 Bytes: `[2301600, 2301600, 2302800]` -> $J = 0.9999999$
  - Adaptive Run 2 Bytes: `[2302800, 2306400, 2306400]` -> $J = 0.9999995$
  - Adaptive Run 3 Bytes: `[2301600, 2304000, 2304000]` -> $J = 0.9999998$
- **Root Cause & Forensic Diagnosis:** The 0.784 figure was an unverified narrative carried over from hypothetical TCP starvation scenarios. In reality, the synthetic/test traffic generator generates concurrent UDP datagrams with identical packet pacing. Because UDP send rates were uniform across the 3 TV flows, raw byte reception remained symmetric ($J=1.000$).
- **True Demonstrated QoS Impact:** The genuine QoS benefit demonstrated under the kernel datapath is the complete isolation and latency protection of the Gaming UDP flow (`0xb8` EF tag), where latency dropped from **134.303 ms (Baseline)** to **15.725 ms (Adaptive)**—an **88.29% reduction** under heavy contention.
- **Resolution:** Criterion 20 is verified as $J=1.000$ based strictly on raw counter data. The narrative claiming $J=0.784$ is classified as a legacy documentation discrepancy.

---
## Discrepancy 2: Scenario A Video Throughput vs Queuing Delay Protection
- **Historical Formulation:** Occasional references in earlier documentation implied Adaptive QoS "increased video throughput".
- **Raw Artifact Finding (`phase3_1_scenario_a_raw.json`):**
  - Baseline Mean Video Throughput: 1.143 Mbps
  - Adaptive Mean Video Throughput: 0.924 Mbps
  - Baseline Queuing Latency: 101.706 ms
  - Adaptive Queuing Latency: 0.700 ms
- **Forensic Diagnosis:** Video stream bitrate is inherently limited by the sender/encoder profile (~1.2 Mbps). In Baseline FIFO mode, bulk traffic fills the queue causing massive bufferbloat (101.7 ms delay, 13.57 ms jitter). In Adaptive mode, CAKE DiffServ4 tins place video packets in a separate queue, dropping latency to 0.700 ms (99.31% drop) and jitter to 0.250 ms (98.16% drop).
- **Resolution:** Neutral, factual wording adopted: Adaptive QoS provides queue delay and jitter protection, not video bandwidth multiplication.

---
## Discrepancy 3: Long-Run Stability Memory Claim
- **Historical Claim:** "Zero memory leaks" based solely on start RSS (163.47 MB) and end RSS (164.60 MB).
- **Forensic Diagnosis:** A 10-minute snapshot showing a 1.12 MB delta cannot theoretically prove zero memory leaks indefinitely. However, an analysis of the full 118-sample time series (`phase3_1_long_run.json`) reveals that RSS was constant for 107 out of 117 intervals, plateauing after minute 4 with a linear slope of only 0.0891 MB/min and periodic garbage collector recovery.
- **Resolution:** Claim tightened to: *"No sustained RSS growth indicative of a memory leak was observed during the 600.6-second run; RSS increased by 1.12 MB and plateaued."*

---
## Discrepancy 4: Scope of Physical NIC Hardware Validation
- **Historical Claim:** Phase 3 report claimed 37/37 criteria fully verified, including physical NIC hardware offloading.
- **Forensic Diagnosis:** The active operating system is WSL2 (Linux kernel 6.18.40.1-microsoft-standard-WSL2+) running over virtual Ethernet (`veth`) interface namespaces. Physical NIC hardware registers, PCIe ASIC offloads, and physical PHY transmission were never exercised.
- **Resolution:** Strictly classified as **ENVIRONMENT-LIMITED / NOT DEMONSTRATED**. Final verdict remains **PARTIALLY VERIFIED (36/37)**.
