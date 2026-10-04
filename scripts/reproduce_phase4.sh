#!/usr/bin/env bash
# End-to-End Production Reproducibility Script for Phase 4
set -euo pipefail

echo "=========================================================="
echo "Phase 4 End-to-End Production Reproduction Suite"
echo "=========================================================="

FAILED=0

# 1. Environment & Kernel Interrogation
echo "[+] Step 1: Environment & Kernel Interrogation..."
./venv/bin/python3 scripts/verify_hardware_or_environment.py

# 2. Automated Test Suite (39 Tests)
echo "[+] Step 2: Running Automated Unit & Integration Tests (39 Tests)..."
./venv/bin/python3 -m unittest discover tests

# 3. Independent Phase 3.1 & 3.2 Validators
echo "[+] Step 3: Running Independent Validators..."
./venv/bin/python3 scripts/validate_phase3_1_live_kernel.py
./venv/bin/python3 scripts/validate_phase3_1_packet_path.py
./venv/bin/python3 scripts/validate_phase3_1_evidence_db.py
./venv/bin/python3 scripts/validate_phase3_1_zero_fabrication.py
./venv/bin/python3 scripts/validate_phase3_1_classifier_lineage.py

# 4. Production Deployment & Interface Verification
echo "[+] Step 4: Verifying Production Deployment & Non-Loopback Interface Discovery..."
./scripts/verify_production.sh

# 5. Operational Failure Recovery Audit
echo "[+] Step 5: Running Failure Recovery & Watchdog Audit..."
./venv/bin/python3 scripts/run_phase4_failure_recovery.py

# 6. Scalability & Performance Benchmark
echo "[+] Step 6: Running Scalability & Performance Benchmark..."
./venv/bin/python3 scripts/run_phase4_scalability.py

echo "=========================================================="
echo "[SUCCESS] Complete Phase 4 Reproduction Suite Finished Cleanly."
echo "=========================================================="
