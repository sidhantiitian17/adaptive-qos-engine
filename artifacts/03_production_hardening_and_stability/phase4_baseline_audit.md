# Phase 4 Baseline Read-Only Engineering Audit

**Project:** Case Study 3 — Adaptive QoS Engine for Mixed Home Broadband Traffic  
**Phase:** Phase 4 Baseline Audit (Read-Only)  
**Date:** 2026-10-03  
**Auditor:** Principal Backend & Systems Auditor  

---

## 1. Audit Overview & Verification Baseline

Before initiating Phase 4 operational hardening, deployment engineering, and security hardening, a complete read-only baseline audit of the Phase 3.2 verified system was conducted.

### Core Architecture & State Unification
- **Process Architecture:** Unified single engine process (`dashboard/unified_dashboard.py` running FastAPI control plane and `AdaptiveQoSController` in the same memory space).
- **Authoritative FlowTable:** `controller.flow_table` is the single source of truth for flow tracking and classification.
- **Authoritative Scheduler:** `controller.scheduler` holds active user intents with automatic timestamp expiration.
- **Authoritative Rollback:** `controller.rollback_mgr` tracks tentative vs permanent tc configurations with verified rollback logic.
- **Authoritative Marking:** `controller.dscp_marker` synchronizes Layer-3 DSCP tags with classified flows.
- **Classification Engine:** Real zero-payload XGBoost classifier inspecting packet length distribution, inter-arrival times, and transport headers (no payload inspection).
- **Datapath Placement:** CAKE qdisc strictly attached to router WAN egress (`veth-gw-wan`) with `diffserv4` tins. NetEm delay (15 ms) and jitter (2 ms) attached to `wanhost` egress (`veth-wan-gw`).

---

## 2. Quantitative System Baseline

| Metric Domain | Baseline Metric Value | Verification Source |
|---|---|---|
| **Unit/Integration Tests** | **26 / 26 PASS** (100% passing) | `python -m unittest discover tests` (Ran in 19.45s) |
| **Independent Validators** | **5 / 5 PASS** | `scripts/validate_phase3_1_*.py` |
| **Evidence Database** | **8 tables, 0 orphan records** | `experiments/evidence.db` via `sqlite3` foreign keys |
| **Database Record Breadth** | 113 experiments, 92 runs, 149 flows, 559 measurements, 0 errors | Independent SQL query |
| **Autonomous Cycle Time** | Mean: **8.027 ms**, p95: **8.567 ms**, p99: **10.826 ms** | `phase3_1_long_run.json` (24,646 cycles) |
| **Deadline Misses** | **0 / 24,646 cycles (0.0%)** | `phase3_1_long_run.json` |
| **Memory Footprint** | Initial RSS: **163.47 MB**, Final RSS: **164.60 MB** (+1.12 MB) | `phase3_1_resource_usage.json` (600.6s run) |
| **Memory Trend** | Flat across 107/117 intervals, slope 0.089 MB/min | Linear fit over 118 samples |
| **Policy Oscillation** | **0 unintended transitions** (0.0 transitions/min) | `phase3_1_policy_oscillation.json` |
| **Scenario A Latency** | Baseline: **101.706 ms** -> Adaptive: **0.700 ms** (-99.31%) | `phase3_1_scenario_a_analysis.json` |
| **Scenario A Jitter** | Baseline: **13.5718 ms** -> Adaptive: **0.2495 ms** (-98.16%) | `phase3_1_scenario_a_analysis.json` |
| **Scenario B Adaptation** | Total reaction time: **0.1042 seconds** (Target $\le 1.0\text{s}$) | `phase3_1_scenario_b_timeline.json` |
| **Scenario B Recovery** | Total restoration time: **0.0420 seconds** (Target $\le 1.0\text{s}$) | `phase3_1_scenario_b_timeline.json` |
| **Scenario C Gaming RTT** | Baseline: **134.303 ms** -> Adaptive: **15.725 ms** (-88.29%) | `phase3_1_scenario_c_analysis.json` |
| **Scenario C Fairness** | Raw byte Jain Index: **1.0000** | `phase3_1_scenario_c_raw.json` |
| **Zero-Fabrication Status** | **0 forbidden constants** (`21.2`, `84.5`, `42.0`) | `validate_phase3_1_zero_fabrication.py` |
| **Cryptographic Manifest** | **68 artifacts tracked** with SHA-256 bit-for-bit matches | `phase3_2_artifact_manifest.json` |

