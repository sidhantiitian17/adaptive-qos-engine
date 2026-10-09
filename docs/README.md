# Adaptive QoS Engine: Documentation Index

Welcome to the documentation suite for the Adaptive QoS Engine for Mixed Home Broadband Traffic.

---

## 1. Getting Started & Operations

- **[Setup Guide](setup_guide.md)**: System requirements, dependencies, and environment initialization.
- **[User & Demonstration Guide](demo_guide.md)**: Running the 24-step acceptance demo and launching the operations dashboard.
- **[Troubleshooting Guide](troubleshooting.md)**: Diagnosing and resolving common runtime errors.
- **[Production Deployment Guide](phase4_deployment.md)**: Systemd service management, signal handling, and zero-downtime operations.

---

## 2. Architecture & Technical Design

- **[Architecture Specification](architecture.md)**: Deep dive into the 4-node routed topology, zero-payload ML classifier, deterministic policy engine, and Linux kernel CAKE queue discipline.
- **[Module M2: Link Capacity Estimator Specification](m2_link_estimator.md)**: SLoPS-style active probing engine based on Jain–Dovrolis methodology, state machine, hysteresis damping, and ground-truth evaluation results.
- **[Known Limitations](known_limitations.md)**: Hardware boundary, virtual environment constraints, and scaling characteristics.
- **[WSL2 / Linux Kernel Build Guide](kernel_build.md)**: Enabling `sch_cake` and `sch_netem` on custom Linux kernels.

---

## 3. Case Study Analysis & Historical Requirements

Historical requirements, problem statements, and phase compliance reports are preserved in [`docs/case_study_analysis/`](case_study_analysis/):
- **[`ps3.md`](case_study_analysis/ps3.md)**: Case Study 3 problem statement and requirements specification.
- **[`PS3_COMPLIANCE_CRITICAL_ANALYSIS.md`](case_study_analysis/PS3_COMPLIANCE_CRITICAL_ANALYSIS.md)**: Detailed compliance evaluation against problem requirements.
- **[`PS3_FINAL_VERIFICATION_REPORT.md`](case_study_analysis/PS3_FINAL_VERIFICATION_REPORT.md)**: Pre-audit implementation verification report.
- **[`CONTEXT (1).md`](case_study_analysis/CONTEXT%20%281%29.md)**: Architectural planning notes and reference guidelines.
- **[`CONTEXT_GAP_ANALYSIS.md`](case_study_analysis/CONTEXT_GAP_ANALYSIS.md)**: Gap analysis between initial plans and codebase reality.
- **[`IMPLEMENTATION_PLAN.md`](case_study_analysis/IMPLEMENTATION_PLAN.md)**: Multi-phase engineering roadmap.
- **[`FINAL_DEMO_REPORT.md`](case_study_analysis/FINAL_DEMO_REPORT.md)**: Initial prototype demo execution log.

---

## 4. Project Artifacts & Forensic Evidence

All formal acceptance matrices, cryptographic manifests, and raw experiment results are consolidated under [`artifacts/`](../artifacts/):
- **[`artifacts/01_forensic_acceptance_audit/`](../artifacts/01_forensic_acceptance_audit/)**: Initial independent forensic audit logs, baseline inspection, and zero-fabrication scan.
- **[`artifacts/02_virtual_datapath_verification/`](../artifacts/02_virtual_datapath_verification/)**: 4-node routed topology rebuild, dual-interface PCAPs, TTL decrement, and CAKE tin deltas.
- **[`artifacts/03_production_hardening_and_stability/`](../artifacts/03_production_hardening_and_stability/)**: 10-minute sustained run, zero memory leak analysis, failure recovery, and anti-starvation proofs.
- **[`artifacts/04_final_release_acceptance/`](../artifacts/04_final_release_acceptance/)**: Final release acceptance report, 37-criterion matrix, 24-step demo trace, and SHA-256 manifests.

See [`artifacts/README.md`](../artifacts/README.md) for full artifact lineage.
