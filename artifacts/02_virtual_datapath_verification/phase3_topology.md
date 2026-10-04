# Phase 3 Multi-Node Residential Topology Specification

This document details the multi-node network architecture, interface configurations, IP routing tables, and traffic flows validated during Phase 3 Hardware & Multi-Node Testing.

---

## 1. Network Topology Diagram

```
                 =======================================================
                                 LAN SUBNET 1 (10.0.1.0/24)
                 =======================================================
                 [ Client 1: lan1 ] (PC / Gaming / Bulk Downloader)
                   IP:  10.0.1.2/24 | fd00:1::2/64
                   MAC: e6:12:34:56:01:02
                   Dev: veth-lan1
                           │
                           │ (veth pair link)
                           ▼
                   Dev: veth-lan1-gw
                   IP:  10.0.1.1/24 | fd00:1::1/64
                 ┌─────────────────────────────────────────────────────┐
                 │                QoS ROUTER (gw)                      │
                 │                                                     │
                 │  - Linux Kernel L3 Routing (IPv4 & IPv6 Forwarding) │
                 │  - DSCP Classification & DiffServ Marker            │
                 │  - Telemetry Poller & Closed-Loop Controller        │
                 │  - CAKE DiffServ4 Smart Queue Management Scheduler  │
                 │    Attached to Egress: veth-gw-wan                  │
                 │    Tins: Bulk | Best Effort | Video | Voice         │
                 │                                                     │
                 │  Interfaces:                                        │
                 │    veth-lan1-gw: 10.0.1.1/24 | fd00:1::1/64 (LAN 1) │
                 │    veth-lan2-gw: 10.0.2.1/24 | fd00:2::1/64 (LAN 2) │
                 │    veth-gw-wan:  10.0.3.1/24 | fd00:3::1/64 (WAN)   │
                 └─────────────────────────────────────────────────────┘
                           ▲                               │
                           │ (veth pair link)              │ (veth pair link)
                           │                               │
                 ========================                  ▼
                  LAN SUBNET 2 (10.0.2.0)         Dev: veth-wan-gw
                 ========================         IP:  10.0.3.2/24 | fd00:3::2/64
                 [ Client 2: lan2 ]               ┌─────────────────────────────────┐
                   (Living Room / 4K Smart TVs)   │     WAN EMULATOR (wanhost)      │
                   IP:  10.0.2.2/24               │                                 │
                   Dev: veth-lan2                 │  - Internet Video/Game Servers  │
                   MAC: e6:12:34:56:02:02         │  - NetEm Impairment Emulator:   │
                                                  │    Delay: 15ms +/- 2ms normal   │
                                                  │    Loss:  0.1% random           │
                                                  └─────────────────────────────────┘
```

---

## 2. Interface IP Allocation & Subnet Mapping

| Node Name | Namespace | Interface | IPv4 CIDR | IPv6 CIDR | Gateway (Default Route) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Client 1** | `lan1` | `veth-lan1` | `10.0.1.2/24` | `fd00:1::2/64` | `10.0.1.1` / `fd00:1::1` |
| **Client 2** | `lan2` | `veth-lan2` | `10.0.2.2/24` | `fd00:2::2/64` | `10.0.2.1` / `fd00:2::1` |
| **Router LAN 1**| `gw` | `veth-lan1-gw`| `10.0.1.1/24` | `fd00:1::1/64` | N/A (Directly connected) |
| **Router LAN 2**| `gw` | `veth-lan2-gw`| `10.0.2.1/24` | `fd00:2::1/64` | N/A (Directly connected) |
| **Router WAN** | `gw` | `veth-gw-wan` | `10.0.3.1/24` | `fd00:3::1/64` | `10.0.3.2` / `fd00:3::2` |
| **WAN Server** | `wanhost` | `veth-wan-gw` | `10.0.3.2/24` | `fd00:3::2/64` | `10.0.3.1` / `fd00:3::1` |

---

## 3. Kernel Routing Tables

### Router Node (`gw`) Routing Table
```
# IPv4 Routing
10.0.1.0/24 dev veth-lan1-gw proto kernel scope link src 10.0.1.1 
10.0.2.0/24 dev veth-lan2-gw proto kernel scope link src 10.0.2.1 
10.0.3.0/24 dev veth-gw-wan proto kernel scope link src 10.0.3.1 
default via 10.0.3.2 dev veth-gw-wan

# IPv6 Routing
fd00:1::/64 dev veth-lan1-gw proto kernel metric 256 pref medium
fd00:2::/64 dev veth-lan2-gw proto kernel metric 256 pref medium
fd00:3::/64 dev veth-gw-wan proto kernel metric 256 pref medium
default via fd00:3::2 dev veth-gw-wan metric 1024 pref medium
```

### Client 1 (`lan1`) Routing Table
```
10.0.1.0/24 dev veth-lan1 proto kernel scope link src 10.0.1.2 
default via 10.0.1.1 dev veth-lan1

fd00:1::/64 dev veth-lan1 proto kernel metric 256 pref medium
default via fd00:1::1 dev veth-lan1 metric 1024 pref medium
```

### WAN Server (`wanhost`) Routing Table
```
10.0.1.0/24 via 10.0.3.1 dev veth-wan-gw 
10.0.2.0/24 via 10.0.3.1 dev veth-wan-gw 
10.0.3.0/24 dev veth-wan-gw proto kernel scope link src 10.0.3.2 
default via 10.0.3.1 dev veth-wan-gw

fd00:1::/64 via fd00:3::1 dev veth-wan-gw metric 1024 pref medium
fd00:2::/64 via fd00:3::1 dev veth-wan-gw metric 1024 pref medium
fd00:3::/64 dev veth-wan-gw proto kernel metric 256 pref medium
default via fd00:3::1 dev veth-wan-gw metric 1024 pref medium
```

---

## 4. Hardware Forwarding & Routing Proof

Empirical verification confirms packets are forwarded through the router rather than processed on local loopback:

1. **IPv4 Forwarding Proof (`TTL=63`)**:
   Ping transmitted from Client 1 (`10.0.1.2`) with default TTL 64 arrived at WAN Host (`10.0.3.2`) with `ttl=63`. The Linux kernel routing subsystem on `gw` decremented the TTL field as required by RFC 1812:
   ```
   64 bytes from 10.0.3.2: icmp_seq=1 ttl=63 time=0.303 ms
   ```

2. **IPv6 Forwarding Proof (`Hop Limit=63`)**:
   Ping6 transmitted from Client 1 (`fd00:1::2`) with default Hop Limit 64 arrived at WAN Host (`fd00:3::2`) with `ttl=63` (Hop Limit=63):
   ```
   64 bytes from fd00:3::2: icmp_seq=1 ttl=63 time=0.275 ms
   ```

3. **CAKE DiffServ4 Forwarding Ingestion**:
   As packets pass through `gw` toward `wanhost`, they egress through `veth-gw-wan` where CAKE DiffServ4 is attached. Inspection of kernel qdisc statistics confirms live packet classification into tins based on DSCP:
   - Voice (`EF` / `0xb8`): 25 packets (5,275 bytes)
   - Video (`AF41` / `0x88`): 35 packets (12,285 bytes)
   - Bulk (`CS1` / `0x20`): 60 packets (75,060 bytes)
   - Best Effort (`CS0` / `0x00`): 20 packets (11,020 bytes)
   - **Total Forwarded**: 140 packets (103,640 bytes) with 0 drops.
