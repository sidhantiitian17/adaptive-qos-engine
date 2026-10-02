"""
Final comparison: Heuristic baseline vs XGBoost AI model.
Ye output seedha report/slide mein use hoga.
"""
from baseline_heuristic import evaluate_heuristic
from train_xgboost import train_and_evaluate

print("=" * 50)
print("BASELINE (Deterministic Heuristic)")
print("=" * 50)
baseline_acc = evaluate_heuristic()

print("\n" + "=" * 50)
print("AI MODEL (XGBoost)")
print("=" * 50)
xgb_acc = train_and_evaluate()

print("\n" + "=" * 50)
print("FINAL COMPARISON")
print("=" * 50)
print(f"Heuristic Baseline Accuracy : {baseline_acc:.3f}")
print(f"XGBoost AI Accuracy         : {xgb_acc:.3f}")
print(f"Improvement                 : {(xgb_acc - baseline_acc)*100:.1f} percentage points")
