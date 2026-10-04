#!/usr/bin/env bash
# Production Uninstallation & Rollback Script
set -euo pipefail

echo "=========================================================="
echo "Uninstalling Adaptive QoS Engine & Reverting Qdiscs"
echo "=========================================================="

if [[ $EUID -ne 0 ]]; then
   echo "[!] Error: This script must be run as root (or with sudo)."
   exit 1
fi

CONF_DIR="/etc/adaptive-qos"
VAR_DIR="/var/lib/adaptive-qos"
INSTALL_DIR="/opt/adaptive-qos-engine"

# 1. Stop and disable systemd service
if systemctl is-active --quiet adaptive-qos 2>/dev/null; then
    echo "[+] Stopping adaptive-qos service..."
    systemctl stop adaptive-qos || true
fi
if systemctl is-enabled --quiet adaptive-qos 2>/dev/null; then
    echo "[+] Disabling adaptive-qos service..."
    systemctl disable adaptive-qos || true
fi

if [[ -f /etc/systemd/system/adaptive-qos.service ]]; then
    rm -f /etc/systemd/system/adaptive-qos.service
    systemctl daemon-reload || true
fi

# 2. Revert WAN Qdisc to default
if [[ -f "$CONF_DIR/config.json" ]]; then
    WAN_IFACE=$(python3 -c "import json; print(json.load(open('$CONF_DIR/config.json')).get('wan_interface', ''))" 2>/dev/null || echo "")
    if [[ -n "$WAN_IFACE" ]]; then
        echo "[+] Reverting qdisc on $WAN_IFACE..."
        tc qdisc del dev "$WAN_IFACE" root 2>/dev/null || true
    fi
fi

# 3. Clean installation files
echo "[+] Removing installation files..."
rm -rf "$INSTALL_DIR" "$CONF_DIR"

echo "=========================================================="
echo "[SUCCESS] Uninstallation Complete."
echo "Qdiscs reverted to kernel defaults. Preserved data in $VAR_DIR."
echo "=========================================================="
