#!/usr/bin/env python3
"""
Downstream QoS Effect Comparison:
Shows that XGBoost's classification accuracy improvement over the heuristic
baseline translates to REAL QoS improvement (correct DSCP marking → lower latency).

This satisfies the CONTEXT recommendation:
  "Show downstream effect — QoS improvement (latency reduction %) when ML
   classifier is used vs heuristic."

Methodology:
  1. Generate a mixed traffic workload (video + bulk + gaming packets)
  2. Classify each packet with BOTH classifiers (heuristic vs XGBoost)
  3. Map each classification to DSCP codepoints
  4. Count misclassifications and their downstream impact:
     - A video flow misclassified as bulk → gets CS1 (Bulk tin) instead of AF41 (Video tin)
     - In CAKE DiffServ4, Bulk tin gets lowest priority → latency increases
  5. Quantify: how many interactive packets would be wrongly deprioritized
"""

import os
import sys
import json
import time
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from classifier.runtime_classifier import FlowClassifier
from classifier.baseline_heuristic import classify_heuristic
from enforcement.dscp_marker import CLASS_TO_DSCP

# CAKE DiffServ4 tin priorities (lower = less priority)
CAKE_TIN_PRIORITY = {
    "CS1":  0,   # Bulk (lowest)
    "CS0":  1,   # Best Effort
    "AF41": 2,   # Video
    "EF":   3,   # Voice/Interactive (highest)
}

def get_dscp_for_class(traffic_class):
    info = CLASS_TO_DSCP.get(traffic_class, CLASS_TO_DSCP["default"])
    return info["name"]

def get_tin_priority(dscp_name):
    return CAKE_TIN_PRIORITY.get(dscp_name, 1)

def generate_test_workload(n_per_class=200):
    """
    Load test data from the actual training_data.csv with a proper train/test split.
    This ensures both classifiers are evaluated on the same distribution they were
    designed for — apples-to-apples comparison.
    """
    import pandas as pd
    from sklearn.model_selection import train_test_split

    csv_path = os.path.join(PROJECT_ROOT, "classifier", "training_data.csv")
    df = pd.read_csv(csv_path)

    # Use the same test split as training (30% held out, same random seed)
    _, test_df = train_test_split(df, test_size=0.30, random_state=42, stratify=df["label"])

    workload = []
    for _, row in test_df.iterrows():
        is_interactive = row["label"] in ("video_conference", "gaming")
        workload.append({
            "total_length": int(row["total_length"]),
            "ttl": int(row["ttl"]),
            "inter_arrival_ms": float(row["inter_arrival_ms"]),
            "ground_truth": row["label"],
            "latency_sensitive": is_interactive
        })

    # Shuffle for realism
    np.random.RandomState(42).shuffle(workload)
    return workload


def simulate_latency_impact(correct_tin, assigned_tin, is_interactive, ground_truth):
    """
    Estimate latency impact of wrong tin assignment in CAKE DiffServ4.
    
    Two types of QoS damage:
    1. DEPRIORITIZATION: Interactive packet sent to lower tin → it suffers extra delay
    2. OVER-PRIORITIZATION: Bulk packet sent to interactive tin → it contends with
       real interactive traffic, increasing THEIR latency (indirect damage)
    
    CAKE DiffServ4 tins:
      - Tin 0 (Bulk/CS1): lowest priority
      - Tin 1 (Best Effort/CS0): moderate
      - Tin 2 (Video/AF41): high priority
      - Tin 3 (Voice/EF): highest priority
    """
    if assigned_tin == correct_tin:
        return 0.0  # Correct assignment

    penalty_per_level = 150.0  # ms, based on CAKE paper bufferbloat measurements

    if is_interactive and assigned_tin < correct_tin:
        # Interactive packet deprioritized → direct latency increase
        levels_dropped = correct_tin - assigned_tin
        return levels_dropped * penalty_per_level

    if not is_interactive and assigned_tin > correct_tin:
        # Bulk packet over-prioritized → steals capacity from interactive tin
        # This causes indirect latency increase for real interactive flows
        levels_boosted = assigned_tin - correct_tin
        return levels_boosted * (penalty_per_level * 0.5)  # indirect effect

    return 0.0


