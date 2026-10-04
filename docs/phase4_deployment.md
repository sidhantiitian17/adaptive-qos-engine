# Production Deployment Guide: Adaptive QoS Engine

**Version:** 4.0  
**Target Environment:** Linux Gateway / Router (Debian, Ubuntu 22.04/24.04, OpenWrt x86_64)  
**Supported Topology:** Home LAN $\leftrightarrow$ Linux Router / QoS Host $\leftrightarrow$ ISP WAN  

---

## 1. Production Topology & Datapath Architecture

In a production environment, the Adaptive QoS Engine operates directly on the Linux router or gateway machine that routes traffic between the home local area network (LAN) and the broadband internet service provider (ISP) modem:

```
+-------------------+          +------------------------------+          +-------------------+
|     HOME LAN      |          |      LINUX QoS ROUTER        |          |     ISP / WAN     |
|                   |          |                              |          |                   |
|  LAN Devices      |  Ethernet|  [LAN Interface: eth1]       |  Ethernet|  Broadband Modem  |
|  (PCs, TVs,       | -------->|  - Kernel L3 IP Forwarding   | -------->|  (Cable, Fiber,   |
|   Consoles, IoT)  |          |  - Zero-Payload Classifier   |          |   5G Home)        |
|                   |          |  - DSCP Egress Marker        |          |                   |
|                   |          |  [WAN Interface: eth0]       |          |                   |
|                   |          |  - CAKE DiffServ4 Qdisc      |          |                   |
+-------------------+          +------------------------------+          +-------------------+
```

### Critical Datapath Placement Rules
1. **WAN Egress Interface:** CAKE MUST be attached to the egress of the WAN interface (`eth0`, `veth-gw-wan`, or PPPoE interface `ppp0`). CAKE actively manages the upstream bottleneck buffer and throttles traffic before it buffers inside the unmanaged ISP modem.
2. **DiffServ4 Tins:**
   - **Voice (CS6, CS7, EF `0xb8`):** Real-time interactive voice (VoIP) and latency-critical gaming probes.
   - **Video (CS4, CS5, AF41 `0x88`):** Video conferencing (Zoom, Teams, WebRTC) and interactive video.
   - **Best Effort (CS0 `0x00`, AF1x, AF2x, AF3x):** Standard HTTP/HTTPS web browsing, streaming media.
   - **Background (CS1 `0x20`):** Bulk file downloads, torrents, cloud backups.
3. **No Loopback:** The engine strictly refuses to bind or apply shaping to `lo` or `localhost`.

---

## 2. Installation & Requirements

### System Requirements
- Linux Kernel $\ge 5.4$ with `sch_cake`, `act_mirred`, and `cls_u32` / `cls_matchall` support.
- `iproute2` with `tc` installed.
- Python $\ge 3.10$.
- Linux Capabilities: `CAP_NET_ADMIN` and `CAP_NET_RAW` (for qdisc modification and raw packet sniffing).

### Automated Production Installation
Run the automated installation script:

```bash
sudo ./scripts/install_production.sh
```

This script:
1. Verifies kernel version and module availability (`sch_cake`).
2. Configures kernel forwarding via sysctl (`net.ipv4.ip_forward=1`, `net.ipv6.conf.all.forwarding=1`).
3. Auto-discovers or binds the configured LAN and WAN network interfaces.
4. Creates the runtime configuration `/etc/adaptive-qos/config.json`.
5. Installs and enables the systemd service `/etc/systemd/system/adaptive-qos.service`.

---

## 3. Configuration Management

Configuration file location: `/etc/adaptive-qos/config.json`

```json
{
  "wan_interface": "eth0",
  "lan_interface": "eth1",
  "nominal_bandwidth_mbps": 100.0,
  "min_guaranteed_bulk_mbps": 20.0,
  "qdisc_scheme": "diffserv4",
  "isolated_hosts": true,
  "api_port": 8000,
  "api_host": "127.0.0.1",
  "db_path": "/var/lib/adaptive-qos/evidence.db",
  "log_level": "INFO",
  "auto_rollback_threshold_ms": 60.0
}
```

---

## 4. Operational Lifecycle (Systemd Integration)

### Start Service
```bash
sudo systemctl start adaptive-qos
```

### Check Service Status
```bash
sudo systemctl status adaptive-qos
```

### Stop Service Cleanly
```bash
sudo systemctl stop adaptive-qos
```
*Note:* On shutdown, the engine's safe shutdown handler flushes in-memory metrics, releases sniffing threads, and cleanly reverts the WAN interface to the permanent known-good policy or clean default qdisc.

---

## 5. Verification & Health Monitoring

To verify deployment correctness at any time:

```bash
sudo ./scripts/verify_production.sh
```

Or query the REST API:
- Health check: `curl -s http://127.0.0.1:8000/health`
- Network status: `curl -s http://127.0.0.1:8000/api/network/status`
- Active flows: `curl -s http://127.0.0.1:8000/api/flows`
- Controller status: `curl -s http://127.0.0.1:8000/api/controller/status`

---

## 6. Uninstallation & Rollback
To completely remove the service and restore standard networking:

```bash
sudo ./scripts/uninstall_production.sh
```
