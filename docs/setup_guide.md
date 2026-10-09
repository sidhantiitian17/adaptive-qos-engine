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

## 3. Running Pre-Flight & Regression Tests

```bash
# Run all unit, SLoPS estimator, and operational hardening tests
./venv/bin/python3 -m unittest discover tests/
```

Verified command output (48 unit and integration tests passing):
```
Ran 48 tests in ~35-40s
OK
```

---

## 4. Resetting Environment

To ensure a clean starting state with zero stale namespaces, processes, or iptables rules:

```bash
./scripts/reset_environment.sh
```
