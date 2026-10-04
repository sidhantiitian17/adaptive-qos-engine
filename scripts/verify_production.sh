#!/usr/bin/env bash
# Production Verification Script for Adaptive QoS Engine
set -euo pipefail

echo "=========================================================="
echo "Verifying Adaptive QoS Engine Production Readiness"
echo "=========================================================="

FAILED=0

# 1. Check Python virtual environment & imports
echo -n "[1] Checking Python environment and ML classifier... "
if ./venv/bin/python3 -c "import xgboost, scapy, fastapi, uvicorn; print('OK')" >/dev/null 2>&1; then
    echo "PASS"
else
    echo "FAIL"
    FAILED=1
fi

# 2. Check Interface Discovery
echo -n "[2] Checking Interface Discovery & Non-Loopback WAN... "
DISCO_OUTPUT=$(./venv/bin/python3 network/interface_discovery.py 2>&1)
if echo "$DISCO_OUTPUT" | grep -q '"wan_interface":'; then
    WAN_IFACE=$(echo "$DISCO_OUTPUT" | grep '"wan_interface":' | awk -F'"' '{print $4}')
    if [[ "$WAN_IFACE" != "lo" && "$WAN_IFACE" != "localhost" ]]; then
        echo "PASS ($WAN_IFACE)"
    else
        echo "FAIL (Loopback detected: $WAN_IFACE)"
        FAILED=1
    fi
else
    echo "FAIL"
    FAILED=1
fi

# 3. Check Evidence DB Integrity
echo -n "[3] Checking Evidence DB Integrity... "
if ./venv/bin/python3 scripts/validate_phase3_1_evidence_db.py >/dev/null 2>&1; then
    echo "PASS (0 orphan records)"
else
    echo "FAIL"
    FAILED=1
fi

# 4. Check Zero-Fabrication
echo -n "[4] Checking Zero-Fabrication Violations... "
if ./venv/bin/python3 scripts/validate_phase3_1_zero_fabrication.py >/dev/null 2>&1; then
    echo "PASS (0 synthetic constants)"
else
    echo "FAIL"
    FAILED=1
fi

# 5. Check Packet Path & Routing Proof
echo -n "[5] Checking Layer-3 Routing & TTL Decrements... "
if ./venv/bin/python3 scripts/validate_phase3_1_packet_path.py >/dev/null 2>&1; then
    echo "PASS (TTL/Hop Limit decrements verified)"
else
    echo "FAIL"
    FAILED=1
fi

# 6. Check Hardware vs Environment Status
echo -n "[6] Checking Hardware Validation Status... "
HW_STATUS=$(./venv/bin/python3 scripts/verify_hardware_or_environment.py | grep '"hardware_validation_status":' | awk -F'"' '{print $4}')
echo "$HW_STATUS"

echo "=========================================================="
if [[ $FAILED -eq 0 ]]; then
    echo "[SUCCESS] Production Verification Checks Passed."
    exit 0
else
    echo "[FAIL] One or more verification checks failed."
    exit 1
fi
