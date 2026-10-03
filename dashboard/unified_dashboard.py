"""
Unified QoS Dashboard — Single-Page Judge-Ready Demo Interface
Combines: 6-metric telemetry + traffic classification table + intent control +
baseline-vs-optimized comparison + event log — all live-updating.
"""
import os, sys, time, json, threading
from collections import deque
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dashboard.metrics_collector import collect_snapshot
from classifier.flow_table import FlowTable
from classifier.runtime_classifier import FlowClassifier
from policy_engine.intent_scheduler import IntentScheduler
from policy_engine.policy_rules import decide_policy
from policy_engine.rollback_manager import RollbackManager
from enforcement.dscp_marker import DscpMarker, CLASS_TO_DSCP

app = FastAPI(title="Adaptive QoS Engine — Unified Dashboard", version="3.0")

# ─── Shared State ───
flow_table = FlowTable()
intent_scheduler = IntentScheduler(default_duration_sec=1200)
dscp_marker = DscpMarker(namespace="gw", dry_run=True)
rollback_mgr = RollbackManager(namespace="gw", iface="veth-gw-wan", dry_run=True)
classifier = FlowClassifier()

event_log = deque(maxlen=200)
system_state = {
    "status": "NORMAL",
    "wan_bandwidth_mbps": 100.0,
    "current_policy_bw": 100,
    "last_update": time.time()
}

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metrics_log.jsonl")

def log_event(msg, level="INFO"):
    entry = {"ts": time.strftime("%H:%M:%S"), "msg": msg, "level": level}
    event_log.appendleft(entry)

log_event("Dashboard started. System in NORMAL state.", "INFO")

# ─── Pydantic Models ───
class IntentRequest(BaseModel):
    text: str
    duration_sec: Optional[int] = None

class OverrideRequest(BaseModel):
    flow_id: str
    corrected_class: str

# ─── API Endpoints ───
@app.get("/api/metrics")
def get_metrics():
    data = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r") as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        if "latency_ms" not in d:
                            lat = d.get("latency", {})
                            d = {
                                "timestamp": d.get("timestamp", 0),
                                "latency_ms": lat.get("avg_ms", 20.0),
                                "jitter_ms": lat.get("jitter_ms", 0.2),
                                "loss_pct": lat.get("loss_pct", 0.0),
                                "throughput_mbps": d.get("throughput_mbps", 0.0),
                                "queue_depth_pkts": d.get("cake_stats", {}).get("queue_depth_pkts", 0),
                                "fairness_index": d.get("fairness_index", 1.0),
                            }
                        data.append(d)
        except Exception:
            pass
    if len(data) < 2:
        data.append(collect_snapshot())
    return data[-60:]

@app.get("/api/snapshot")
def get_snapshot():
    return collect_snapshot()

@app.get("/api/status")
def get_status():
    active_intent = intent_scheduler.get_active_intent()
    active_flows = flow_table.get_active_flows(active_within_sec=30)
    status = system_state["status"]
    if rollback_mgr.history_log and rollback_mgr.history_log[-1].get("status") == "rolled_back":
        status = "ROLLED_BACK"
    return {
        "system_status": status,
        "wan_bandwidth_mbps": system_state["wan_bandwidth_mbps"],
        "current_policy_bw": system_state["current_policy_bw"],
        "active_intent": active_intent,
        "active_flows_count": len(active_flows),
        "flow_classes": list(set(f.get("class", "unknown") for f in active_flows)),
        "dscp_rules_count": len(dscp_marker.get_rules()),
        "rollback_history_count": len(rollback_mgr.history_log),
    }

@app.get("/api/flows")
def get_flows():
    flows = flow_table.get_active_flows(active_within_sec=60)
    enriched = []
    for f in flows:
        fclass = f.get("class", "unclassified")
        dscp = CLASS_TO_DSCP.get(fclass, CLASS_TO_DSCP.get("default", {}))
        f["dscp_name"] = dscp.get("name", "CS0")
        f["dscp_val"] = dscp.get("val", "0x00")
        enriched.append(f)
    return {"flows": enriched}

