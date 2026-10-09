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
    host = os.environ.get("AQE_API_HOST", "127.0.0.1")
    is_loopback = host in ("127.0.0.1", "::1", "localhost")
    token = os.environ.get("AQE_API_TOKEN")

    if not is_loopback and not token and not os.environ.get("AQE_ALLOW_UNAUTHENTICATED_REMOTE"):
        print("[FATAL SECURITY ERROR] Remote binding requested without AQE_API_TOKEN configured.")
        print("Set AQE_API_TOKEN in environment to securely enable remote access.")
        sys.exit(1)

    print(f"[AQE] Starting authoritative unified dashboard from api/server wrapper on http://{host}:8080...")
    uvicorn.run(app, host=host, port=8080)
