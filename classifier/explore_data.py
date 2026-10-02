import pandas as pd

df = pd.read_csv("training_data.csv")

print("=== Dataset Shape ===")
print(df.shape)

print("\n=== Per-Label Stats ===")
print(df.groupby("label")[["total_length", "ttl", "inter_arrival_ms"]].describe())

print("\n=== Sample Rows ===")
print(df.sample(10))
