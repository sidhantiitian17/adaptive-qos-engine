"""
Simple rule-based classifier — PDF ka 'deterministic baseline' requirement.
Sirf packet-size aur inter-arrival-time ke thresholds use karta hai, 
koi training/learning nahi.
"""
import os
import pandas as pd

def classify_heuristic(total_length, inter_arrival_ms):
    """
    Simple rules (humare synthetic traffic generators ke design se derived):
    - gaming: bahut chhote packets (~60-100 bytes), chhota inter-arrival
    - video_conference: medium packets (~200-300 bytes), consistent inter-arrival
    - bulk_download: bade packets (~1400+ bytes, MTU ke close)
    """
    if total_length < 100:
        return "gaming"
    elif total_length < 500:
        return "video_conference"
    else:
        return "bulk_download"

def evaluate_heuristic(csv_path=None):
    if csv_path is None:
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "training_data.csv")
    df = pd.read_csv(csv_path)
    df["predicted"] = df.apply(
        lambda row: classify_heuristic(row["total_length"], row["inter_arrival_ms"]), axis=1
    )
    accuracy = (df["predicted"] == df["label"]).mean()
    print(f"=== Heuristic Baseline Accuracy: {accuracy:.3f} ===")

    print("\nConfusion-style breakdown:")
    print(pd.crosstab(df["label"], df["predicted"]))

    return accuracy

if __name__ == "__main__":
    evaluate_heuristic()
