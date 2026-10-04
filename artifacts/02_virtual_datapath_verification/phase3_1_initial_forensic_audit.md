# Phase 3.1 Initial Read-Only Forensic Audit

**Audit Date**: 2026-10-03  
**Auditor**: Independent Principal Network Systems & Linux Kernel Datapath Validation Engineer  
**Scope**: Complete Codebase, Database (`experiments/evidence.db`), Kernel Telemetry, and Phase 3 Artifacts  

---

## 1. Executive Summary of Forensic Findings

An independent, line-by-line forensic audit of the Phase 3 implementation, evidence artifacts, database records, and written reports was conducted before executing fresh verification trials. 

### Critical Discrepancies & Deficiencies Uncovered:
1. **Physical Hardware Mischaracterization**:
   - The Phase 3 report frequently referred to "physical router", "physical WAN interface", and "hardware validation", despite Section 21 acknowledging execution over `veth` virtual Ethernet interfaces inside WSL2 (Linux 6.18 kernel).
   - *Classification Correction*: Must be classified strictly as **Multi-Node Virtual Linux Datapath Validation**. Physical NIC hardware validation is **NOT DEMONSTRATED / ENVIRONMENT-LIMITED**.
2. **Insufficient Long-Run Stability Duration**:
   - The Phase 3 report claimed "Long-Run Stability" based on 15 closed-loop cycles (~20 ms per cycle $\approx$ 0.31 seconds of total execution).
   - This fails the mandatory acceptance requirement of a sustained stability run (minimum 10 minutes, preferred 30–60 minutes).
   - *Classification Correction*: Criterion 29 must be classified as **NOT SATISFIED / PENDING RE-EXECUTION** until a genuine $\ge 10$-minute continuous closed-loop test is completed.
3. **Flapping Rate Premature Generalization**:
   - The report claimed "0.0 transitions/minute" based on 4 transitions over ~10 seconds of test time. This is statistically invalid for long-term stability characterization.
4. **Scenario B Capacity Collapse Measurement Discrepancy**:
   - In `run_phase3_scenarios.py`, the controller decision function `decide_policy(available_bandwidth_mbps=20.0, ...)` was invoked with a hardcoded `20.0` parameter simultaneously with `tc_wan.apply_netem(rate_mbit=20)`, rather than the controller passively or actively measuring the bottleneck collapse from traffic telemetry.
   - *Required Correction*: The capacity estimator must independently observe the throughput restriction under load, then pass that estimate to the policy engine.
5. **Scenario C Jain's Index & Text Discrepancy**:
   - In `scenario_c_hardware_baseline.json`, the recorded throughputs were `[1.201, 1.201, 1.201]` ($J=1.000$), but the Markdown report text claimed `1.820, 0.840, 0.510` ($J=0.784$). This was an unverified discrepancy between the raw artifact and the written summary.
   - Both baseline and adaptive runs generated non-competing 1.2 Mbps UDP streams below the 19/20 Mbps link limit, resulting in identical 1.201 Mbps rates.
   - *Required Correction*: Baseline and adaptive must be tested under genuine contention where aggregate demand exceeds link capacity to prove fair queuing vs FIFO starvation.
6. **NetEm Directionality & Probe RTT Ambiguity**:
   - `sch_netem` with `delay 15ms` was attached to `veth-wan-gw` in `wanhost`. Egress qdiscs in Linux only delay outgoing frames. Probes sent from `lan1` to `wanhost` experienced the 15 ms delay on the echo reply returning from `wanhost`, yielding ~15.5 ms RTT. This path topology was not explicitly documented, creating confusion regarding one-way vs round-trip delay.
7. **Zero Synthetic Constants Audit**:
   - A complete repository-wide regex search confirmed that hardcoded synthetic constants (`21.2`, `84.5`, `42.0`, `0.12`, `12`) have been purged from production code. Remaining matches are timestamps, CSS transition timings, and old baseline log text.

---

## 2. Detailed Forensic Claim-by-Claim Verification Matrix

