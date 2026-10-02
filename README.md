# Adaptive QoS Engine for Mixed Home Broadband Traffic

An intent-aware QoS controller that classifies broad traffic categories without
reading private payloads, estimates link capacity, applies queueing/shaping
policies, and verifies whether the policy improved user experience.

## Prerequisites

- WSL2 (Ubuntu) with a **custom kernel build** enabling `sch_cake` and `sch_netem`
  modules (not included in stock WSL2 kernel). See `docs/kernel_build.md`.
- Python 3.12+
- System packages: `sudo apt install -y iproute2 iperf3 tcpdump python3-venv jq`

## Setup

```bash
git clone <repo-url>
cd adaptive-qos-engine
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Quick Start (One Command)

```bash
sudo ./start_all.sh
```

This creates the network namespace topology (gateway, 2 LAN hosts, 1 WAN host),
applies CAKE enforcement, and sets a NetEm-simulated WAN link (20 Mbps, 20ms delay).

## Architecture

See `docs/architecture.png`. Components:
- **Testbed** (`testbed/`): netns/veth topology + NetEm WAN simulation
- **Enforcement** (`enforcement/`): CAKE qdisc wrapper scripts
- **Estimator** (`estimator/`): SLoPS-inspired active-probing bandwidth estimator
- **Classifier** (`classifier/`): NetMatrix-style feature extraction + XGBoost
- **Policy Engine** (`policy_engine/`): rule-based decision engine + rollback manager
- **API** (`api/`): Laya-based natural-language intent parser + REST endpoints
- **Dashboard** (`dashboard/`): live metrics visualization

### AI Contribution Framing

> **Laya** (NLP intent parser) is used purely as a user-experience layer for
> capturing temporary user intent in natural language (e.g. *"I have a video
> call scheduled, make it the primary focus"* → `{action: "prioritize",
> traffic_class: "video_conference", duration_sec: 1200}`). It does not affect
> core QoS decisions — those are made by a fully deterministic, rule-based
> policy engine.
>
> The **measurable AI contribution** evaluated in this project is the
> **traffic classifier** (`classifier/`), which uses an XGBoost model trained
> on NetMatrix-style features (packet length, TTL, inter-arrival time) to
> classify flows without reading payloads. It achieves **99.1% accuracy** vs
> a deterministic heuristic baseline's 93.7% — a +5.4 percentage-point
> improvement that translates to correct DSCP marking and reduced
> interactive latency under competing traffic (see `experiments/`).


## Reproducing Key Results

### 1. Verify testbed connectivity
```bash
cd testbed && ./verify_connectivity.sh
```
Expected: 0% packet loss on all 4 tests (IPv4/IPv6, lan1/lan2 ↔ wanhost).

### 2. Verify CAKE enforcement
```bash
cd enforcement && ./apply_cake.sh 100mbit
sudo ip netns exec gw tc qdisc show dev veth-gw-wan
```
Expected: `qdisc cake ... bandwidth 100Mbit diffserv4 ...`

### 3. Verify link-capacity estimator accuracy
```bash
cd estimator
sudo ip netns exec lan1 python3 assert_within_tolerance.py 10.0.3.2 30 20
```
Expected: `PASS ✅` with error < 20%.

### 4. Verify classifier: AI vs deterministic baseline
```bash
cd classifier && python3 compare_classifiers.py
```
**Our result:** Heuristic baseline 93.7% accuracy vs XGBoost 99.1% accuracy
(+5.5 percentage points).

### 5. Verify automated rollback on bad policy
```bash
cd policy_engine
sudo python3 test_rollback_scenario.py
```
Expected: policy rolled back to last known-good bandwidth after failing health check.

### 6. Reproduce the headline baseline-vs-optimized result
```bash
cd experiments
./run_baseline.sh && ./run_optimized.sh && python3 generate_report.py
```
**Our result** (18 Mbps constrained link, competing bulk + interactive flow):

| Metric | Baseline (FIFO) | Optimized (CAKE) | Improvement |
|---|---|---|---|
| Avg Latency (ms) | 965.6 | 20.5 | **97.9% lower** |
| Jitter (ms) | 566.9 | 0.18 | **100% lower** |
| Bulk Throughput (Mbps) | 17.2 | 16.9 | comparable (fair test) |

## Known Limitations

See `docs/known_limitations.md`.

## Third-Party Licenses

See `THIRD_PARTY_LICENSES.md`.
