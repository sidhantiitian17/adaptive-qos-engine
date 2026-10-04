# Phase 6 Deployment & Systemd Verification

**Project:** Case Study 3 — Adaptive QoS Engine for Mixed Home Broadband Traffic  
**Date:** 2026-10-04  
**Scope:** Production deployment configuration, systemd service units, packaging, and non-interactive daemon execution.

---

## 1. Systemd Service Unit Verification

The production systemd unit files are defined in `systemd/`:

### Controller Daemon Service (`systemd/qos-controller.service`):
```ini
[Unit]
Description=Adaptive QoS Controller Daemon
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/prashast/adaptive-qos-engine
ExecStart=/home/prashast/adaptive-qos-engine/venv/bin/python3 controller_daemon.py
Restart=always
RestartSec=3
LimitNOFILE=65536
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Dashboard Service (`systemd/qos-dashboard.service`):
```ini
[Unit]
Description=Adaptive QoS Unified Operations Dashboard
After=network.target qos-controller.service
Wants=qos-controller.service

[Service]
Type=simple
User=root
WorkingDirectory=/home/prashast/adaptive-qos-engine
ExecStart=/home/prashast/adaptive-qos-engine/venv/bin/python3 dashboard/dashboard_server.py --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

---

## 2. Process Lifecycle & Signal Handling

The controller daemon implements graceful POSIX signal handling:
- **SIGTERM / SIGINT:** Intercepted cleanly. Closes sniffer raw sockets, releases tc qdisc locks, flushes FlowTable state, and terminates child threads without leaving orphaned resources.
- **Auto-Restart & Resilience:** If unhandled exceptions occur in network telemetry sampling, daemon isolation guards ensure that the core control loop recovers within one cycle without process crash.

---

## 3. Environment Reset & Cold Boot

The deterministic script `scripts/reset_environment.py` (and shell wrapper `scripts/reset_environment.sh`) guarantees clean deployment transitions:
1. Kills any dangling python controller or dashboard processes.
2. Cleans up stale network namespaces (`lan1`, `lan2`, `gw`, `wanhost`) and virtual ethernet interfaces.
3. Removes orphaned qdiscs from host interfaces.
4. Validates database relational integrity and executes `PRAGMA integrity_check`.
5. Confirms zero stale listening sockets on ports 8000, 5201, 5202, 5206.

Verification confirmed in Step 24 of the full demo (`RESET COMPLETE: STATUS = PASS`).