@app.post("/api/intent")
def submit_intent(req: IntentRequest):
    from api.intent_parser_fallback import parse_intent_fallback
    try:
        from api.intent_parser import parse_intent
        parsed = parse_intent(req.text)
        parsed["parser"] = "laya"
    except Exception:
        parsed = parse_intent_fallback(req.text)
        parsed["parser"] = "fallback"

    duration = req.duration_sec or parsed.get("duration_sec", 1200)
    traffic_class = parsed.get("traffic_class", "video_conference")
    action = parsed.get("action", "prioritize")

    # If Laya/fallback detected a class but couldn't determine action,
    # default to "prioritize" — user saying "I have a video call" implies prioritize.
    if action in ("none", None, "") and traffic_class not in ("other", "unknown"):
        action = "prioritize"

    if action == "prioritize":
        scheduled = intent_scheduler.schedule_intent(
            traffic_class=traffic_class, action=action, duration_sec=duration,
            on_expire=lambda r: (log_event(f"Intent expired for {r['traffic_class']}. Reverted to baseline.", "WARN"),
                                 system_state.update({"status": "NORMAL"}))
        )
        system_state["status"] = "PRIORITY_ACTIVE"
        log_event(f"Intent scheduled: prioritize {traffic_class} for {duration}s", "ACTION")
        parsed["execution_status"] = "scheduled_and_applied"
        parsed["expires_at"] = scheduled.get("expires_at")
    elif action == "reset":
        intent_scheduler.clear()
        system_state["status"] = "NORMAL"
        log_event("Intent cleared. Reverted to default baseline.", "ACTION")
        parsed["execution_status"] = "reset_to_default"
    return parsed

@app.delete("/api/intent")
def clear_intent():
    intent_scheduler.clear()
    system_state["status"] = "NORMAL"
    log_event("Active intent cancelled by user.", "ACTION")
    return {"status": "cleared"}

@app.post("/api/override")
def submit_override(req: OverrideRequest):
    flow_table.override(req.flow_id, req.corrected_class)
    if "->" in req.flow_id and ":" in req.flow_id:
        src_ip = req.flow_id.split(":")[0]
        dscp_marker.mark_host(src_ip, req.corrected_class)
    log_event(f"Manual override: {req.flow_id} → {req.corrected_class}", "ACTION")
    return {"status": "applied", "flow_id": req.flow_id, "corrected_class": req.corrected_class}

@app.get("/api/events")
def get_events():
    return list(event_log)

@app.get("/api/comparison")
def get_comparison():
    results_path = os.path.join(PROJECT_ROOT, "experiments", "downstream_qos_results.json")
    comparison = {
        "headline": {
            "baseline_latency_ms": 965.6, "optimized_latency_ms": 20.5,
            "baseline_jitter_ms": 566.9, "optimized_jitter_ms": 0.18,
            "baseline_bulk_mbps": 17.2, "optimized_bulk_mbps": 16.9,
            "latency_reduction_pct": 97.9
        },
        "classifier": {
            "heuristic_accuracy": 93.1, "xgboost_accuracy": 99.1,
            "heuristic_qos_damage_ms": 12.5, "xgboost_qos_damage_ms": 2.3,
            "qos_damage_reduction_pct": 82
        }
    }
    if os.path.exists(results_path):
        with open(results_path) as f:
            comparison["downstream_detail"] = json.load(f)
    return comparison

@app.post("/api/simulate/inject-failure")
def simulate_inject_failure():
    rollback_mgr.apply_policy(50, "diffserv4")
    rollback_mgr.make_permanent(50)
    log_event("Applied 50mbit policy (known-good).", "ACTION")
    rollback_mgr.apply_policy(1, "diffserv4")
    log_event("Injected BAD policy: 1mbit.", "WARN")
    healthy = rollback_mgr.health_check()
    if not healthy:
        rollback_mgr.rollback()
        system_state["status"] = "ROLLED_BACK"
        log_event("Health check FAILED → auto-rollback to 50mbit.", "ERROR")
        return {"result": "rollback_triggered", "restored_to": 50}
    return {"result": "unexpected_pass"}

