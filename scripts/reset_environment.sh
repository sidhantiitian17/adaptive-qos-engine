#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [ -f "./venv/bin/python3" ]; then
    ./venv/bin/python3 scripts/reset_environment.py
else
    python3 scripts/reset_environment.py
fi
