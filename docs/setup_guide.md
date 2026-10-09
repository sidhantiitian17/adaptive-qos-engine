# Adaptive QoS Engine: Quick Start & Setup Guide

## 1. System Requirements
- **OS:** Linux x86_64 or ARM64 (Ubuntu 22.04 LTS / 24.04 LTS, Debian 12, or WSL2)
- **Kernel:** Linux 5.15+ with `sch_cake`, `sch_netem`, `veth`, and `iptables`/`nftables` support
- **Python:** Python 3.10+ (Python 3.12 recommended)
- **Permissions:** Root access or `CAP_NET_ADMIN` capabilities for netlink qdisc and namespace configuration

---

## 2. Environment Setup

```bash
# 1. Clone repository
git clone https://github.com/sidhantiitian17/adaptive-qos-engine.git
cd adaptive-qos-engine

# 2. Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install core dependencies
pip install --upgrade pip
pip install -r requirements.txt
# Or minimal core packages (Note: sqlite3 is included in Python's standard library):
# pip install fastapi uvicorn pydantic scikit-learn xgboost torch httpx
```

---

## 3. Running Pre-Flight & Regression Tests (Unprivileged)

All core module unit tests, SLoPS estimator algorithmic logic, state unification, and operational hardening tests execute without requiring root privileges:

```bash
# Run all unit and regression tests (no sudo required)
./venv/bin/python3 -m unittest discover tests/
```

Verified command output (57 unit and regression tests passing):
```
Ran 57 tests in ~31-32s (measured: 30.9-32.0s on Linux 6.6 / WSL2)
OK
```

### Module-Specific Unit Tests
Individual test suites can be executed independently:

```bash
# M2 SLoPS Estimator algorithmic logic (PCT, PDT, loopback, state machine, fallback)
./venv/bin/python3 -m unittest tests/test_m2_slops_estimator.py

# M2 Metric consistency & interval containment validation
./venv/bin/python3 -m unittest tests/test_m2_consistency.py

# M3 / M6 Unified state machine and rollback protection
./venv/bin/python3 -m unittest tests/test_state_unification.py

# M5 / Observability & operational hardening
./venv/bin/python3 -m unittest tests/test_phase4_operational_hardening.py

# M1 Classifier runtime inference
./venv/bin/python3 classifier/runtime_classifier.py

# M7 Laya Natural Language Intent Parser
./venv/bin/python3 api/test_laya.py
```

---

## 4. Running Privileged Integration Tests & M2 Ground-Truth Evaluation

Running active probing over Linux network namespaces, rate shaping with `tc netem`, or CAKE qdisc enforcement requires Linux root privileges (`sudo`) and kernel modules (`sch_cake`, `sch_netem`):

```bash
# 1. Setup the 4-namespace virtual testbed topology (lan1, lan2, gw, wanhost)
sudo ./testbed/setup_topo.sh

# 2. Run the end-to-end M2 Link Capacity Estimator ground-truth evaluation suite
# (Tests 1-6 across NetEm rate changes, dynamic drops, bursty cross-traffic, and baseline comparison)
sudo ./venv/bin/python3 experiments/run_m2_evaluation.py

# 3. Output artifacts are generated in results/m2/:
# results/m2/summary.csv, results/m2/report.md, results/m2/*.json
```

---

## 5. Running End-to-End Testbed Scenarios

To reproduce full system QoS scenarios comparing default FIFO queueing against Adaptive QoS Engine:

```bash
# Scenario 1: Bulk Transfer vs Interactive Video Conference (Bufferbloat mitigation)
sudo ./experiments/test_scenario1_bulk_vs_video.sh

# Scenario 2: WAN Capacity Drop & Dynamic Throttling Adaptation
sudo ./experiments/test_scenario2_wan_drop.sh

# Scenario 3: Multi-Device Contention & Policy Floor Fairness
sudo ./experiments/test_scenario3_multi_device.sh
```

---

## 6. Resetting Environment & Enforcement Rollback

To tear down all testbed namespaces, release virtual ethernet interfaces, flush iptables DSCP markers, and revert kernel qdiscs to clean defaults:

```bash
# Clean reset of all testbed resources and background processes
sudo ./scripts/reset_environment.sh

# Alternatively, manual rollback of CAKE qdisc to safe default
sudo ./enforcement/rollback.sh
```
