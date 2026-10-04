# Phase 7 — Real User Journey Report

This report documents the step-by-step verification of **11 primary real-user journeys** executed across the Adaptive QoS Engine Unified Web Dashboard. Each journey represents a realistic operational task performed by a household administrator or network engineer.

---

### Journey 1: First-Time Landing & Initial Orientation
- **User Goal**: Access the router dashboard, verify that the QoS engine is active, and assess current home broadband link quality.
- **Actions**:
  1. Open web browser to `http://127.0.0.1:8080/`.
  2. Inspect the top header badges and breadcrumbs.
  3. Review the 6 telemetry metric cards on the Overview screen.
- **Observed Behavior**:
  - Dashboard DOM loads cleanly in under 20 ms.
  - Header displays `HEALTHY / OPTIMAL` status in emerald green, `100 Mbps Nominal` WAN capacity, and `diffserv4` active policy.
  - Telemetry cards display live RTT (`20.0 ms`), Jitter (`0.2 ms`), Packet Loss (`0.00%`), and Queue Depth (`0 pkts`).
- **Verdict**: **VERIFIED**

---

### Journey 2: Observing Real-Time Traffic & Active Stream Classification
- **User Goal**: Identify which household devices are consuming bandwidth and verify that zero-payload classification is accurately categorizing their applications.
- **Actions**:
  1. Click the `Traffic` navigation tab in the sidebar.
  2. Inspect the live FlowTable.
  3. Verify device mapping (`Work Laptop`, `Gaming PC`, `NAS / Downloads`).
- **Observed Behavior**:
  - FlowTable displays 6 active sessions with full IP:port 5-tuples.
  - Work Laptop traffic is categorized as `video_conference` (confidence 0.95, DSCP AF41).
  - Gaming PC traffic is categorized as `gaming` (confidence 0.98, DSCP CS4).
  - NAS traffic is categorized as `bulk_download` (confidence 0.92, DSCP CS1).
  - All classifications were derived purely from packet size, TTL, and inter-arrival intervals without inspecting packet payloads.
- **Verdict**: **VERIFIED**

---

### Journey 3: Understanding Automated Decisions ("Why Did AQE Do This?")
- **User Goal**: Understand why the router is shaping traffic and verify that algorithmic decisions are transparent rather than a "black box."
- **Actions**:
  1. Navigate to the `Overview` tab.
  2. Read the "Why Did AQE Do This?" explanation widget.
  3. Inspect the decision trace table.
- **Observed Behavior**:
  - Widget explains: *"AQE is shaping the link to 95 Mbps and reserving a minimum 19 Mbps policy floor for bulk traffic (20% of the shaped rate)."*
  - Decision trace details the exact inputs: Link Capacity = 100 Mbps, Effective Shaping Target = 95 Mbps (5% link-safety buffer), Active bulk flows detected = 1.
  - Mathematical justification is clearly laid out for the user.
- **Verdict**: **VERIFIED**

---

### Journey 4: Setting a Temporary Service Intent (NLP & Presets)
- **User Goal**: Temporarily elevate priority for an urgent Zoom video meeting without permanently reconfiguring router settings.
- **Actions**:
  1. Click the `Intent` navigation tab.
  2. Enter the prompt: *"I have an important client video call scheduled"* and set duration to 30 minutes.
  3. Alternatively, click the `Preset: Video (15m)` button.
- **Observed Behavior**:
  - Submitting sends `POST /api/intent`.
  - The Laya NLP engine parses the intent into `video_conference` priority with duration 1800 seconds.
  - Status immediately changes to `PRIORITY_ACTIVE` with a dynamic countdown timer in the header.
  - CAKE tin configuration dynamically locks higher weight to the Voice/Video tin.
  - Clicking `Cancel Active Intent` restores nominal operation within 1 cycle.
- **Verdict**: **VERIFIED**

---

### Journey 5: Experiencing and Observing a Sudden WAN Drop
- **User Goal**: Verify that when the ISP connection suddenly degrades (e.g. cable link flap or peak-hour throttling), the engine prevents latency spikes and avoids bufferbloat.
- **Actions**:
  1. Click `⚡ Simulate WAN Drop (100→20)` on the Overview toolbar.
  2. Observe telemetry strip and shaping behavior.
  3. Click `↻ Restore Nominal 100M` after 10 seconds.
