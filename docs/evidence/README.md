# Forensic Audit & Reproducibility Evidence Package

This directory contains the complete, unedited forensic reproducibility audit evidence for the **Adaptive QoS Engine**. Every artifact in this directory was generated during a clean-room audit executed against commit [`4040228`](https://github.com/sidhantiitian17/adaptive-qos-engine/commit/40402280a62006b5ed30f9612382a9bddc66813e) and verified on branch `fix/reproducible-presentation-alignment`.

---

## Directory Contents

| Path | Description |
|:---|:---|
| [`screenshot_manifest.csv`](screenshot_manifest.csv) | Full machine-readable manifest mapping all 26 genuine terminal screenshots to commands, exit codes, and raw logs. |
| [`environment_fingerprint.txt`](environment_fingerprint.txt) | Detailed host system fingerprint (kernel version, OS release, CPU, memory, networking utilities). |
| [`git_manifest.txt`](git_manifest.txt) | Git repository provenance and commit metadata at audit baseline. |
| [`screenshots/`](screenshots/) | Directory of 26 authentic terminal screenshots captured via `xvfb-run` + `xterm` + `maim` across 11 audit stages. |
| [`terminal_logs/`](terminal_logs/) | Raw text terminal transcripts and standard output logs matching each screenshot. |
| [`reports/FORENSIC_REPRODUCIBILITY_REPORT.md`](reports/FORENSIC_REPRODUCIBILITY_REPORT.md) | Exhaustive forensic audit report detailing findings, root causes, and reproducible presentation numbers. |
| [`reports/discrepancy_matrix.md`](reports/discrepancy_matrix.md) | Itemized comparison matrix resolving differences between README claims, slide presentations, and runtime measurements. |

---

## Evidence Integrity Policy

1. **Zero Fabrication**: No terminal screenshot, metric, test summary, or log file in this evidence package has been synthesized, mocked, or retrospectively edited.
2. **Explicit Provenance**: Every metric links directly to its execution command, exit code, and captured raw log file.
3. **Commit Distinction**: Results from the baseline audit of original commit `4040228` are strictly distinguished from results verified after bug remediation on branch `fix/reproducible-presentation-alignment`.
