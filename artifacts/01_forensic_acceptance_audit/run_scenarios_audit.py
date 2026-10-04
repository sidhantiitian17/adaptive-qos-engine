import os
import sys
import time
import json
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if os.geteuid() != 0:
    subprocess.run(["unshare", "-rn", sys.executable, __file__] + sys.argv[1:])
    sys.exit(0)

subprocess.run(["ip", "link", "set", "dev", "lo", "up"], check=True)

from experiments.scenario_runner import ScenarioRunner

print("=== REPRODUCING SCENARIO A, B, AND C FORENSIC AUDIT ===")
runner = ScenarioRunner()

# Scenario A: Baseline vs Adaptive
print("\n[Scenario A] Running Baseline...")
res_a_base = runner.run_scenario_a(mode="BASELINE", duration_sec=3.0)
with open("audit_artifacts/scenario_a_baseline.json", "w") as f:
    json.dump(res_a_base, f, indent=2)

print("[Scenario A] Running Adaptive...")
res_a_adapt = runner.run_scenario_a(mode="ADAPTIVE", duration_sec=3.0)
with open("audit_artifacts/scenario_a_adaptive.json", "w") as f:
    json.dump(res_a_adapt, f, indent=2)

# Scenario B: WAN Collapse
print("\n[Scenario B] Running Baseline & Adaptive WAN Collapse...")
res_b_base = runner.run_scenario_b(mode="BASELINE", duration_sec=2.0)
res_b_adapt = runner.run_scenario_b(mode="ADAPTIVE", duration_sec=2.0)
with open("audit_artifacts/scenario_b.json", "w") as f:
    json.dump({"baseline": res_b_base, "adaptive": res_b_adapt}, f, indent=2)

# Scenario C: 3 TV Streams + Gaming Device
print("\n[Scenario C] Running Baseline...")
res_c_base = runner.run_scenario_c(mode="BASELINE", duration_sec=3.0)
with open("audit_artifacts/scenario_c_baseline.json", "w") as f:
    json.dump(res_c_base, f, indent=2)

print("[Scenario C] Running Adaptive...")
res_c_adapt = runner.run_scenario_c(mode="ADAPTIVE", duration_sec=3.0)
with open("audit_artifacts/scenario_c_adaptive.json", "w") as f:
    json.dump(res_c_adapt, f, indent=2)

print("\nAll forensic scenario reproductions complete.")
