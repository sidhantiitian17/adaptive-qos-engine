"""
REST API for Intent-Aware QoS Engine:
Provides natural-language intent ingestion, real-time misclassification overrides,
flow monitoring, and active policy status endpoints.
"""
import os
import sys
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

# Ensure project modules are resolvable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from api.intent_parser import parse_intent
from api.intent_parser_fallback import parse_intent_fallback
from classifier.flow_table import FlowTable
from policy_engine.intent_scheduler import IntentScheduler
from policy_engine.policy_rules import decide_policy
from enforcement.dscp_marker import DscpMarker

app = FastAPI(title="Adaptive QoS Engine API", version="2.0")

# Shared state singletons
flow_table = FlowTable()
intent_scheduler = IntentScheduler(default_duration_sec=1200)
dscp_marker = DscpMarker(namespace="gw", dry_run=False)

# Track current policy decision
current_policy = {
    "bandwidth_mbit": 100,
    "diffserv_mode": "diffserv4",
    "active_intent": None,
    "active_classes": []
}

class IntentRequest(BaseModel):
    text: str
    duration_sec: Optional[int] = None

class OverrideRequest(BaseModel):
    flow_id: str
    corrected_class: str

class ManualPolicyRequest(BaseModel):
    bandwidth_mbit: int
    diffserv_mode: Optional[str] = "diffserv4"

@app.post("/intent")
def submit_intent(req: IntentRequest):
    """
    Ingest natural language intent, parse via Laya (with fallback),
    register priority session in scheduler, and apply priority policy.
    """
    try:
        parsed = parse_intent(req.text)
        parsed["parser"] = "laya"
    except Exception as e:
        parsed = parse_intent_fallback(req.text)
        parsed["parser"] = "fallback"
        parsed["fallback_reason"] = str(e)

    duration = req.duration_sec or parsed.get("duration_sec", 1200)
    traffic_class = parsed.get("traffic_class", "video_conference")
    action = parsed.get("action", "prioritize")

    if action == "prioritize":
        # Schedule the temporary priority with automatic reversion
        scheduled = intent_scheduler.schedule_intent(
            traffic_class=traffic_class,
            action=action,
            duration_sec=duration,
            on_expire=lambda rec: _handle_intent_expiration(rec)
        )
        current_policy["active_intent"] = scheduled
        parsed["execution_status"] = "scheduled_and_applied"
        parsed["expires_at"] = scheduled["expires_at"]
    elif action == "reset":
        intent_scheduler.clear()
        current_policy["active_intent"] = None
        parsed["execution_status"] = "reset_to_default"

    return parsed

def _handle_intent_expiration(record):
    """Callback when temporary intent timer expires."""
    print(f"[API SERVER] Intent expired for {record.get('traffic_class')}. Restoring baseline.")
    current_policy["active_intent"] = None

@app.post("/override")
def submit_override(req: OverrideRequest):
    """
    Manually correct a flow's traffic class (Constraint C5).
    Immediately updates the flow table and kernel DSCP mangle rules.
    """
    flow_table.override(req.flow_id, req.corrected_class)

    # Extract source IP if present in flow_id (e.g. 10.0.1.2:5000->...)
    if "->" in req.flow_id and ":" in req.flow_id:
        src_part = req.flow_id.split("->")[0]
        src_ip = src_part.split(":")[0]
        dscp_marker.mark_host(src_ip, req.corrected_class)
    elif ":" in req.flow_id:
        src_ip = req.flow_id.split(":")[0]
        dscp_marker.mark_host(src_ip, req.corrected_class)

    return {
        "status": "applied",
        "flow_id": req.flow_id,
        "corrected_class": req.corrected_class,
        "flow_state": flow_table.get(req.flow_id)
    }

@app.get("/status")
def get_status():
    """Return system state: active intent, policy parameters, and active flow counts."""
    active_intent = intent_scheduler.get_active_intent()
    active_flows = flow_table.get_active_flows(active_within_sec=30)
    current_policy["active_intent"] = active_intent
    current_policy["active_classes"] = list(set(f["class"] for f in active_flows))

    return {
        "policy": current_policy,
        "active_intent": active_intent,
        "active_flows_count": len(active_flows),
        "flow_classes_summary": flow_table.get_summary(),
        "recent_overrides": [f for f in active_flows if f.get("overridden")]
    }

@app.get("/flows")
def get_flows():
    """Return all active flows and their classification states."""
    return {"flows": flow_table.get_active_flows(active_within_sec=30)}

@app.delete("/intent")
def clear_intent():
    """Cancel any active temporary intent immediately."""
    intent_scheduler.clear()
    current_policy["active_intent"] = None
    return {"status": "cleared", "message": "Reverted to default baseline policy."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
