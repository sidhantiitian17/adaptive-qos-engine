# Adaptive QoS Engine: Scripts Directory Guide

This directory contains automation, verification, orchestration, and benchmarking scripts for the Adaptive QoS Engine.

---

## 1. Core Demonstration & Operational Scripts

| Script | Purpose | Usage |
|:---|:---|:---|
| **`run_full_demo.sh`** | **Authoritative 24-Step End-to-End Demo** | `./scripts/run_full_demo.sh` |
| **`reset_environment.sh`** | **Deterministic Environment Reset & Cleanup** | `./scripts/reset_environment.sh` |
| `reset_environment.py` | Python implementation of post-run cleanup & database check | Called by `reset_environment.sh` |
| `run_full_demo.py` | Python implementation of 24-step acceptance workflow | Called by `run_full_demo.sh` |

---

## 2. Production Deployment & Systemd Scripts

| Script | Purpose | Usage |
|:---|:---|:---|
| `install_production.sh` | Installs controller & dashboard systemd services | `sudo ./scripts/install_production.sh` |
| `uninstall_production.sh` | Stops and removes systemd services | `sudo ./scripts/uninstall_production.sh` |
| `verify_production.sh` | Probes systemd units and REST health endpoints | `./scripts/verify_production.sh` |
| `verify_hardware_or_environment.py`| Inspects CPU, NICs, and virtualization environment | `./venv/bin/python3 scripts/verify_hardware_or_environment.py` |

---

## 3. Network Namespaces & Virtual Datapath Setup

| Script | Purpose | Usage |
|:---|:---|:---|
| `setup_netns.sh` | Builds 4-node routed topology (`lan1`, `lan2`, `gw`, `wanhost`) | `sudo ./scripts/setup_netns.sh` |
| `cleanup_netns.sh` | Deletes veth pairs and tears down namespaces | `sudo ./scripts/cleanup_netns.sh` |
| `verify_netns.sh` | Pings across namespaces to verify cross-hop IP routing | `sudo ./scripts/verify_netns.sh` |

---

## 4. Scenario Benchmarks

| Script | Purpose | Usage |
|:---|:---|:---|
| `run_scenario_a.sh` | Runs Scenario A: Baseline vs Adaptive bufferbloat | `sudo ./scripts/run_scenario_a.sh` |
| `run_scenario_b.sh` | Runs Scenario B: Dynamic WAN capacity drop & recovery | `sudo ./scripts/run_scenario_b.sh` |
| `run_scenario_c.sh` | Runs Scenario C: 3 TV streams + Gaming contention & fairness | `sudo ./scripts/run_scenario_c.sh` |

---

## 5. Audit & Forensic Acceptance Tools

| Script | Purpose |
|:---|:---|
| `validate_phase3_1_packet_path.py` | Verifies dual-interface PCAP packet capture and TTL decrement |
| `validate_phase3_1_live_kernel.py` | Queries live CAKE qdisc counters and DiffServ tin distributions |
| `validate_phase3_1_evidence_db.py` | Verifies relational integrity and zero orphans in `evidence.db` |
| `validate_phase3_1_classifier_lineage.py` | Traces multi-packet inference confidence progression |
| `validate_phase3_1_zero_fabrication.py` | Scans for synthetic numbers and hardcoded constants |
| `generate_phase4_manifests.py` | Computes SHA-256 hashes and generates Phase 4 manifests |
| `generate_phase4_1_manifests.py` | Computes SHA-256 hashes for Phase 4.1 audit artifacts |
| `reproduce_phase4.sh` | Full automated reproduction of Phase 4 production testbed |
