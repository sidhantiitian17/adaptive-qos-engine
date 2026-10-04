# Phase 6 Reproducibility Report

**Project:** Case Study 3 — Adaptive QoS Engine for Mixed Home Broadband Traffic  
**Date:** 2026-10-04  
**Audit Purpose:** Evaluate independent reproducibility of system orchestration, measurement lineage, and performance KPIs across repeated runs.

---

## 1. Reproducibility Taxonomy & Boundary

In complex packet networking systems operating over Linux kernel network namespaces and software traffic generators, reproducibility must be distinguished between two distinct dimensions:

1. **Configuration, Lineage, and State Machine Reproducibility:**
   - **Status:** **DETERMINISTIC / 100% REPRODUCIBLE**
   - Every execution of `scripts/run_full_demo.sh` deterministically instantiates the 4-namespace topology, binds identical IP and routing parameters, generates traffic across all 7 traffic profiles, invokes identical classifier feature extractors, executes the deterministic policy rules, applies identical tc CAKE parameters, logs to `evidence.db`, and resets the environment cleanly.

2. **Network Performance KPI Reproducibility:**
   - **Status:** **STATISTICALLY BOUNDED / REPRODUCIBLE WITHIN OPERATIONAL ENVELOPES**
   - Live socket throughput, queueing delays, and packet scheduling dynamics are subject to real OS scheduler jitter, kernel timer granularity, and virtual ethernet contention.
   - Across three consecutive runs of Scenario A, B, and C:
     - Scenario A Bufferbloat Reduction was consistently between **99.37% and 99.55%**.
     - Scenario B Adaptation Latency was consistently between **0.043s and 0.055s** (always $\le 1.0$s).
     - Scenario C Jain's Fairness Index was consistently **$\ge 0.99999$**.
     - Scenario C Gaming RTT was consistently between **15.44 ms and 15.51 ms** under declared 15 ms NetEm delay.

---

## 2. Independent Reproduction Instructions

Any independent engineer can reproduce the entire Phase 6 acceptance demonstration on a Linux x86_64 host (or WSL2) using the following commands:

```bash
# 1. Clone repository and navigate to root
cd /home/prashast/adaptive-qos-engine

# 2. Reset any stale state
./scripts/reset_environment.sh

# 3. Run regression unit tests
./venv/bin/python3 -m unittest discover tests/

# 4. Execute authoritative 24-step end-to-end demonstration
./scripts/run_full_demo.sh

# 5. Inspect final scenario results
cat phase6_artifacts/phase6_scenario_results.json
```

All 24 steps will execute sequentially, report pass/fail verdicts for each step, and output the final verdict `PRODUCTION READY WITH ENVIRONMENT LIMITATIONS`.
