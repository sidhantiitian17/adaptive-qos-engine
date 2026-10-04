# Phase 7 — UI vs API Consistency Report

This report verifies the mathematical and semantic parity between the values rendered in the **Browser User Interface (DOM)** and the raw JSON data returned by the **REST API (`/api/*`)**.

| Telemetry / State Field | Browser UI Rendered Element | REST API Endpoint & Field | UI Value | API Raw JSON Value | Discrepancy | Verification Result |
|---|---|---|---|---|---|---|
| **System Health** | Header Status Badge (`#system-status`) | `GET /api/status` -> `system_status` | `HEALTHY / OPTIMAL` | `"HEALTHY / OPTIMAL"` | 0.0% | **CONSISTENT** |
| **WAN Capacity** | Header Capacity Badge (`#wan-capacity`) | `GET /api/status` -> `effective_capacity` | `100.0 Mbps` | `100.0` | 0.0% | **CONSISTENT** |
| **Active QoS Policy** | Header Policy Badge (`#active-policy`) | `GET /api/status` -> `active_policy` | `diffserv4` | `"diffserv4"` | 0.0% | **CONSISTENT** |
| **Daemon Uptime** | Header Uptime Badge (`#uptime-val`) | `GET /api/status` -> `uptime` | `00:03:15` | `"00:03:15"` | 0.0% | **CONSISTENT** |
| **Active Flow Count** | Overview Metric Card (`#card-flows`) | `GET /api/flows` -> `total` | `6 active flows` | `6` | 0.0% | **CONSISTENT** |
| **Round-Trip Latency** | Telemetry Strip Card (`#val-latency`) | `GET /api/metrics` -> `[last].latency_ms` | `20.0 ms` | `20.0` | 0.0% | **CONSISTENT** |
| **Jitter** | Telemetry Strip Card (`#val-jitter`) | `GET /api/metrics` -> `[last].jitter_ms` | `0.2 ms` | `0.2` | 0.0% | **CONSISTENT** |
| **Packet Loss** | Telemetry Strip Card (`#val-loss`) | `GET /api/metrics` -> `[last].loss_pct` | `0.00%` | `0.0` | 0.0% | **CONSISTENT** |
| **Aggregate Throughput** | Telemetry Strip Card (`#val-throughput`) | `GET /api/metrics` -> `[last].throughput_mbps` | `0.0 Mbps` | `0.0` | 0.0% | **CONSISTENT** |
| **CAKE Queue Depth** | Telemetry Strip Card (`#val-queue`) | `GET /api/metrics` -> `[last].queue_depth_pkts` | `0 pkts` | `0` | 0.0% | **CONSISTENT** |
| **Jain's Fairness Index**| Telemetry Strip Card (`#val-fairness`) | `GET /api/metrics` -> `[last].fairness_index` | `1.000` | `1.0` | 0.0% | **CONSISTENT** |
| **Active Intent Status** | Intent Banner / Status (`#intent-status`)| `GET /api/status` -> `active_intent` | `None (Nominal)` | `null` | 0.0% | **CONSISTENT** |
| **Overridden Flow Class**| FlowTable Row Badge (`.badge-override`) | `GET /api/flows` -> `flows[x].class` | `gaming` | `"gaming"` | 0.0% | **CONSISTENT** |
| **Audit Event Count** | Events Table Rows Count | `GET /api/events` -> `len(events)` | `28 rows` | `28` | 0.0% | **CONSISTENT** |

### Consistency Audit Summary
- **Total Fields Audited**: 14
- **Consistent**: 14 (100.0%)
- **Discrepancies**: 0 (0.0%)
- **Zero Mock Transforms**: Confirmed. All UI rendering templates parse API JSON properties directly without hardcoded overrides or client-side fabrication.
