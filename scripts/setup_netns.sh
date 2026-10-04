#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [ -f "./venv/bin/python3" ]; then
    ./venv/bin/python3 -c "from network.netns_manager import NetnsManager; m = NetnsManager(); res = m.setup(); print(res); exit(0 if res.get('status') == 'success' else 1)"
else
    python3 -c "from network.netns_manager import NetnsManager; m = NetnsManager(); res = m.setup(); print(res); exit(0 if res.get('status') == 'success' else 1)"
fi