@app.post("/api/simulate/bandwidth-drop")
def simulate_bandwidth_drop():
    system_state["wan_bandwidth_mbps"] = 20.0
    system_state["status"] = "DEGRADED"
    decision = decide_policy(20.0, flow_table.get_active_flows(active_within_sec=30))
    system_state["current_policy_bw"] = decision["bandwidth_mbit"]
    log_event("WAN bandwidth drop detected: 100 → 20 Mbps.", "WARN")
    log_event(f"Policy recalculated: shaping → {decision['bandwidth_mbit']}mbit.", "ACTION")
    return {"new_capacity": 20, "new_shaping": decision["bandwidth_mbit"]}

@app.post("/api/simulate/restore")
def simulate_restore():
    system_state["wan_bandwidth_mbps"] = 100.0
    system_state["current_policy_bw"] = 100
    system_state["status"] = "NORMAL"
    log_event("WAN bandwidth restored to 100 Mbps. System NORMAL.", "INFO")
    return {"status": "restored"}

@app.post("/api/simulate/add-flows")
def simulate_add_flows():
    samples = [
        ("10.0.1.2:5000->10.0.3.2:5201/udp", 200, 64, 0.4, "video_conference"),
        ("10.0.2.2:9001->10.0.3.2:9001/udp", 88, 63, 3.0, "gaming"),
        ("10.0.2.2:45000->10.0.3.2:80/tcp", 1500, 63, 0.2, "bulk_download"),
        ("10.0.1.2:5100->10.0.3.2:443/tcp", 220, 64, 0.5, "video_conference"),
    ]
    for fid, tl, ttl, ia, gt in samples:
        for _ in range(5):
            flow_table.record_packet(fid, tl, ttl)
        result = classifier.predict_sample(tl, ttl, ia)
        flow_table.update_classification(fid, result["class"], result["confidence"])
        dscp_marker.mark_host(fid.split(":")[0], result["class"])
    log_event(f"Simulated {len(samples)} flows added to flow table.", "INFO")
    return {"flows_added": len(samples)}

