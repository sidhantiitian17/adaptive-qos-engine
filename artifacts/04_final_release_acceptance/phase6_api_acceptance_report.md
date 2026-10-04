# Phase 6 API Acceptance Report

**Project:** Case Study 3 — Adaptive QoS Engine for Mixed Home Broadband Traffic  
**Component:** Control Plane & Observability REST API (`api/server.py` & `dashboard/unified_dashboard.py`)  
**Status Date:** 2026-10-04  
**Verdict:** **`VERIFIED PASS`**

---

## 1. REST API Specification & Endpoint Verification

The control plane exposes a well-defined REST API implemented using FastAPI with strict Pydantic model validation. Every endpoint was tested against the running service during the authoritative 24-step demo and the regression test suite.

| Endpoint | Method | Request Payload | Response Code | Description & Validation |
|:---|:---:|:---|:---:|:---|
| `/health` | GET | None | 200 OK | Health check returning controller status, active flows, and uptime. |
| `/readiness` | GET | None | 200 OK | Readiness probe verifying classifier and tc manager readiness. |
| `/api/network/status` | GET | None | 200 OK | Returns active WAN interface (`veth-gw-wan`) and network class. |
| `/api/controller/status` | GET | None | 200 OK | Comprehensive system state snapshot including active policy and intent. |
| `/api/flows` | GET | None | 200 OK | Returns list of currently active flows with ML classification & confidence. |
| `/api/measurements` | GET | `limit: int = 50` | 200 OK | Paginated historical telemetry measurements from `evidence.db`. |
| `/api/policies` | GET | `limit: int = 20` | 200 OK | Audit trail of dynamic policy changes and automated adaptations. |
| `/api/experiments` | GET | `limit: int = 20` | 200 OK | Execution records for benchmark experiments and scenarios. |
| `/api/evidence` | GET | None | 200 OK | Record counts across all relational tables in `evidence.db`. |
| `/api/intent` | POST | `IntentRequest` (`text`, `traffic_class`, `duration_sec`) | 200 OK | Schedules temporary service priority and executes policy cycle. |
| `/api/intent` | DELETE | None | 200 OK | Cancels active temporary priority and restores baseline policy. |
| `/api/override` | POST | `OverrideRequest` (`flow_id`, `corrected_class`) | 200 OK | Manually overrides classification and updates kernel DSCP tagging. |
| `/api/events` | GET | None | 200 OK | System log events with timestamp and severity levels. |

---

## 2. Input Validation & Error Handling

All incoming mutation requests are validated against strict security constraints:

1. **Empty Intent Protection:**
   - Request: `POST /api/intent {"text": ""}`
   - Response: `HTTP 400 Bad Request` (`detail: "Intent text cannot be empty."`)
   - Verified: Test `test_07_api_intent_validation_empty_text` passes.

2. **Excessive String Length Protection:**
   - Request: `POST /api/intent {"text": "A" * 300}`
   - Response: `HTTP 400 Bad Request` (`detail: "Intent text exceeds maximum allowed length of 256 characters."`)
   - Verified: Test `test_08_api_intent_validation_max_length` passes.

3. **Control Character Injection Protection:**
   - Request: `POST /api/intent {"text": "intent\x00malicious"}`
   - Response: `HTTP 400 Bad Request` (`detail: "Intent text contains invalid control characters."`)
   - Verified: Test `test_09_api_intent_validation_control_characters` passes.

4. **Invalid Duration Range:**
   - Request: `POST /api/intent {"text": "prioritize video", "duration_sec": 5}` (Duration < 10s)
   - Response: `HTTP 400 Bad Request` (`detail: "duration_sec must be between 10 and 86400 seconds."`)
   - Verified: Test `test_10_api_intent_validation_duration_range` passes.

5. **Invalid Flow Override Correction:**
   - Request: `POST /api/override {"flow_id": "10.0.1.2:5000", "corrected_class": "invalid_profile"}`
   - Response: `HTTP 400 Bad Request` (`detail: "Invalid corrected_class 'invalid_profile'..."`)
   - Verified: Test `test_11_api_override_validation` passes.

---

## 3. Conclusion

The API layer is robust, strictly validated, securely handles malformed inputs without crashing, and accurately reflects real-time system state.