def run_comparison():
    print("=" * 70)
    print("DOWNSTREAM QoS EFFECT: Classifier Accuracy → Latency Impact")
    print("=" * 70)

    # Load XGBoost model
    clf = FlowClassifier(os.path.join(PROJECT_ROOT, "classifier", "xgb_model.pkl"))
    workload = generate_test_workload(n_per_class=200)

    results = {"heuristic": [], "xgboost": []}

    for pkt in workload:
        gt = pkt["ground_truth"]
        correct_dscp = get_dscp_for_class(gt)
        correct_tin = get_tin_priority(correct_dscp)

        # --- Heuristic classification ---
        h_class = classify_heuristic(pkt["total_length"], pkt["inter_arrival_ms"])
        h_dscp = get_dscp_for_class(h_class)
        h_tin = get_tin_priority(h_dscp)
        h_penalty = simulate_latency_impact(correct_tin, h_tin, pkt["latency_sensitive"], gt)

        results["heuristic"].append({
            "ground_truth": gt,
            "predicted": h_class,
            "correct": h_class == gt,
            "assigned_dscp": h_dscp,
            "correct_dscp": correct_dscp,
            "latency_penalty_ms": h_penalty,
            "latency_sensitive": pkt["latency_sensitive"]
        })

        # --- XGBoost classification ---
        x_result = clf.predict_sample(
            pkt["total_length"], pkt["ttl"], pkt["inter_arrival_ms"]
        )
        x_class = x_result["class"]
        x_dscp = get_dscp_for_class(x_class)
        x_tin = get_tin_priority(x_dscp)
        x_penalty = simulate_latency_impact(correct_tin, x_tin, pkt["latency_sensitive"], gt)

        results["xgboost"].append({
            "ground_truth": gt,
            "predicted": x_class,
            "correct": x_class == gt,
            "assigned_dscp": x_dscp,
            "correct_dscp": correct_dscp,
            "latency_penalty_ms": x_penalty,
            "latency_sensitive": pkt["latency_sensitive"]
        })

    # === Compute aggregate metrics ===
    for name in ["heuristic", "xgboost"]:
        data = results[name]
        total = len(data)
        correct = sum(1 for d in data if d["correct"])
        accuracy = correct / total

        # Interactive packets (video + gaming) that were wrongly deprioritized
        interactive = [d for d in data if d["latency_sensitive"]]
        interactive_misclass = [d for d in interactive if not d["correct"]]
        interactive_wrong_tin = [d for d in interactive if d["latency_penalty_ms"] > 0]

        # Bulk packets wrongly sent to interactive tins (steals interactive capacity)
        bulk = [d for d in data if not d["latency_sensitive"]]
        bulk_overprioritized = [d for d in bulk if d["latency_penalty_ms"] > 0]

        avg_penalty_all = np.mean([d["latency_penalty_ms"] for d in data])
        avg_penalty_interactive = np.mean([d["latency_penalty_ms"] for d in interactive]) if interactive else 0

        # Worst case: interactive packets sent to bulk tin
        severe_misclass = [d for d in interactive if d["latency_penalty_ms"] >= 300]

        results[f"{name}_summary"] = {
            "accuracy": accuracy,
            "total_packets": total,
            "interactive_packets": len(interactive),
            "interactive_misclassified": len(interactive_misclass),
            "interactive_wrong_tin": len(interactive_wrong_tin),
            "bulk_overprioritized": len(bulk_overprioritized),
            "severe_deprioritized": len(severe_misclass),
            "avg_latency_penalty_ms": round(avg_penalty_all, 1),
            "avg_interactive_penalty_ms": round(avg_penalty_interactive, 1),
        }

    # === Print Results ===
    # Count by class
    class_counts = {}
    for p in workload:
        class_counts[p["ground_truth"]] = class_counts.get(p["ground_truth"], 0) + 1
    counts_str = " + ".join(f"{v} {k}" for k, v in sorted(class_counts.items()))
    print(f"\nWorkload: {len(workload)} packets from test split ({counts_str})\n")

    h = results["heuristic_summary"]
    x = results["xgboost_summary"]

    print(f"{'Metric':<45} {'Heuristic':>12} {'XGBoost':>12} {'Improvement':>14}")
    print("-" * 85)
    print(f"{'Classification Accuracy':<45} {h['accuracy']:>11.1%} {x['accuracy']:>11.1%} {(x['accuracy']-h['accuracy'])*100:>+12.1f}pp")
    print(f"{'Interactive Packets Misclassified':<45} {h['interactive_misclassified']:>12} {x['interactive_misclassified']:>12} {h['interactive_misclassified']-x['interactive_misclassified']:>+12d}")
    print(f"{'Interactive Packets in WRONG Tin':<45} {h['interactive_wrong_tin']:>12} {x['interactive_wrong_tin']:>12} {h['interactive_wrong_tin']-x['interactive_wrong_tin']:>+12d}")
    print(f"{'Bulk Packets OVER-Prioritized (→Voice Tin)':<45} {h['bulk_overprioritized']:>12} {x['bulk_overprioritized']:>12} {h['bulk_overprioritized']-x['bulk_overprioritized']:>+12d}")
    print(f"{'Severely Deprioritized (→Bulk Tin)':<45} {h['severe_deprioritized']:>12} {x['severe_deprioritized']:>12} {h['severe_deprioritized']-x['severe_deprioritized']:>+12d}")
    print(f"{'Avg Latency Penalty (all pkts, ms)':<45} {h['avg_latency_penalty_ms']:>12.1f} {x['avg_latency_penalty_ms']:>12.1f} {h['avg_latency_penalty_ms']-x['avg_latency_penalty_ms']:>+12.1f}")
    print(f"{'Avg Latency Penalty (interactive, ms)':<45} {h['avg_interactive_penalty_ms']:>12.1f} {x['avg_interactive_penalty_ms']:>12.1f} {h['avg_interactive_penalty_ms']-x['avg_interactive_penalty_ms']:>+12.1f}")

    print("\n" + "=" * 85)
    total_h = h['avg_latency_penalty_ms']
    total_x = x['avg_latency_penalty_ms']
    if total_x < total_h and total_h > 0:
        reduction = ((total_h - total_x) / total_h * 100)
        print(f"CONCLUSION: XGBoost reduces overall QoS damage by {reduction:.0f}% vs heuristic baseline.")
        print(f"  • Heuristic over-prioritizes {h['bulk_overprioritized']} bulk packets into Voice/Gaming")
        print(f"    tin → steals capacity from real interactive flows.")
        print(f"  • XGBoost: only {x['bulk_overprioritized']} bulk packet(s) over-prioritized.")
        print(f"  • Net effect: {total_h:.1f}ms avg penalty (heuristic) vs {total_x:.1f}ms (XGBoost).")
    elif total_h < total_x and total_x > 0:
        print(f"CONCLUSION: Heuristic has lower total penalty in this test.")
    else:
        print("CONCLUSION: Both classifiers achieve similar downstream QoS impact.")
    print("=" * 85)

    # Save JSON results
    output_path = os.path.join(PROJECT_ROOT, "experiments", "downstream_qos_results.json")
    with open(output_path, "w") as f:
        json.dump({
            "heuristic": results["heuristic_summary"],
            "xgboost": results["xgboost_summary"],
            "timestamp": time.time()
        }, f, indent=2)
    print(f"\nDetailed results saved to: {output_path}")


if __name__ == "__main__":
    run_comparison()
