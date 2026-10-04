# Phase 4 Supply Chain & License Compliance Audit Report

**Project:** Case Study 3 — Adaptive QoS Engine for Mixed Home Broadband Traffic  
**Evaluation Date:** 2026-10-03  
**Auditor:** Principal Backend & Systems Auditor  

---

## 1. Executive Summary
An inventory of all direct runtime, system, and machine learning dependencies was conducted. All third-party libraries use industry-standard open-source licenses compatible with edge and embedded router appliances (MIT, BSD-3-Clause, Apache-2.0, and GPL-2.0).

---

## 2. Dependency Inventory & License Matrix

| Component / Library | Version | Upstream License | Purpose in System | Verification Status |
|---|:---:|:---:|---|:---:|
| **XGBoost** | 2.0.3 | Apache-2.0 | Zero-payload NetMatrix flow classification | **VERIFIED** |
| **Scapy** | 2.7.0 | GPL-2.0 | Layer-3/Layer-4 header packet capture & parsing | **VERIFIED** |
| **FastAPI** | 0.141.1 | MIT | REST control plane, health, and observability | **VERIFIED** |
| **Starlette** | 1.7.0 | BSD-3-Clause | ASGI framework foundation for FastAPI | **VERIFIED** |
| **Uvicorn** | 0.54.0 | BSD-3-Clause | Production ASGI web server | **VERIFIED** |
| **Pydantic** | 2.13.5 | MIT | Strict request schema validation & sanitization | **VERIFIED** |
| **NumPy** | 2.5.3 | BSD-3-Clause | Numerical packet feature array calculations | **VERIFIED** |
| **Pandas** | 3.0.6 | BSD-3-Clause | Feature dataframe construction for classifier | **VERIFIED** |
| **Scikit-Learn** | 1.9.1 | BSD-3-Clause | Model serialization and preprocessing utilities | **VERIFIED** |
| **SQLite3** | Built-in | Public Domain | Evidence database persistence & integrity | **VERIFIED** |
| **iproute2 (tc)** | System | GPL-2.0 | Linux CAKE DiffServ4 & NetEm kernel mutations | **VERIFIED** |
| **Linux Kernel** | 6.18.40.1 | GPL-2.0 | Datapath Layer-3 routing & DiffServ4 queueing | **VERIFIED** |

---

## 3. Vulnerability & Version Pinning Review
- **Unpinned Dependencies:** 0. Runtime dependencies are managed via virtualenv `./venv/` with pinned release versions.
- **Copyleft Boundary:** GPL-2.0 utilities (`tc`, `ip`) are invoked via standard system process execution boundaries (`execve`), preserving license separation from the application control plane.
- **Zero-Telemetry Guarantee:** No telemetry, tracking, or cloud phone-home SDKs are included. All metrics are persisted locally in SQLite.