# ─── Dashboard HTML ───
@app.get("/", response_class=HTMLResponse)
def render_dashboard():
    return DASHBOARD_HTML

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Adaptive QoS Engine — Control Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
:root{--bg:#0b1120;--card:#111827;--border:#1e293b;--accent:#06b6d4;--green:#10b981;--yellow:#f59e0b;--red:#ef4444;--text:#e2e8f0;--muted:#64748b;--font:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:var(--font);font-size:14px}
/* TOP BAR */
.topbar{display:flex;justify-content:space-between;align-items:center;padding:14px 24px;background:#0f172a;border-bottom:1px solid var(--border)}
.topbar h1{font-size:18px;color:var(--accent);display:flex;align-items:center;gap:8px}
.topbar .badges{display:flex;gap:12px;align-items:center}
.badge{padding:6px 14px;border-radius:20px;font-size:12px;font-weight:700;letter-spacing:.5px}
.badge-normal{background:#064e3b;color:#6ee7b7;border:1px solid #10b981}
.badge-degraded{background:#78350f;color:#fcd34d;border:1px solid #f59e0b}
.badge-rolled-back{background:#7f1d1d;color:#fca5a5;border:1px solid #ef4444}
.badge-priority{background:#1e1b4b;color:#a5b4fc;border:1px solid #818cf8}
.wan-num{font-size:22px;font-weight:800;color:#fff}
.wan-label{font-size:11px;color:var(--muted);text-transform:uppercase}
.intent-badge{font-size:12px;color:#c4b5fd;background:#312e81;padding:6px 12px;border-radius:8px}
/* SECTIONS */
.container{max-width:1440px;margin:0 auto;padding:16px 20px}
.section-title{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin:20px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--border)}
/* METRICS GRID */
.metrics-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.metric-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px}
.metric-header{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
.metric-title{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
.metric-value{font-size:20px;font-weight:700;color:#fff}
canvas{max-height:140px!important}
/* SPLIT PANEL */
.split{display:grid;grid-template-columns:3fr 2fr;gap:14px;margin-top:14px}
/* TABLE */
.flow-table{width:100%;border-collapse:collapse;font-size:13px}
.flow-table th{text-align:left;padding:8px 10px;color:var(--muted);border-bottom:1px solid var(--border);font-size:11px;text-transform:uppercase}
.flow-table td{padding:7px 10px;border-bottom:1px solid #1a2332}
.flow-table tr:hover{background:#1a2332}
.conf-high{color:var(--green)}.conf-mid{color:var(--yellow)}.conf-low{color:var(--red)}
.btn{padding:4px 10px;border:none;border-radius:4px;cursor:pointer;font-size:11px;font-weight:600}
.btn-correct{background:#1e293b;color:var(--accent);border:1px solid var(--accent)}
.btn-correct:hover{background:var(--accent);color:#000}
.btn-primary{background:var(--accent);color:#000;padding:8px 16px;font-size:13px;border-radius:6px;border:none;cursor:pointer;font-weight:700}
.btn-primary:hover{background:#22d3ee}
.btn-danger{background:var(--red);color:#fff;padding:6px 12px;border-radius:6px;border:none;cursor:pointer;font-size:12px}
.btn-warn{background:var(--yellow);color:#000;padding:6px 12px;border-radius:6px;border:none;cursor:pointer;font-size:12px}
.btn-sm{padding:6px 12px;font-size:12px;border-radius:6px;border:1px solid var(--border);background:var(--card);color:var(--text);cursor:pointer}
.btn-sm:hover{border-color:var(--accent);color:var(--accent)}
/* INTENT PANEL */
.intent-panel{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px}
.intent-input{width:100%;padding:10px;background:#1e293b;border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;margin-bottom:10px}
.intent-input:focus{outline:none;border-color:var(--accent)}
.quick-btns{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.active-intent-card{background:#1e1b4b;border:1px solid #4338ca;border-radius:8px;padding:10px;margin-top:10px}
.countdown{font-size:20px;font-weight:800;color:#a5b4fc}
/* COMPARISON */
.compare-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.compare-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;text-align:center}
.compare-label{font-size:11px;color:var(--muted);text-transform:uppercase;margin-bottom:8px}
.compare-old{font-size:28px;font-weight:800;color:var(--red);text-decoration:line-through;opacity:.6}
.compare-new{font-size:28px;font-weight:800;color:var(--green)}
.compare-arrow{font-size:16px;color:var(--muted);margin:2px 0}
.improvement{font-size:12px;color:var(--green);font-weight:700;margin-top:4px}
/* EVENT LOG */
.event-log{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px;max-height:220px;overflow-y:auto;font-family:'Courier New',monospace;font-size:12px}
.event-log .ev{padding:3px 0;border-bottom:1px solid #1a2332}
.ev-info{color:#94a3b8}.ev-action{color:var(--accent)}.ev-warn{color:var(--yellow)}.ev-error{color:var(--red)}
/* SIM BUTTONS */
.sim-bar{display:flex;gap:8px;margin:14px 0;flex-wrap:wrap}
/* OVERRIDE MODAL */
.modal-bg{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.6);z-index:100;justify-content:center;align-items:center}
.modal-bg.show{display:flex}
.modal{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px;min-width:320px}
.modal h3{margin-bottom:12px;color:var(--accent)}
.modal select{width:100%;padding:8px;background:#1e293b;color:var(--text);border:1px solid var(--border);border-radius:6px;margin-bottom:12px}
@media(max-width:900px){.metrics-grid{grid-template-columns:repeat(2,1fr)}.split{grid-template-columns:1fr}.compare-grid{grid-template-columns:1fr}}
</style>
</head>
<body>

<!-- ZONE 1: TOP BAR -->
<div class="topbar">
  <h1>🎛️ Adaptive QoS Engine</h1>
  <div class="badges">
    <span class="badge badge-normal" id="statusBadge">● NORMAL</span>
    <div style="text-align:center">
      <div class="wan-num" id="wanBw">100.0</div>
      <div class="wan-label">WAN Mbps</div>
    </div>
    <span class="intent-badge" id="intentBadge">No active intent</span>
  </div>
</div>

<div class="container">

<!-- SIMULATION CONTROLS -->
<div class="section-title">🧪 Live Simulation Controls (for demo)</div>
<div class="sim-bar">
  <button class="btn-sm" onclick="simAction('/api/simulate/add-flows','POST')">＋ Add Sample Flows</button>
  <button class="btn-sm" onclick="simAction('/api/simulate/bandwidth-drop','POST')">⚡ WAN Drop 100→20</button>
  <button class="btn-sm" onclick="simAction('/api/simulate/restore','POST')">↻ Restore WAN</button>
  <button class="btn-danger" onclick="simAction('/api/simulate/inject-failure','POST')">💀 Inject Bad Policy</button>
</div>

<!-- ZONE 2: LIVE METRICS -->
<div class="section-title">📊 Live Telemetry — 6 Required Metrics</div>
<div class="metrics-grid">
  <div class="metric-card"><div class="metric-header"><span class="metric-title">Interactive Latency</span><span class="metric-value" id="valLat">—</span></div><canvas id="cLat"></canvas></div>
  <div class="metric-card"><div class="metric-header"><span class="metric-title">Jitter</span><span class="metric-value" id="valJit">—</span></div><canvas id="cJit"></canvas></div>
  <div class="metric-card"><div class="metric-header"><span class="metric-title">Packet Loss</span><span class="metric-value" id="valLoss">—</span></div><canvas id="cLoss"></canvas></div>
  <div class="metric-card"><div class="metric-header"><span class="metric-title">Throughput</span><span class="metric-value" id="valTput">—</span></div><canvas id="cTput"></canvas></div>
  <div class="metric-card"><div class="metric-header"><span class="metric-title">Queue Depth</span><span class="metric-value" id="valQ">—</span></div><canvas id="cQ"></canvas></div>
  <div class="metric-card"><div class="metric-header"><span class="metric-title">Jain's Fairness</span><span class="metric-value" id="valFair">—</span></div><canvas id="cFair"></canvas></div>
</div>

<!-- ZONE 3: TRAFFIC TABLE + INTENT PANEL -->
<div class="split">
  <div>
    <div class="section-title">🔍 Traffic Classification Table (live flows)</div>
    <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;overflow:hidden">
      <table class="flow-table">
        <thead><tr><th>Flow ID</th><th>Class</th><th>Confidence</th><th>DSCP</th><th>Override</th></tr></thead>
        <tbody id="flowBody"><tr><td colspan="5" style="color:var(--muted);text-align:center;padding:20px">No flows yet — click "Add Sample Flows" above</td></tr></tbody>
      </table>
    </div>
  </div>
  <div>
    <div class="section-title">🎯 Intent Control Panel</div>
    <div class="intent-panel">
      <input class="intent-input" id="nlInput" placeholder='e.g. "I have a video call, prioritize it"'>
      <button class="btn-primary" style="width:100%;margin-bottom:12px" onclick="submitIntent()">Submit Intent (Laya NLP)</button>
      <div class="quick-btns">
        <button class="btn-sm" onclick="quickIntent('prioritize video call',900)">📹 Video 15m</button>
        <button class="btn-sm" onclick="quickIntent('prioritize video call',1800)">📹 Video 30m</button>
        <button class="btn-sm" onclick="quickIntent('prioritize gaming',900)">🎮 Gaming 15m</button>
        <button class="btn-sm" onclick="quickIntent('prioritize gaming',1800)">🎮 Gaming 30m</button>
      </div>
      <div id="activeIntentArea"></div>
    </div>
  </div>
</div>

<!-- ZONE 4: BASELINE vs OPTIMIZED -->
<div class="section-title">⚔️ Baseline (FIFO) vs Optimized (CAKE+DSCP) — Automated Experiment Results</div>
<div class="compare-grid">
  <div class="compare-card">
    <div class="compare-label">Avg Latency</div>
    <div class="compare-old">965.6 ms</div>
    <div class="compare-arrow">▼</div>
    <div class="compare-new">20.5 ms</div>
    <div class="improvement">↓ 97.9% reduction</div>
  </div>
  <div class="compare-card">
    <div class="compare-label">Jitter</div>
    <div class="compare-old">566.9 ms</div>
    <div class="compare-arrow">▼</div>
    <div class="compare-new">0.18 ms</div>
    <div class="improvement">↓ 99.97% reduction</div>
  </div>
  <div class="compare-card">
    <div class="compare-label">Bulk Throughput</div>
    <div class="compare-old" style="text-decoration:none;color:var(--text);opacity:1">17.2 Mbps</div>
    <div class="compare-arrow">≈</div>
    <div class="compare-new">16.9 Mbps</div>
    <div class="improvement" style="color:var(--accent)">Fair — no starvation ✓</div>
  </div>
</div>
<div class="compare-grid" style="margin-top:14px">
  <div class="compare-card">
    <div class="compare-label">Classifier: Heuristic</div>
    <div class="compare-old" style="text-decoration:none;opacity:1">93.1% accuracy</div>
    <div style="font-size:11px;color:var(--red);margin-top:4px">25 bulk pkts over-prioritized</div>
  </div>
  <div class="compare-card">
    <div class="compare-label">Classifier: XGBoost (AI)</div>
    <div class="compare-new">99.1% accuracy</div>
    <div style="font-size:11px;color:var(--green);margin-top:4px">Only 1 pkt over-prioritized</div>
  </div>
  <div class="compare-card">
    <div class="compare-label">QoS Damage Reduction</div>
    <div class="compare-new" style="font-size:36px">82%</div>
    <div class="improvement">XGBoost vs heuristic</div>
  </div>
</div>

<!-- ZONE 5: EVENT LOG -->
<div class="section-title">📋 Event / Decision Log</div>
<div class="event-log" id="eventLog"><div class="ev ev-info">Waiting for events...</div></div>

</div><!-- /container -->

<!-- OVERRIDE MODAL -->
<div class="modal-bg" id="overrideModal">
  <div class="modal">
    <h3>Override Classification</h3>
    <p style="font-size:12px;color:var(--muted);margin-bottom:8px">Flow: <span id="overrideFlowId"></span></p>
    <select id="overrideSelect">
      <option value="video_conference">video_conference (AF41)</option>
      <option value="gaming">gaming (EF)</option>
      <option value="bulk_download">bulk_download (CS1)</option>
    </select>
    <div style="display:flex;gap:8px">
      <button class="btn-primary" onclick="doOverride()">Apply Override</button>
      <button class="btn-sm" onclick="closeModal()">Cancel</button>
    </div>
  </div>
</div>

<script>
const charts={};
const COLORS={latency:'#06b6d4',jitter:'#f59e0b',loss:'#ef4444',throughput:'#3b82f6',queue:'#8b5cf6',fairness:'#10b981'};

function mkChart(id,label,color,fill=false){
  const ctx=document.getElementById(id).getContext('2d');
  charts[id]=new Chart(ctx,{type:'line',data:{labels:[],datasets:[{label,data:[],borderColor:color,backgroundColor:fill?color+'22':'transparent',fill,tension:.3,borderWidth:2,pointRadius:1}]},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:false}},scales:{x:{display:true,grid:{color:'#1a2436'},ticks:{color:'#556987',maxTicksLimit:5,font:{size:10}}},y:{beginAtZero:true,grid:{color:'#1a2436'},ticks:{color:'#556987',font:{size:10}}}}}});
}
function updChart(id,labels,data){if(!charts[id])return;charts[id].data.labels=labels;charts[id].data.datasets[0].data=data;charts[id].update('none');}

mkChart('cLat','Latency',COLORS.latency);
mkChart('cJit','Jitter',COLORS.jitter);
mkChart('cLoss','Loss',COLORS.loss,true);
mkChart('cTput','Throughput',COLORS.throughput,true);
mkChart('cQ','Queue',COLORS.queue,true);
mkChart('cFair','Fairness',COLORS.fairness);

// ─── POLLING ───
async function refresh(){
  try{
    // Metrics
    const m=await(await fetch('/api/metrics')).json();
    if(m.length){
      const lb=m.map(d=>new Date((d.timestamp||0)*1000).toLocaleTimeString());
      updChart('cLat',lb,m.map(d=>d.latency_ms??0));
      updChart('cJit',lb,m.map(d=>d.jitter_ms??0));
      updChart('cLoss',lb,m.map(d=>d.loss_pct??0));
      updChart('cTput',lb,m.map(d=>d.throughput_mbps??0));
      updChart('cQ',lb,m.map(d=>d.queue_depth_pkts??0));
      updChart('cFair',lb,m.map(d=>d.fairness_index??1));
      const l=m[m.length-1];
      document.getElementById('valLat').textContent=(l.latency_ms??0)+' ms';
      document.getElementById('valJit').textContent=(l.jitter_ms??0)+' ms';
      document.getElementById('valLoss').textContent=(l.loss_pct??0)+' %';
      document.getElementById('valTput').textContent=(l.throughput_mbps??0)+' Mbps';
      document.getElementById('valQ').textContent=(l.queue_depth_pkts??0)+' pkts';
      document.getElementById('valFair').textContent=(l.fairness_index??1).toFixed(2);
    }
    // Status
    const s=await(await fetch('/api/status')).json();
    const sb=document.getElementById('statusBadge');
    const st=s.system_status||'NORMAL';
    sb.textContent='● '+st;
    sb.className='badge badge-'+(st==='NORMAL'?'normal':st==='DEGRADED'?'degraded':st==='PRIORITY_ACTIVE'?'priority':'rolled-back');
    document.getElementById('wanBw').textContent=(s.wan_bandwidth_mbps||100).toFixed(1);
    const ai=s.active_intent;
    const ib=document.getElementById('intentBadge');
    if(ai&&ai.traffic_class){
      const rem=ai.remaining_sec||0;
      ib.textContent='⏱ '+ai.traffic_class+' priority — '+Math.ceil(rem/60)+'m '+Math.floor(rem%60)+'s left';
      ib.style.background='#312e81';
      document.getElementById('activeIntentArea').innerHTML='<div class="active-intent-card"><div style="display:flex;justify-content:space-between;align-items:center"><div><div style="font-size:12px;color:var(--muted)">Active Priority</div><div style="font-size:15px;font-weight:700;color:#c4b5fd">'+ai.traffic_class+'</div></div><div class="countdown">'+Math.ceil(rem/60)+'m '+Math.floor(rem%60)+'s</div></div><button class="btn-danger" style="margin-top:8px;width:100%" onclick="cancelIntent()">Cancel Intent</button></div>';
    }else{
      ib.textContent='No active intent';ib.style.background='#1e293b';
      document.getElementById('activeIntentArea').innerHTML='';
    }
    // Flows
    const fl=await(await fetch('/api/flows')).json();
    const tb=document.getElementById('flowBody');
    if(fl.flows&&fl.flows.length){
      tb.innerHTML=fl.flows.map(f=>{
        const c=f.confidence||0;const cc=c>=.9?'conf-high':c>=.7?'conf-mid':'conf-low';
        const cls=f.class||'?';const dscp=f.dscp_name||'CS0';
        const ov=f.overridden?'<span style="color:var(--yellow)">✎ manual</span>':'<button class="btn btn-correct" onclick="openOverride(\''+f.flow_id+'\')">Correct</button>';
        return '<tr><td style="font-size:12px;font-family:monospace">'+f.flow_id+'</td><td>'+cls+'</td><td class="'+cc+'">'+(c*100).toFixed(0)+'%</td><td>'+dscp+'</td><td>'+ov+'</td></tr>';
      }).join('');
    }
    // Events
    const ev=await(await fetch('/api/events')).json();
    const el=document.getElementById('eventLog');
    if(ev.length){
      el.innerHTML=ev.map(e=>'<div class="ev ev-'+(e.level||'info').toLowerCase()+'"><span style="color:#475569">['+e.ts+']</span> '+e.msg+'</div>').join('');
    }
  }catch(e){console.error(e)}
}
refresh();setInterval(refresh,2000);

// ─── ACTIONS ───
async function simAction(url,method){await fetch(url,{method});refresh();}
async function submitIntent(){
  const t=document.getElementById('nlInput').value;if(!t)return;
  await fetch('/api/intent',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});
  document.getElementById('nlInput').value='';refresh();
}
function quickIntent(text,dur){
  fetch('/api/intent',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,duration_sec:dur})}).then(()=>refresh());
}
function cancelIntent(){fetch('/api/intent',{method:'DELETE'}).then(()=>refresh());}

let overrideFlowId='';
function openOverride(fid){overrideFlowId=fid;document.getElementById('overrideFlowId').textContent=fid;document.getElementById('overrideModal').classList.add('show');}
function closeModal(){document.getElementById('overrideModal').classList.remove('show');}
function doOverride(){
  const cls=document.getElementById('overrideSelect').value;
  fetch('/api/override',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({flow_id:overrideFlowId,corrected_class:cls})}).then(()=>{closeModal();refresh();});
}
</script>
</body>
</html>"""

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  Adaptive QoS Engine — Unified Dashboard")
    print("  Open: http://localhost:8080")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8080)
