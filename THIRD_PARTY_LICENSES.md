# Third-Party Licenses

| Component | License | Notes |
|---|---|---|
| Linux kernel (CAKE, NetEm qdiscs) | GPLv2 | Used via `tc`/`iproute2` CLI; no kernel source modified beyond enabling existing config options |
| iproute2 | GPLv2 | System package, used as-is |
| XGBoost | Apache 2.0 | `pip install xgboost` |
| scikit-learn | BSD-3-Clause | `pip install scikit-learn` |
| pandas, numpy | BSD-3-Clause | `pip install pandas numpy` |
| FastAPI | MIT | `pip install fastapi` |
| Laya | Apache 2.0 | `pip install laya`; model weights downloaded from Hugging Face (convaiinnovations/laya) |
| PyTorch | BSD-3-Clause | CPU-only build, dependency of Laya |
| scapy | GPLv2 | `pip install scapy`, used for packet feature extraction |
| Chart.js | MIT | Loaded via CDN in dashboard HTML |
| iperf3 | BSD-3-Clause (variant) | System package, used as traffic generator/measurement tool |

No proprietary code, data, or media is redistributed in this repository.
