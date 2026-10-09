"""
Live 6-Metric QoS Monitoring Dashboard:
Visualizes Latency, Jitter, Packet Loss, Throughput, Queue Depth, and Fairness.
"""
import os
import sys
import json
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dashboard.metrics_collector import collect_snapshot

app = FastAPI(title="Adaptive QoS Engine Dashboard", version="2.0")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metrics_log.jsonl")

def _normalize_entry(d: dict) -> dict:
    """Normalize legacy 2-metric logs into the comprehensive 6-metric schema."""
    if "latency_ms" not in d:
        lat = d.get("latency", {})
        cake = d.get("cake_stats", {})
        return {
            "timestamp": d.get("timestamp", 0),
            "latency_ms": lat.get("avg_ms", 20.0),
            "jitter_ms": lat.get("jitter_ms", 0.2),
            "loss_pct": lat.get("loss_pct", 0.0),
            "throughput_mbps": d.get("throughput_mbps", 0.0),
            "queue_depth_pkts": cake.get("queue_depth_pkts", 0),
            "queue_depth_bytes": cake.get("queue_depth_bytes", 0),
            "fairness_index": d.get("fairness_index", 1.0),
            "cake_stats": cake
        }
    return d

@app.get("/api/metrics")
def get_metrics():
    data = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r") as f:
                for line in f:
                    if line.strip():
                        data.append(_normalize_entry(json.loads(line)))
        except Exception:
            pass

    # If log file is empty or sparse, supplement with a fresh snapshot
    if len(data) < 2:
        fresh = collect_snapshot()
        data.append(fresh)

    return data[-60:]  # Return up to last 60 points

@app.get("/api/snapshot")
def get_current_snapshot():
    return collect_snapshot()

@app.get("/", response_class=HTMLResponse)
def render_dashboard():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Adaptive QoS Engine — Telemetry Dashboard</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
            body { background: #0f141c; color: #e1e7ef; padding: 24px; }
            header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; border-bottom: 1px solid #1f293d; padding-bottom: 16px; }
            h1 { font-size: 22px; color: #00f2fe; display: flex; align-items: center; gap: 8px; }
            .badge { background: #132742; color: #38ef7d; padding: 6px 12px; border-radius: 20px; font-size: 13px; font-weight: bold; border: 1px solid #11998e; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 20px; }
            .card { background: #161f2e; border: 1px solid #233149; border-radius: 12px; padding: 18px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
            .card-header { display: flex; justify-content: space-between; margin-bottom: 12px; }
            .card-title { font-size: 14px; font-weight: 600; color: #8da2c0; text-transform: uppercase; letter-spacing: 0.5px; }
            .card-value { font-size: 20px; font-weight: 700; color: #fff; }
            canvas { max-height: 220px; width: 100%; }
        </style>
    </head>
    <body>
        <header>
            <h1>🎛️ Adaptive QoS Telemetry Dashboard</h1>
            <div class="badge" id="statusBadge">● SYSTEM ACTIVE (CAKE DiffServ4)</div>
        </header>

        <div class="grid">
            <!-- 1. Latency -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Interactive Latency</span>
                    <span class="card-value" id="valLatency">-- ms</span>
                </div>
                <canvas id="latencyChart"></canvas>
            </div>

            <!-- 2. Jitter -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Latency Jitter</span>
                    <span class="card-value" id="valJitter">-- ms</span>
                </div>
                <canvas id="jitterChart"></canvas>
            </div>

            <!-- 3. Packet Loss -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Packet Loss Rate</span>
                    <span class="card-value" id="valLoss">-- %</span>
                </div>
                <canvas id="lossChart"></canvas>
            </div>

            <!-- 4. Throughput -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">WAN Throughput</span>
                    <span class="card-value" id="valThroughput">-- Mbps</span>
                </div>
                <canvas id="throughputChart"></canvas>
            </div>

            <!-- 5. Queue Depth -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">CAKE Queue Depth</span>
                    <span class="card-value" id="valQueue">-- pkts</span>
                </div>
                <canvas id="queueChart"></canvas>
            </div>

            <!-- 6. Fairness -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Jain's Fairness Index</span>
                    <span class="card-value" id="valFairness">--</span>
                </div>
                <canvas id="fairnessChart"></canvas>
            </div>
        </div>

        <script>
        const charts = {};

        function createOrUpdateChart(id, labels, data, label, color, isFill=false) {
            if (charts[id]) {
                charts[id].data.labels = labels;
                charts[id].data.datasets[0].data = data;
                charts[id].update('none');
                return;
            }
            const ctx = document.getElementById(id).getContext('2d');
            charts[id] = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: label,
                        data: data,
                        borderColor: color,
                        backgroundColor: isFill ? color + '22' : 'transparent',
                        fill: isFill,
                        tension: 0.35,
                        borderWidth: 2,
                        pointRadius: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { display: true, grid: { color: '#1a2436' }, ticks: { color: '#556987', maxTicksLimit: 6 } },
                        y: { beginAtZero: true, grid: { color: '#1a2436' }, ticks: { color: '#556987' } }
                    }
                }
            });
        }

        async function fetchAndUpdate() {
            try {
                const res = await fetch('/api/metrics');
                const list = await res.json();
                if (!list || list.length === 0) return;

                const labels = list.map(d => new Date(d.timestamp * 1000).toLocaleTimeString());
                const latencies = list.map(d => d.latency_ms ?? 0);
                const jitters = list.map(d => d.jitter_ms ?? 0);
                const losses = list.map(d => d.loss_pct ?? 0);
                const throughputs = list.map(d => d.throughput_mbps ?? 0);
                const queues = list.map(d => d.queue_depth_pkts ?? 0);
                const fairness = list.map(d => d.fairness_index ?? 1.0);

                const latest = list[list.length - 1];
                document.getElementById('valLatency').innerText = latest.latency_ms != null ? `${latest.latency_ms} ms` : '--';
                document.getElementById('valJitter').innerText = latest.jitter_ms != null ? `${latest.jitter_ms} ms` : '--';
                document.getElementById('valLoss').innerText = latest.loss_pct != null ? `${latest.loss_pct} %` : '--';
                document.getElementById('valThroughput').innerText = latest.throughput_mbps != null ? `${latest.throughput_mbps} Mbps` : '0.0 Mbps';
                document.getElementById('valQueue').innerText = latest.queue_depth_pkts != null ? `${latest.queue_depth_pkts} pkts` : '--';
                document.getElementById('valFairness').innerText = latest.fairness_index != null ? `${latest.fairness_index}` : '--';

                createOrUpdateChart('latencyChart', labels, latencies, 'Latency (ms)', '#00f2fe');
                createOrUpdateChart('jitterChart', labels, jitters, 'Jitter (ms)', '#f7b731');
                createOrUpdateChart('lossChart', labels, losses, 'Packet Loss (%)', '#ff5252', true);
                createOrUpdateChart('throughputChart', labels, throughputs, 'Throughput (Mbps)', '#4facfe', true);
                createOrUpdateChart('queueChart', labels, queues, 'Queue Depth (pkts)', '#a55eea', true);
                createOrUpdateChart('fairnessChart', labels, fairness, 'Fairness Index', '#20bf6b');
            } catch (err) {
                console.error("Dashboard update failed:", err);
            }
        }

        fetchAndUpdate();
        setInterval(fetchAndUpdate, 2000);
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("AQE_DASHBOARD_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=8001)
