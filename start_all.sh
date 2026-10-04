#!/bin/bash
set -e

# ==============================================================================
# Adaptive QoS Engine: End-to-End System Startup Script
# Starts:
#   1. Network namespaces + CAKE qdisc + NetEm WAN emulator (if sudo available)
#   2. Unified 5-Zone Dashboard (FastAPI / Uvicorn on http://localhost:8080)
#   3. Autonomous Closed-Loop QoS Controller Daemon
# ==============================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

PYTHON="python3"
if [ -f "./venv/bin/python3" ]; then
    PYTHON="./venv/bin/python3"
fi

echo "================================================================="
echo "        STARTING ADAPTIVE QOS ENGINE END-TO-END                  "
echo "================================================================="

# 1. Stop any previous instances
echo -e "\n[1/4] Cleaning up any previous running instances..."
if [ -f ".engine.pid" ]; then
    PID=$(cat .engine.pid 2>/dev/null || true)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "Stopping previous unified engine (PID $PID)..."
        kill "$PID" 2>/dev/null || true
    fi
    rm -f .engine.pid
fi

if [ -f ".dashboard.pid" ]; then
    PID=$(cat .dashboard.pid 2>/dev/null || true)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "Stopping previous dashboard (PID $PID)..."
        kill "$PID" 2>/dev/null || true
    fi
    rm -f .dashboard.pid
fi

if [ -f ".controller.pid" ]; then
    PID=$(cat .controller.pid 2>/dev/null || true)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "Stopping previous controller daemon (PID $PID)..."
        kill "$PID" 2>/dev/null || true
    fi
    rm -f .controller.pid
fi

# Also free port 8080 if lingering
fuser -k 8080/tcp 2>/dev/null || true
sleep 1

# 2. Kernel Testbed Setup (if root/passwordless sudo available)
echo -e "\n[2/5] Checking Kernel Network Emulation Testbed..."
CAN_SUDO=false
if sudo -n true 2>/dev/null; then
    CAN_SUDO=true
fi

if [ "$CAN_SUDO" = true ]; then
    echo "  Passwordless sudo detected: Configuring kernel testbed..."
    if ! ip netns list 2>/dev/null | grep -q "gw"; then
        echo "  Setting up netns topology (gw, lan1, lan2, wanhost)..."
        cd testbed && sudo ./setup_topo.sh && cd "$PROJECT_DIR"
    else
        echo "  Netns topology already present."
    fi
    echo "  Applying CAKE qdisc (100mbit diffserv4)..."
    cd enforcement && ./apply_cake.sh 100mbit 2>/dev/null || true && cd "$PROJECT_DIR"
    echo "  Setting NetEm WAN link to 100mbit 20ms..."
    cd testbed && python3 wan_simulator.py 100 2>/dev/null || true && cd "$PROJECT_DIR"
else
    echo "  Notice: Non-root execution. Running engine and controller in safe emulation mode."
    echo "  (All policy decisions, ML classification, intent NLP, and rollback operate normally)"
fi

# 3. Start Unified Engine (FastAPI Control Plane + Embedded Autonomous Controller)
echo -e "\n[3/4] Starting Unified Adaptive QoS Engine (Authoritative Control Plane on :8080)..."
mkdir -p logs
nohup $PYTHON -u dashboard/unified_dashboard.py < /dev/null > logs/engine.log 2>&1 &
ENGINE_PID=$!
disown $ENGINE_PID 2>/dev/null || true
echo $ENGINE_PID > .engine.pid
echo "  Unified Engine started (PID $ENGINE_PID, log: logs/engine.log)"

# 4. Verification & Health Probes
echo -e "\n[4/4] Waiting for unified engine to become healthy and ready..."
MAX_RETRIES=20
READY=false
for i in $(seq 1 $MAX_RETRIES); do
    if curl -s http://127.0.0.1:8080/api/status >/dev/null 2>&1; then
        READY=true
        break
    fi
    sleep 0.5
done

if [ "$READY" = true ]; then
    echo "  ✅ Unified Engine service is UP and responding at http://localhost:8080"
    
    echo ""
    echo "================================================================="
    echo "   🚀 ADAPTIVE QOS ENGINE IS RUNNING SUCCESSFULLY!              "
    echo "================================================================="
    echo "  Authoritative Engine URL:  http://localhost:8080"
    echo "  API Documentation:         http://localhost:8080/docs"
    echo "  Engine PID:                $ENGINE_PID"
    echo ""
    echo "  Logs:                      tail -f logs/engine.log"
    echo ""
    echo "  To stop the application cleanly, run:"
    echo "    ./stop_all.sh"
    echo "================================================================="
else
    echo "  ❌ Failed to reach dashboard within timeout. Check logs/engine.log for errors."
    exit 1
fi
