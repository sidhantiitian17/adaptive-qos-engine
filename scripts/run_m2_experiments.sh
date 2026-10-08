#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

PYTHON="python3"
if [ -f "./venv/bin/python3" ]; then
    PYTHON="./venv/bin/python3"
fi

echo "================================================================="
echo "   RUNNING MODULE M2 (LINK CAPACITY ESTIMATOR) EVALUATION SUITE  "
echo "================================================================="

sudo $PYTHON experiments/run_m2_evaluation.py

echo ""
echo "================================================================="
echo "   M2 EVALUATION COMPLETE — EVIDENCE SAVED TO results/m2/        "
echo "================================================================="
