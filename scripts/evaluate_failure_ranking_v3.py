from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

DATA = ROOT / "data" / "processed" / "failure_30d_dataset_v3.parquet"
MODEL = ROOT / "ml" / "models" / "failure_30d_v3_logistic.joblib"

df = pd.read_parquet(DATA)

bundle = joblib.load(MODEL)
model = bundle["model"]
features = bundle["features"]

test = df[df["split"] == "test"].copy()

X = test[features]
y = test["failure_within_30_days"]

test["risk_probability"] = model.predict_proba(X)[:, 1]

test = test.sort_values(
    "risk_probability",
    ascending=False,
).reset_index(drop=True)

total_failures = int(y.sum())
n = len(test)

rows = []

for fraction in [0.005, 0.01, 0.02, 0.05, 0.10]:

    k = max(1, int(n * fraction))

    selected = test.head(k)

    captured = int(
        selected["failure_within_30_days"].sum()
    )

    precision = (
        captured / k
        if k
        else 0
    )

    recall = (
        captured / total_failures
        if total_failures
        else 0
    )

    rows.append({
        "top_fraction": fraction,
        "observations_flagged": k,
        "failures_captured": captured,
        "precision": precision,
        "recall": recall,
        "mean_risk_flagged": selected[
            "risk_probability"
        ].mean(),
    })

results = pd.DataFrame(rows)

print("=" * 80)
print("FAILURE RISK RANKING")
print("=" * 80)

print(
    results.to_string(
        index=False,
        formatters={
            "top_fraction": "{:.1%}".format,
            "precision": "{:.2%}".format,
            "recall": "{:.2%}".format,
            "mean_risk_flagged": "{:.4f}".format,
        },
    )
)

output = ROOT / "ml" / "models" / "failure_30d_v3_ranking_results.csv"

results.to_csv(
    output,
    index=False,
)

print("\nSaved:")
print(output)

print("\nHighest-risk 20 observations:")
print(
    test[
        [
            "asset_id",
            "prediction_timestamp",
            "risk_probability",
            "failure_within_30_days",
        ]
    ]
    .head(20)
    .to_string(index=False)
)
