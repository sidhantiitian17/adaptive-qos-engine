# Adaptive QoS Engine: Project Artifacts Directory

This directory consolidates all forensic acceptance audit evidence, Linux kernel datapath measurements, operational hardening traces, and final release deliverables for the Adaptive QoS Engine.

---

## Artifact Progression & Directory Overview

```
artifacts/
├── 01_forensic_acceptance_audit/          # Initial independent forensic audit
├── 02_virtual_datapath_verification/      # 4-node routed topology & packet capture
├── 03_production_hardening_and_stability/ # 10-min long run, zero-leak & recovery
├── 04_final_release_acceptance/           # 24-step demo, final matrix & sign-off
└── README.md                              # This directory guide
```

---

## Directory Details & Clear Purpose

### 1. `01_forensic_acceptance_audit/` (formerly `audit_artifacts`)
- **Clear Purpose:** Contains the initial independent forensic acceptance audit of the baseline engine implementation.
- **Key Evidence:**
  - `audit_matrix.md`: Initial criterion-by-criterion forensic audit matrix.
  - `audit_summary.md`: Summary of discrepancies and baseline findings.
  - `zero_fabrication_scan.txt`: Initial AST scan verifying absence of canned numbers.
  - `db_integrity_report.json`: Relational validation of `evidence.db`.
  - `tc_qdisc_evidence.txt`: Kernel netlink qdisc inspection dump.

---

### 2. `02_virtual_datapath_verification/` (formerly `phase3_artifacts`)
- **Clear Purpose:** Contains evidence for the true multi-node Linux virtual routed datapath (`lan1`, `lan2`, `gw`, `wanhost`).
- **Key Evidence:**
  - `phase3_1_packet_path_ipv4.pcap`: Dual-interface PCAP capture proving packet traversal across gateway.
  - `phase3_1_packet_path_analysis.json`: Independent verification of IPv4 TTL (`64 -> 63`) and IPv6 Hop Limit decrement.
  - `phase3_1_dscp_path_trace.json`: Zero DSCP bleaching across router forwarding hops.
  - `phase3_1_cake_counter_delta.json`: Live kernel packet increments across DiffServ tins (`Voice`, `Video`, `BestEffort`, `Bulk`).
  - `phase3_1_rtt_samples.json`: Nanosecond UDP RTT samples under NetEm 15ms WAN delay.

---

### 3. `03_production_hardening_and_stability/` (formerly `phase4_artifacts`)
- **Clear Purpose:** Contains operational hardening, sustained reliability, failure recovery, and stress testing records.
- **Key Evidence:**
  - `phase4_long_run.json`: 10-minute continuous production run (20,003 cycles, 7.65 ms cycle latency).
  - `phase4_1_memory_analysis.md`: Detailed resident set size (RSS) drift analysis (+0.08 MB over 10 min, zero memory leak).
  - `phase4_failure_recovery.json`: 8 daemon failure modes (SIGTERM, SIGKILL, DB locks, bad policy injection, auto-rollback).
  - `phase4_scalability.json`: 10,000-flow concurrency and FlowTable lock contention benchmark.
  - `phase4_2_1_anti_starvation_closure.md`: Mathematical proof of 20% guaranteed bulk floor (`max(2, round(shaping * 0.20))`).

---

### 4. `04_final_release_acceptance/` (formerly `phase6_artifacts`)
- **Clear Purpose:** Contains the authoritative deliverables for final software release sign-off and end-to-end acceptance.
- **Verdict:** **`PRODUCTION READY WITH ENVIRONMENT LIMITATIONS`** (36/37 criteria verified, 1 environment-limited).
- **Key Evidence:**
  - `phase6_final_release_acceptance_report.md`: Formal acceptance sign-off document.
  - `phase6_acceptance_matrix.md`: Exhaustive 37-criterion evaluation matrix.
  - `phase6_end_to_end_test_report.md`: Full 24-step demonstration execution trace.
  - `phase6_scenario_results.json`: Empirical measurements (Scenario A: 99.52% latency reduction; Scenario B: 0.048s adaptation; Scenario C: 0.9999998 Jain fairness).
  - `phase6_kpi_recalculation.md`: First-principles mathematical derivation of all KPIs.
  - `phase6_zero_fabrication_audit.md`: Rigorous audit proving 0 synthetic constants across all 744 database records.
  - `phase6_artifact_manifest.json`: Cryptographic SHA-256 hashes for all generated release deliverables.
  - `phase6_provenance_manifest.json`: Host kernel, OS, and dataset lineage.