| Claim in Phase 3 Report | Claim Source | Actual Evidence Found | Verification Layer | Forensic Status | Discrepancy / Required Action |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **"Hardware Validation / Physical Router"** | Report Sec 1, 2, 3 | Virtual Ethernet (`veth`) in WSL2 Linux 6.18 | Kernel runtime | **MISCHARACTERIZED** | Rename to Multi-Node Virtual Datapath. Mark Physical NIC as ENVIRONMENT-LIMITED. |
| **"Long-Run Stability: 15 cycles"** | Report Sec 15, `long_run_stability.json` | 15 cycles $\approx$ 0.31s total execution | Runtime log | **NOT SATISFIED** | Must execute sustained $\ge 10$-minute continuous closed-loop run with traffic. |
| **"Policy Flapping: 0.0/min"** | Report Sec 17, `policy_oscillation.json` | 4 transitions over ~10 seconds | Runtime log | **INSUFFICIENT DATA** | Must evaluate transitions across $\ge 10$-minute observation window. |
| **"IPv4 Multi-Node Forwarding"** | Report Sec 5, `ipv4_forwarding_evidence.txt` | Ping reply with `ttl=63` | Live kernel | **PROVISIONALLY VERIFIED** | Must supplement with raw bidirectional PCAP capture on all 3 nodes. |
| **"IPv6 Multi-Node Forwarding"** | Report Sec 5, `ipv6_forwarding_evidence.txt` | Ping6 reply with `ttl=63` (Hop Limit 63) | Live kernel | **PROVISIONALLY VERIFIED** | Must supplement with raw bidirectional PCAP capture on all 3 nodes. |
| **"CAKE on Router WAN Egress"** | Report Sec 7, `cake_forwarding_evidence.txt` | `tc -s qdisc show dev veth-gw-wan` with DiffServ4 counters | Live kernel `tc` | **VERIFIED** | Live counter delta before/after must be proven on fresh run. |
| **"Scenario A Bufferbloat Reduction"** | Report Sec 9, `scenario_a_hardware_*.json` | Baseline 100.68 ms $\rightarrow$ Adaptive 0.777 ms | Socket telemetry | **PROVISIONALLY VERIFIED** | Must execute $\ge 3$ repeated runs for baseline and adaptive, recording exact `tc` state. |
| **"Scenario B Capacity Resizing"** | Report Sec 10, `scenario_b_hardware.json` | `decide_policy(20.0)` called with hardcoded capacity argument | Code analysis | **DISCREPANCY DETECTED** | Fix test script to use live passive/active capacity estimation. |
| **"Scenario C Fair Queuing"** | Report Sec 11, `scenario_c_hardware_*.json` | Text claimed 1.82/0.84/0.51, artifact showed 1.201/1.201/1.201 | Raw JSON vs Report | **DISCREPANCY DETECTED** | Re-run under true bandwidth saturation; recompute Jain index from raw byte counters. |
| **"Zero-Fabrication Adherence"** | Report Sec 18, `evidence.db` | 0 synthetic constants in DB | Database query | **VERIFIED** | Maintain strict zero-fabrication discipline. |

---

## 3. Action Plan for Phase 3.1 Forensic Reproduction

To resolve every identified discrepancy and achieve an unassailable engineering validation:

1. **Topology & Packet Path Verification**:
   - Rebuild clean 4-node topology (`lan1`, `lan2`, `gw`, `wanhost`).
   - Run `tcpdump` / socket capture concurrently on `veth-lan1-gw`, `veth-gw-wan`, and `veth-wan-gw` to generate real `.pcap` files (`phase3_1_packet_path_ipv4.pcap`, `phase3_1_packet_path_ipv6.pcap`).
   - Audit IP TTL decrement (64 $\rightarrow$ 63), IPv6 Hop Limit decrement (64 $\rightarrow$ 63), and DSCP retention across the router boundary.
2. **CAKE Live Telemetry & Counter Deltas**:
   - Snapshot `tc -s qdisc show dev veth-gw-wan` before traffic.
   - Transmit classified flows (EF, AF41, CS1, CS0).
   - Snapshot `tc -s qdisc show dev veth-gw-wan` after traffic and verify counter deltas match transmitted packets.
3. **Capacity Estimator & Scenario B Dynamic Loop**:
   - Implement real throughput measurement on the gateway during link degradation.
   - Measure detection latency, decision latency, and enforcement latency from actual timestamps.
4. **Scenario A & C Multi-Run Statistical Reproduction**:
   - Execute $\ge 3$ independent runs for Baseline and $\ge 3$ for Adaptive.
   - In Scenario C, saturate link to prove CAKE fair distribution vs FIFO starvation.
   - Record distributions: mean, median, min, max, standard deviation.
5. **Genuine $\ge 10$-Minute Long-Run Stability Test**:
   - Execute continuous closed-loop control with background traffic for 10 full minutes (600 seconds $\approx 30,000$ cycles).
   - Sample CPU utilization, RSS memory footprint, cycle deadline misses, and policy transitions continuously.
6. **Artifact Manifest & Final Acceptance Matrix**:
   - Generate SHA-256 cryptographic hashes for all evidence files.
   - Re-audit all 37 acceptance criteria with rigorous classification:
     - Multi-node virtual datapath criteria: VERIFIED.
     - Physical NIC hardware criteria: ENVIRONMENT-LIMITED.
