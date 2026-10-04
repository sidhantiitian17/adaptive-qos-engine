"""
[QUARANTINED / DEPRECATED PROTOTYPE SERVER]
This standalone prototype API on port 8000 has been retired and quarantined
to prevent split-brain state or hardcoded prototype defaults.

The authoritative application state, control plane, closed-loop engine,
and REST API endpoints are unified and actively maintained in
dashboard/unified_dashboard.py on port 8080.

To maintain backward compatibility if launched via `uvicorn api.server:app`,
this module delegates directly to the authoritative unified dashboard app.
"""
import os
import sys
import warnings

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

warnings.warn(
    "api/server.py is deprecated and quarantined. Delegating to authoritative dashboard/unified_dashboard.py",
    DeprecationWarning,
    stacklevel=2
)

# Export the authoritative unified application
from dashboard.unified_dashboard import app

if __name__ == "__main__":
    import uvicorn
    print("[AQE] Starting authoritative unified dashboard from api/server wrapper on http://127.0.0.1:8080...")
    uvicorn.run(app, host="0.0.0.0", port=8080)
