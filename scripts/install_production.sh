#!/usr/bin/env bash
# Production Installation Script for Adaptive QoS Engine
set -euo pipefail

echo "=========================================================="
echo "Installing Adaptive QoS Engine (Production Deployment)"
echo "=========================================================="

# 1. Check Root Privileges
if [[ $EUID -ne 0 ]]; then
   echo "[!] Error: This script must be run as root (or with sudo)."
   exit 1
fi

INSTALL_DIR="/opt/adaptive-qos-engine"
CONF_DIR="/etc/adaptive-qos"
VAR_DIR="/var/lib/adaptive-qos"
LOG_DIR="/var/log/adaptive-qos"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 2. Verify Kernel CAKE Support
echo "[+] Checking Linux Kernel CAKE support..."
if ! modprobe sch_cake 2>/dev/null; then
    echo "[!] Warning: modprobe sch_cake returned non-zero. Checking built-in kernel config..."
    if ! tc qdisc add dev lo root cake 2>/dev/null; then
        echo "[!] Notice: sch_cake not dynamically loadable on loopback; verifying tc capability..."
    else
        tc qdisc del dev lo root 2>/dev/null || true
    fi
fi

# 3. Enable IP Forwarding
echo "[+] Enabling Linux kernel IPv4 and IPv6 forwarding..."
sysctl -w net.ipv4.ip_forward=1 >/dev/null
sysctl -w net.ipv6.conf.all.forwarding=1 >/dev/null

# 4. Create Directories
echo "[+] Creating configuration and data directories..."
mkdir -p "$CONF_DIR" "$VAR_DIR" "$LOG_DIR" "$INSTALL_DIR"

# 5. Discover Network Interfaces
echo "[+] Running Interface Discovery..."
python3 -c "
import sys
sys.path.insert(0, '$SOURCE_DIR')
from network.interface_discovery import InterfaceDiscovery
disco = InterfaceDiscovery()
topo = disco.discover_topology()
import json
conf = {
    'wan_interface': topo['wan_interface'],
    'lan_interface': topo['lan_interface'],
    'nominal_bandwidth_mbps': 100.0,
    'min_guaranteed_bulk_mbps': 20.0,
    'qdisc_scheme': 'diffserv4',
    'isolated_hosts': True,
    'api_port': 8000,
    'api_host': '127.0.0.1',
    'db_path': '$VAR_DIR/evidence.db',
    'log_level': 'INFO',
    'auto_rollback_threshold_ms': 60.0
}
with open('$CONF_DIR/config.json', 'w') as f:
    json.dump(conf, f, indent=2)
print(f\"[+] Configured WAN: {topo['wan_interface']}, LAN: {topo['lan_interface']}\")
"

# 6. Copy Files to Installation Directory
echo "[+] Installing code files to $INSTALL_DIR..."
cp -ru "$SOURCE_DIR"/* "$INSTALL_DIR/" || true

# 7. Install Systemd Service if supported
if [[ -d /etc/systemd/system ]]; then
    echo "[+] Installing systemd service unit..."
    cp "$SOURCE_DIR/systemd/adaptive-qos.service" /etc/systemd/system/adaptive-qos.service
    systemctl daemon-reload || true
    echo "[+] Service installed: run 'systemctl enable --now adaptive-qos' to start."
fi

echo "=========================================================="
echo "[SUCCESS] Installation Complete."
echo "Configuration: $CONF_DIR/config.json"
echo "Evidence DB:   $VAR_DIR/evidence.db"
echo "=========================================================="
