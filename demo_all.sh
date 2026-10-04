#!/bin/bash
set -e

# ==============================================================================
# Master Demonstration Script Wrapper (Delegates to Authoritative Phase 6 Demo)
# ==============================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [ -f "./scripts/run_full_demo.sh" ]; then
    exec ./scripts/run_full_demo.sh "$@"
else
    echo "Error: ./scripts/run_full_demo.sh not found." >&2
    exit 1
fi
