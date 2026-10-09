# Known Limitations

## 1. Emulated environment, not production hardware
This prototype runs entirely in Linux network namespaces (netns + veth) inside
WSL2, not on physical routers or real ISP links. NetEm is used to emulate WAN
link conditions (rate, delay, loss). This is explicitly labeled per the project
requirement: "if a hardware capability is emulated, the report must label it as
emulation."

## 2. Custom kernel required for CAKE and NetEm
The stock WSL2 kernel ships without the `sch_cake` and `sch_netem` qdisc modules.
We built a custom WSL2 kernel (based on microsoft/WSL2-Linux-Kernel) with these
modules enabled. See `docs/kernel_build.md` for exact steps. On a standard Linux
distribution (e.g. Ubuntu Server/Desktop), both modules are typically available
out of the box.

## 3. Linux `tc` qdiscs shape egress traffic only
A significant debugging finding during development: `tc` qdiscs only shape
**outgoing (egress)** traffic on the interface they are attached to. Several of
our tests initially produced misleading "no difference" results because
competing traffic was routed in the wrong direction relative to the shaped
interface (e.g., using `iperf3 -R` sent traffic through an un-shaped egress
path). Our final experiment scripts (`experiments/run_baseline.sh`,
`run_optimized.sh`) correctly route all competing flows through the gateway's
shaped egress interface.

## 4. `tbf` qdisc module unavailable; NetEm used as the "dumb" baseline instead
Our baseline comparison originally intended to use `tbf` (Token Bucket Filter)
as a rate-limited, non-fair baseline queue. This module was also missing from
our custom kernel build. We substituted a single-queue `netem` configuration
(rate-limited, no per-flow fairness) as a functionally equivalent "dumb FIFO"
baseline, since NetEm was already confirmed available.

## 5. Laya intent-parser confidence calibration
Laya's base English checkpoint reports uncalibrated confidence scores for the
`action` field of our intent-parsing schema (consistently ~0.3, flagged by the
library itself as a known limitation of its zero-shot checkpoints). We treat
this conservatively: low-confidence classifications are routed through the
`/override` confirmation endpoint rather than being silently trusted, which
satisfies the requirement that classifiers "expose confidence and allow
correction of misclassification."

## 6. Synthetic, lab-generated traffic for classifier training
Our traffic classifier is trained on synthetic traffic generated within the
testbed (`classifier/traffic_generators.py`) rather than captured from real
household devices. Classification accuracy (99.1%) reflects performance on this
controlled dataset; real-world encrypted traffic may be more heterogeneous.

## 7. Scale
The testbed emulates a small household (1 gateway, 2 LAN hosts, 1 WAN
endpoint). Production deployment at ISP/router scale would require testing with
significantly more concurrent flows and devices.

## 8. Where real hardware/certification would be required
A production deployment would require: certified home-router hardware with
sufficient CPU for real-time packet classification; integration with actual
ISP uplink monitoring (not synthetic NetEm); and enterprise-grade identity management
(such as mTLS or OAuth2/OIDC, building upon the prototype's constant-time token
authentication and loopback-isolation controls).

## 9. Cooperative remote reflector requirement for active probing
Active SLoPS-style probing requires an active receiver/reflector on the remote
endpoint (e.g., ISP gateway, access point, or edge POP). In single-ended
deployments where no remote reflector is present, the engine automatically
falls back to passive interface byte counter analysis and RTT dispersion
heuristics in `estimator/passive_estimator.py`.

## 10. User-space socket pacing vs. native kernel pacing
The prototype SLoPS packet sender implements sub-millisecond inter-packet
pacing in user-space Python using `time.perf_counter()` busy-waiting and
preallocated byte buffers. While this achieves $< 15\%$ error up to 100+ Mbps
in our Linux namespace testbed, a commercial production deployment on router
CPEs would implement pacing natively in the kernel using eBPF/XDP, `io_uring`,
or a dedicated C daemon to eliminate user-space scheduler jitter.

## 11. SQLite Evidence Database & Result Artifact Scope Limitation
The SQLite WAL database (`experiments/evidence.db`) persists experiment metadata,
active flows, policy state transitions, and canonical evaluation summary scalar metrics
(e.g., `static_100_error_pct`, `static_20_error_pct`, and `adaptation_time_sec` for M2).
It is intentionally designed not to store high-frequency, packet-level raw probe trains
or microsecond arrival timestamp series to avoid write amplification and lock contention.
Similarly, evaluation artifacts in `results/m2/*.json` and `results/m2/summary.csv` store
structured experiment summaries, per-scenario validation metrics, and sampled capacity
estimates (including convergence status, iteration counts, aggregate PCT/PDT trend scores,
resource overhead, and sample ranges). Microsecond-level packet arrival timestamps are
analyzed in-memory during SLoPS execution and are not persisted to disk in either SQLite or
the summary files to minimize disk I/O and artifact footprint.

## 12. Bulk Non-Starvation: Analytical Planning Floor vs. CAKE DRR Servicing
AQE guarantees that bulk background traffic (e.g., OS updates, torrents, cloud backups)
is never starved when latency-sensitive applications (VoIP, gaming, video conferencing)
are active. To achieve this:
1. **Analytical Planning Floor:** The policy engine computes an analytical minimum bandwidth
   floor for bulk traffic as $\max(2, \text{round}(C_{\text{shaped}} \times 0.20))$ Mbps.
   This ensures that link capacity planning and admission reasoning explicitly account for
   bulk progress.
2. **Datapath Non-Starvation Enforced via CAKE DRR:** Rather than carving out a rigid,
   static sub-qdisc rate reservation (which would artificially cap bulk throughput or waste
   link capacity when high-priority queues are idle), CAKE enforces fair queuing across
   DiffServ tins using Deficit Round Robin (DRR) with per-tin byte quanta (e.g., 300 bytes for
   Bulk vs 1514 bytes for Best Effort). This mathematical queuing structure guarantees that
   the bulk tin (CS1 / Tin 0) is serviced in every round, strictly preventing starvation
   while allowing bulk flows to burst up to 100% of available bandwidth whenever priority
   flows fall silent.
