#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "========================================================================="
echo "   ADAPTIVE QOS ENGINE: AUTHORITATIVE PHASE 6 FULL DEMONSTRATION         "
echo "========================================================================="

if [ -f "./venv/bin/python3" ]; then
    ./venv/bin/python3 scripts/run_full_demo.py "$@"
else
    python3 scripts/run_full_demo.py "$@"
fi
