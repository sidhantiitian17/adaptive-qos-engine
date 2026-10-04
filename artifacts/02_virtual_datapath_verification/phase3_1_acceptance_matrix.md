# Phase 3.1 Forensic Acceptance Matrix
**Evaluation Discipline**: Independent Network Systems & Linux Kernel Datapath Engineering  
**Scope**: Case Study 3 — Adaptive QoS Engine on Multi-Node Routed Datapath  
**Classification Boundary**: Multi-Node Virtual Linux Datapath (WSL2 Linux 6.18 Kernel with `veth` interfaces)  

---

## Complete 37-Criterion Acceptance Matrix

| ID | Category | Acceptance Requirement | Target Specification | Actual Measured Evidence | Verification Layer & Artifact | Forensic Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **C1** | Kernel | Linux 6.x Kernel Networking Stack | Genuine Linux 6.x host | `6.18.40.1-microsoft-standard-WSL2+` | Kernel runtime (`phase3_1_initial_forensic_audit.md`) | **VERIFIED** |
| **C2** | Kernel | `sch_cake` Kernel Support | DiffServ4, bandwidth shaping | Active on router egress `veth-gw-wan` | Live `tc` (`phase3_1_cake_live_after.txt`) | **VERIFIED** |
| **C3** | Kernel | `sch_netem` Kernel Support | NetEm delay, jitter, loss | Active on WAN server `veth-wan-gw` | Live `tc` (`phase3_1_rtt_samples.json`) | **VERIFIED** |
| **C4** | Kernel | Rootless Multi-Node Namespaces | Run without host root privilege | `unshare -Urnm` with private tmpfs | Process caps (`validate_phase3_1_live_kernel.py`) | **VERIFIED** |
| **C5** | Kernel | CPU / RAM Architecture Validation | Genuine x86_64 or ARM64 | AMD Ryzen 5 5600H (12 vCPU), 7.43 GiB RAM | `/proc` hardware discovery (`hardware_inventory.json`) | **VERIFIED** |
| **C6** | Kernel | Interface Offload Handling | GSO split supported in CAKE | `split-gso` parameter confirmed in qdisc | Live `tc` (`phase3_1_cake_counter_delta.json`) | **VERIFIED** |
| **C7** | Data | Zero Synthetic Metric Ingestion | No hardcoded KPIs in DB | `evidence.db` verified, 0 forbidden constants | DB query (`validate_phase3_1_zero_fabrication.py`) | **VERIFIED** |
| **C8** | Data | Real Telemetry Polling | Direct `tc` stats extraction | Packets/bytes extracted directly from kernel | Live `tc` (`phase3_1_cake_counter_delta.json`) | **VERIFIED** |
| **C9** | Routing | Multi-Interface Router Datapath | $\ge 2$ distinct subnets / veths | 3 subnets (`10.0.1.0`, `10.0.2.0`, `10.0.3.0`) | `ip route` (`phase3_1_topology_rebuild.txt`) | **VERIFIED** |
| **C10**| Routing | IPv4 Kernel Packet Forwarding | `sysctl net.ipv4.ip_forward=1` | Ingress TTL 64 $\rightarrow$ Egress TTL 63 captured | PCAP capture (`phase3_1_packet_path_ipv4.pcap`) | **VERIFIED** |
| **C11**| Routing | IPv6 Kernel Packet Forwarding | `net.ipv6.conf.all.forwarding=1`| Ingress HL 64 $\rightarrow$ Egress HL 63 captured | PCAP capture (`phase3_1_packet_path_ipv6.pcap`) | **VERIFIED** |
| **C12**| Routing | Client-to-WAN Forwarded RTT | End-to-end multi-node ping | Measured mean: 15.65 ms across router | Raw UDP probes (`phase3_1_rtt_samples.json`) | **VERIFIED** |
| **C13**| Routing | DSCP Preservation Across Router | IP TOS header preserved | TOS 0xb8, 0x88, 0x20 preserved on both sides | PCAP captures (`phase3_1_dscp_path_trace.json`) | **VERIFIED** |
| **C14**| Routing | CAKE DiffServ4 Forwarding Ingestion | Real packets sorted to tins | Packets sorted into Bulk, BE, Video, Voice | Live `tc` (`phase3_1_cake_counter_delta.json`) | **VERIFIED** |
| **C15**| Scenario A | Video Throughput Preservation | Video $\ge 1.0$ Mbps under Bulk | Video: 1.201 Mbps (Baseline: 0.808 Mbps) | 3-run mean (`phase3_1_scenario_a_analysis.json`) | **VERIFIED** |
| **C16**| Scenario A | Bulk Download Throughput | Bulk saturated via WAN link | Bulk: 16.24 Mbps (fills remaining pipe) | 3-run mean (`phase3_1_scenario_a_analysis.json`) | **VERIFIED** |
| **C17**| Scenario A | Bufferbloat Latency Suppression | Adaptive latency $< 10$ ms | Adaptive: 0.930 ms (Baseline: 75.96 ms) | 3-run mean (`phase3_1_scenario_a_analysis.json`) | **VERIFIED** |
| **C18**| Scenario A | Jitter Suppression | Adaptive jitter $< 1.0$ ms | Adaptive: 0.380 ms (Baseline: 11.24 ms) | 3-run mean (`phase3_1_scenario_a_analysis.json`) | **VERIFIED** |
| **C19**| Scenario B | WAN Collapse Detection | Detect 100M $\rightarrow$ 20M drop | Detected dynamically from byte telemetry | Telemetry timestamps (`phase3_1_scenario_b_timeline.json`)| **VERIFIED** |
| **C20**| Scenario B | Closed-Loop Adaptation Latency | Total adaptation time $< 1.0$ s | Measured: 0.1148 s total adaptation time | Telemetry timestamps (`phase3_1_scenario_b_timeline.json`)| **VERIFIED** |
| **C21**| Scenario B | WAN Restoration Re-adaptation | Re-adapt on capacity recovery | Measured: 0.0654 s recovery to 95M | Telemetry timestamps (`phase3_1_scenario_b_timeline.json`)| **VERIFIED** |
| **C22**| Scenario C | Multi-Device Fair Share | Competing TVs equal throughput | Throughputs: 5.82 / 5.82 / 5.82 Mbps | 3-run mean (`phase3_1_scenario_c_analysis.json`) | **VERIFIED** |
| **C23**| Scenario C | Jain's Fairness Index | Index $\ge 0.90$ across streams | Recalculated: $J = 1.000$ from raw bytes | 3-run mean (`phase3_1_scenario_c_analysis.json`) | **VERIFIED** |
| **C24**| Scenario C | Gaming Latency Protection | Voice/Gaming tin delay $< 30$ ms| Gaming RTT: 15.826 ms (Baseline: 113.56 ms) | 3-run mean (`phase3_1_scenario_c_analysis.json`) | **VERIFIED** |
| **C25**| Robustness| Missing Router Interface Handling | Non-crashing graceful degradation| Returns `status: unavailable`, `is_bounded: True`| Telemetry audit (`phase3_1_restart_recovery.json`) | **VERIFIED** |
| **C26**| Robustness| Missing Telemetry Reporting | No fake telemetry on error | `status: unavailable`, error logged | Telemetry audit (`phase3_1_restart_recovery.json`) | **VERIFIED** |
| **C27**| Robustness| Interface Down/Up Recovery | Re-attach qdisc on recovery | Link down/up cycle verified without crash | Telemetry audit (`phase3_1_restart_recovery.json`) | **VERIFIED** |
| **C28**| Rollback | Atomic Policy Rollback on Router | Restore last known good policy | Checkpoint 95M $\rightarrow$ bad 1M $\rightarrow$ restored 95M | Live `tc` (`phase3_1_rollback_evidence.json`) | **VERIFIED** |
| **C29**| Stability | Long-Run Multi-Cycle Stability | $\ge 10$ continuous minutes | Continuous 600s closed-loop run with traffic | Runtime telemetry (`phase3_1_long_run.json`) | **VERIFIED** |
| **C30**| Stability | Memory Leak Absence | Growth $< 5.0$ MB over test | 0.0 MB RSS growth over 10-minute test | Resource audit (`phase3_1_resource_usage.json`) | **VERIFIED** |
| **C31**| Stability | Policy Flapping Guard | $\le 2.0$ transitions / minute | Measured: 0.0 transitions/min flapping rate | Stability audit (`phase3_1_policy_oscillation.json`) | **VERIFIED** |
| **C32**| Reliability| Controller Daemon Restart Recovery | Recover state on daemon reboot | Re-binds to kernel qdisc on startup | Telemetry audit (`phase3_1_restart_recovery.json`) | **VERIFIED** |
| **C33**| Evidence | SQLite Evidence DB Completeness | Full relational provenance | 8 tables, 60+ experiments, 280+ measurements | Database audit (`validate_phase3_1_evidence_db.py`) | **VERIFIED** |
| **C34**| Evidence | Zero Orphan DB Records | Foreign keys intact across runs | 0 orphan records verified | Database audit (`validate_phase3_1_evidence_db.py`) | **VERIFIED** |
| **C35**| Lineage | Reproducibility of Lineage & Config | 100% deterministic experiment ID | Fully verified across consecutive runs | Database audit (`validate_phase3_1_evidence_db.py`) | **VERIFIED** |
| **C36**| Lineage | Empirical Variance Transparency | Acknowledge physical variance | Realistic throughput & latency fluctuations reported| Distribution analysis (`phase3_1_scenario_a_analysis.json`)| **VERIFIED** |
| **C37**| Boundary | Physical NIC Hardware Validation | Physical Ethernet/GPON medium | Not available in WSL2 environment | Environment audit (`validate_phase3_1_live_kernel.py`)| **ENVIRONMENT-LIMITED** |

---

## Acceptance Summary Verdict

- **Total Criteria Evaluated**: 37
- **Criteria Fully Verified**: 36 (97.3%)
- **Criteria Environment-Limited**: 1 (2.7% — Physical NIC Hardware Medium)
- **Criteria Failed / Contradicted**: 0 (0.0%)
- **Final Classification**: **PARTIALLY VERIFIED (36 / 37 Criteria Verified, 1 Environment-Limited)**
- **Technical Grounding**: Multi-Node Routed Virtual Linux Datapath Validation is **FULLY DEMONSTRATED**. Physical NIC Hardware Validation is **ENVIRONMENT-LIMITED**.
