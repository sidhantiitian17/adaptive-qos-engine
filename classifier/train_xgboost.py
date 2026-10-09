"""
NetMatrix-inspired feature set + XGBoost classifier.
Train/test split karke accuracy measure karte hain, 
baseline heuristic se compare karne ke liye.
"""
import os
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
import xgboost as xgb
import pickle

def train_and_evaluate(csv_path=None, model_out=None):
    if csv_path is None:
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "training_data.csv")
    if model_out is None:
        model_out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xgb_model.pkl")
    df = pd.read_csv(csv_path)

    # Features: total_length, ttl, inter_arrival_ms (NetMatrix style — payload kabhi nahi)
    X = df[["total_length", "ttl", "inter_arrival_ms"]]
    y = df["label"]

    # Labels ko numbers mein encode karo (XGBoost ko numeric chahiye)
    le = LabelEncoder()
    y_encoded = le.fit_transform(y)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_encoded, test_size=0.3, random_state=42, stratify=y_encoded
    )

    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=6,
        objective='multi:softmax',
        num_class=len(le.classes_),
        eval_metric='mlogloss'
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)

    print(f"=== XGBoost Accuracy: {accuracy:.3f} ===\n")
    print("Classification Report:")
    print(classification_report(y_test, y_pred, target_names=le.classes_))

    print("Confusion Matrix:")
    print(pd.DataFrame(
        confusion_matrix(y_test, y_pred),
        index=le.classes_, columns=le.classes_
    ))

    # Feature importance dekho (konsa feature sabse zyada kaam ka hai)
    print("\nFeature Importances:")
    for name, score in zip(X.columns, model.feature_importances_):
        print(f"  {name}: {score:.3f}")

    # Model save karo baad mein use karne ke liye
    with open(model_out, "wb") as f:
        pickle.dump({"model": model, "label_encoder": le}, f)
    print(f"\nModel saved to {model_out}")

    return accuracy

if __name__ == "__main__":
    train_and_evaluate()
