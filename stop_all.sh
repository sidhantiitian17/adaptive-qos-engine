#!/bin/bash

# ==============================================================================
# Adaptive QoS Engine: Clean Shutdown Script
# ==============================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "================================================================="
echo "        STOPPING ADAPTIVE QOS ENGINE                             "
echo "================================================================="

STOPPED=0

if [ -f ".engine.pid" ]; then
    PID=$(cat .engine.pid 2>/dev/null || true)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "Stopping Unified Engine (PID $PID)..."
        kill "$PID" 2>/dev/null || true
        STOPPED=$((STOPPED + 1))
    fi
    rm -f .engine.pid
fi

if [ -f ".dashboard.pid" ]; then
    PID=$(cat .dashboard.pid 2>/dev/null || true)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "Stopping Dashboard (PID $PID)..."
        kill "$PID" 2>/dev/null || true
        STOPPED=$((STOPPED + 1))
    fi
    rm -f .dashboard.pid
fi

if [ -f ".controller.pid" ]; then
    PID=$(cat .controller.pid 2>/dev/null || true)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "Stopping Controller Daemon (PID $PID)..."
        kill "$PID" 2>/dev/null || true
        STOPPED=$((STOPPED + 1))
    fi
    rm -f .controller.pid
fi

# Clean up port 8080 or any remaining controller_daemon processes
pkill -f "controller_daemon.py" 2>/dev/null || true
fuser -k 8080/tcp 2>/dev/null || true

echo "All services stopped cleanly ($STOPPED process(es) terminated)."
echo "================================================================="