---

## 3. Network Datapath & Topology Baseline

- **Environment:** Linux kernel `6.18.40.1-microsoft-standard-WSL2+` (Ubuntu 24.04 LTS).
- **Topology:** 4 isolated network namespaces:
  - `lan1`: `10.0.1.2/24`, `fc00:1::2/64` (default via `10.0.1.1` / `fc00:1::1`)
  - `lan2`: `10.0.2.2/24`, `fc00:2::2/64` (default via `10.0.2.1` / `fc00:2::1`)
  - `gw`: Layer-3 router with IP forwarding enabled (`net.ipv4.ip_forward=1`, `net.ipv6.conf.all.forwarding=1`).
    - Interfaces: `veth-gw-lan1` (`10.0.1.1/24`), `veth-gw-lan2` (`10.0.2.1/24`), `veth-gw-wan` (`10.0.3.1/24`).
    - Active qdisc: `cake bandwidth 100Mbit diffserv4` attached to `veth-gw-wan`.
  - `wanhost`: `10.0.3.2/24`, `fc00:3::2/64` (default via `10.0.3.1` / `fc00:3::1`).
    - Active qdisc: `netem delay 15ms 2ms` attached to `veth-wan-gw`.
- **Packet Forwarding Provenance:**
  - Dual-interface packet captures verify Layer-3 decrement:
    - IPv4: Ingress TTL 64 on `veth-lan1-gw` $\rightarrow$ Egress TTL 63 on `veth-gw-wan`.
    - IPv6: Ingress Hop Limit 64 on `veth-lan1-gw` $\rightarrow$ Egress Hop Limit 63 on `veth-gw-wan`.
  - DSCP values (`0xb8`, `0x88`, `0x20`, `0x00`) preserved across router hops into corresponding DiffServ4 tins.

---

## 4. Current Security Posture & API Exposure

- **API Binding:** `127.0.0.1:8000` (FastAPI / Uvicorn).
- **Subprocess Security:** All shell commands in `TcManager`, `rollback_manager`, and `metrics_collector` pass argument lists (`subprocess.run(["tc", ...])`) avoiding `shell=True` injection vulnerabilities.
- **Rootless Execution:** Unshare wrapper allows non-root users with user namespaces to safely control virtual datapaths without broad host privilege escalation.
- **Payload Privacy:** Classifier only extracts transport headers and packet arrival statistics. Raw packet payloads are never stored, logged, or inspected.

---

## 5. Areas for Phase 4 Hardening

While the Phase 3.2 system achieved verified status across 36 software/kernel criteria, Phase 4 requires the following operational and production enhancements:

1. **Production Deployment Model:** Standalone systemd/service integration, clean installation (`scripts/install_production.sh`), uninstallation, and configuration management without development dependencies.
2. **Real Interface Discovery:** Robust interface discovery for host-level multi-NIC deployments, detecting default routes, driver, speed, and MTU without guessing or defaulting to `lo`.
3. **Hardware Acceptance Verification:** Explicit checking for physical NIC availability. When physical NICs are absent, maintaining the `ENVIRONMENT-LIMITED` classification without fabrication.
4. **Enhanced API Validation & Security:** Strict validation of intent endpoints, rate limits, token authentication headers where applicable, and input sanitization on all endpoints.
5. **Observability Expansion:** Adding standardized `/health`, `/readiness`, `/api/network/status`, and structured JSON logging with error codes and transaction IDs.
6. **Scalability & Stress Testing:** Load testing the FlowTable and controller under 10, 25, 50, and 100 concurrent flows to establish true empirical overhead bounds.
7. **Anti-Starvation Verification:** Empirical demonstration that background bulk flows maintain guaranteed throughput floor (minimum 20% capacity) during sustained high-priority contention.
8. **Automated Clean-Environment Reproduction:** Standalone `scripts/reproduce_phase4.sh` capable of rebuilding, validating, and generating fresh cryptographic manifests.

*Status: Baseline Audit Complete. Proceeding to Phase 4 Operational Implementation.*
