#!/bin/bash
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [ -f "./venv/bin/python3" ]; then
    ./venv/bin/python3 -c "from network.netns_manager import NetnsManager; m = NetnsManager(); print(m.verify())"
else
    python3 -c "from network.netns_manager import NetnsManager; m = NetnsManager(); print(m.verify())"
fi
