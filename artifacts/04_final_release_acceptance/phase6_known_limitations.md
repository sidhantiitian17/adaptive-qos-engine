# Phase 6 Known Limitations & Operational Constraints

**Project:** Case Study 3 — Adaptive QoS Engine for Mixed Home Broadband Traffic  
**Phase:** 6 — Final Software Release  
**Status Date:** 2026-10-04  
**Verdict Impact:** Governs the classification as `PRODUCTION READY WITH ENVIRONMENT LIMITATIONS`.

---

## 1. Physical Hardware & ASIC Validation Boundary (Criterion 37)

### Limitation Description:
The current acceptance and validation environment is hosted on an x86_64 Linux machine executing under Microsoft WSL2 (`6.6.x-microsoft-standard-WSL2` kernel).
- The network topology is constructed using Linux kernel network namespaces (`ip netns`) and virtual Ethernet pairs (`veth`).
- The primary host network interface is a virtualized Hyper-V adapter (`hv_netvsc`), not a discrete physical PCIe Network Interface Card (NIC) with hardware ASIC queues or optical PHY transceivers.

### Impact on Product Readiness:
- **Software, Control Plane & Kernel Datapath:** 100% verified. Real Linux kernel traffic control (`sch_cake`), netfilter/iptables DSCP mangling, TCP/UDP sockets, routing table lookups, and ML inference run without modification.
- **Physical Hardware Offload:** Hardware offloaded QoS (e.g., IEEE 802.1p VLAN tagging on physical switches, NIC hardware DiffServ queues, hardware-assisted timestamping) cannot be physically validated in this virtualized environment.
- **Classification:** **`ENVIRONMENT-LIMITED`**. This limitation is environmental and does not compromise software correctness.

---

## 2. Multi-Node IPv6 Forwarding Scope

- **Verified:** Dual-stack IPv6 routing across network namespaces (`fd00:1::/64`, `fd00:2::/64`, `fd00:3::/64`) and local loopback (`::1`) demonstrates Hop Limit decrement (`64 -> 63`) and DSCP preservation.
- **Limitation:** In non-virtual deployments with ISP prefix delegation (DHCPv6-PD), dynamic IPv6 prefix changes must be coordinated with the router's upstream gateway.

---

## 3. High-Speed Multi-Gigabit Links (> 2.5 Gbps)

- The software implementation in Python (control plane) and Linux kernel CAKE (datapath) easily manages typical residential broadband bandwidths from 10 Mbps to 1 Gbps.
- On multi-gigabit connections (> 2.5 Gbps to 10 Gbps), CPU utilization for single-threaded packet inspection can become a bottleneck. Production deployments at those speeds should leverage eBPF/XDP for zero-copy metadata extraction and hardware-assisted CAKE offload.
