#!/usr/bin/env bash
# ==============================================================================
# Phase 7 — Real User UI / Dashboard End-to-End Acceptance Test Runner
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

echo "========================================================================"
echo " Starting Phase 7 Real User UI Acceptance Test Suite"
echo "========================================================================"

if [ -f "./venv/bin/python3" ]; then
    PYTHON="./venv/bin/python3"
else
    PYTHON="python3"
fi

${PYTHON} "${REPO_ROOT}/scripts/run_ui_acceptance_test.py" "$@"

echo "========================================================================"
echo " Phase 7 Real User UI Acceptance Test Suite Complete"
echo "========================================================================"
