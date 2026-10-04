#!/bin/bash
set -e

# ==============================================================================
# Environment Reset Wrapper (Delegates to Authoritative Reset Script)
# ==============================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [ -f "./scripts/reset_environment.sh" ]; then
    exec ./scripts/reset_environment.sh "$@"
else
    echo "Error: ./scripts/reset_environment.sh not found." >&2
    exit 1
fi