- **Observed Behavior**:
  - Capacity transitions from 100 Mbps to 20 Mbps.
  - Controller adapts in **43.1 ms**, reducing shaping rate to 19 Mbps and reserving a minimum 4 Mbps policy floor for bulk traffic (20% of 19 Mbps shaping rate; actual measured bulk throughput: ~3.8 Mbps).
  - Interactive gaming latency remains protected below 20 ms, while bulk streams absorb the reduction.
  - Restoring nominal restores 95 Mbps shaping in **37.9 ms**.
- **Verdict**: **VERIFIED**

---

### Journey 6: Manually Overriding an Incorrect Flow Classification
- **User Goal**: Manually reclassify a traffic stream if an unusual application is misclassified.
- **Actions**:
  1. Open the `Traffic` view.
  2. Click the `Override` button on a specific flow row.
  3. Select `gaming` from the dropdown and submit the modal.
- **Observed Behavior**:
  - Modal issues `POST /api/override` with flow identifier.
  - FlowTable marks `overridden: True`, locks class to `gaming`, and assigns DSCP `CS4`.
  - Row immediately displays a highlighted `Manual Override` badge.
- **Verdict**: **VERIFIED**

---

### Journey 7: Inspecting Historical Experiments & Baseline Comparisons
- **User Goal**: Verify the quantitative improvement of Adaptive QoS compared to an unmanaged standard router.
- **Actions**:
  1. Click the `Experiments` tab.
  2. Review the Scenario 1 comparison card and Scenario 2 replay timeline.
- **Observed Behavior**:
  - Dashboard illustrates: Unmanaged FIFO baseline p95 latency = **171.4 ms** vs Adaptive CAKE p95 latency = **1.0 ms** (99.4% latency reduction).
  - Clicking `Play Replay` animates the real-time bufferbloat mitigation curve during sudden congestion.
- **Verdict**: **VERIFIED**

---

### Journey 8: Investigating System Events & Audit Logs
- **User Goal**: Inspect operational logs to verify system health and identify any policy warnings.
- **Actions**:
  1. Click the `Events` tab.
  2. Cycle through filter buttons: `All`, `Action`, `Warning`, `Critical`.
- **Observed Behavior**:
  - Event log displays chronological, timestamped entries with severity color coding.
  - Filtering by `Action` displays policy shifts and intent triggers.
  - Filtering by `Warning` displays bandwidth degradation alerts.
- **Verdict**: **VERIFIED**

---

### Journey 9: Injecting a Policy Failure & Watching Self-Healing Rollback
- **User Goal**: Verify that if a corrupted policy or runaway script attempts to set an invalid rate, the engine automatically rolls back without dropping connectivity.
- **Actions**:
  1. Click `💀 Inject Bad Policy (Test Rollback)` on the Overview toolbar.
  2. Inspect controller console, status badge, and Events view.
- **Observed Behavior**:
  - Injected bad rate (1000 Mbps) violates bandwidth bounds.
  - Anomaly detector flags the violation immediately.
  - `RollbackManager` restores previous stable policy (`diffserv4` @ 95 Mbps) in under 1 second.
  - Event log records a `CRITICAL: Anomaly detected, auto-rollback executed` record.
- **Verdict**: **VERIFIED**

---

### Journey 10: Exporting Reports & Downloading Evidence
- **User Goal**: Export comprehensive verification reports for auditing or technical support.
- **Actions**:
  1. Click `Export Report` in the top header or visit the `Reports` view.
  2. Click `Download Report .md` and `Open Fullpage HTML`.
- **Observed Behavior**:
  - `GET /api/report/markdown` serves the full Phase 6/7 production acceptance report.
  - `GET /api/report/html` renders a standalone, printable HTML document.
  - "Copy Markdown" copies raw report text directly to user clipboard with a success toast.
- **Verdict**: **VERIFIED**

---

### Journey 11: Checking System Health, Resource Consumption, & Settings
- **User Goal**: Verify that the QoS engine runs efficiently on modest consumer router hardware.
- **Actions**:
  1. Click the `Settings` tab.
  2. Inspect system telemetry: CPU usage, memory RSS, network interfaces, and database status.
- **Observed Behavior**:
  - System info reports: Linux kernel `6.18.40.1`, Python `3.12.3`.
  - Process RSS footprint is steady at **162.5 MB**; CPU consumption is **< 1.5%**.
  - Database status shows `experiments/evidence.db` active with 5 synchronized relational tables.
- **Verdict**: **VERIFIED**

---

### Overall Journey Verdict
All 11 user journeys executed successfully end-to-end through the dashboard UI.
**Verdict**: **END-TO-END USER ACCEPTED WITH ENVIRONMENT LIMITATIONS**
