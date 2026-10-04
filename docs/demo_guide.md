# Adaptive QoS Engine: User & Demonstration Guide

## 1. Running the Complete 24-Step Verification Demo

The engine includes an end-to-end demonstration script that executes all 24 authoritative validation steps:

```bash
./scripts/run_full_demo.sh
```

### What the Demo Validates:
1. **Multi-Node Virtual Network:** Spins up 4 Linux namespaces (`lan1`, `lan2`, `gw`, `wanhost`) with dual virtual Ethernet links and routed forwarding.
2. **Autonomous Controller Daemon:** Boots the QoS daemon on router `gw` and begins closed-loop bandwidth observation.
3. **ML Classification:** Injects realistic traffic across 7 traffic profiles and verifies zero-payload classification inference.
4. **CAKE Traffic Control:** Installs root CAKE qdisc on the router's WAN egress and marks packets into DiffServ tins.
5. **Scenario A (Bufferbloat Elimination):** Contrasts an unshaped bufferbloated link with adaptive CAKE shaping (>99% latency reduction).
6. **Scenario B (Dynamic Link Collapse):** Injects a sudden WAN drop (100 Mbps -> 20 Mbps) and verifies closed-loop adaptation in < 50ms.
7. **Scenario C (Multi-Stream Fairness):** Evaluates 3 competing TV bulk streams alongside interactive gaming, verifying Jain's index > 0.999.
8. **Intent Lifecycle:** Demonstrates operator priority requests and atomic rollbacks.

---

## 2. Launching the Unified Operations Dashboard

```bash
# Start unified dashboard server on port 8000
./venv/bin/python3 dashboard/dashboard_server.py --host 0.0.0.0 --port 8000
```

Open your browser at `http://localhost:8000`:
- **Overview:** View live link utilization, current shaping rate, and system status.
- **Traffic:** Inspect active flows and real-time ML classification confidence.
- **Policies:** View DiffServ mappings and anti-starvation progress guarantees.
- **Intent:** Submit natural language priority requests or select quick presets.
- **Experiments:** Review historical test records and telemetry graphs.
