from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
)


ROOT = Path(__file__).resolve().parents[1]

DATA = (
    ROOT
    / "data"
    / "processed"
    / "failure_30d_dataset_v3.parquet"
)

MODEL = (
    ROOT
    / "ml"
    / "models"
    / "failure_30d_v3_logistic.joblib"
)

OUTPUT = (
    ROOT
    / "ml"
    / "models"
    / "failure_30d_v3_backtest.csv"
)


def evaluate_period(
    period: pd.DataFrame,
    features: list[str],
    model,
) -> dict:

    X = period[features]
    y = period["failure_within_30_days"].astype(int).to_numpy()

    probabilities = model.predict_proba(X)[:, 1]

    n = len(period)
    failures = int(y.sum())

    result = {
        "period_start": period["prediction_timestamp"].min(),
        "period_end": period["prediction_timestamp"].max(),
        "rows": n,
        "failures": failures,
        "failure_rate": failures / n if n else 0.0,
        "unique_assets": period["asset_id"].nunique(),
        "pr_auc": (
            average_precision_score(y, probabilities)
            if failures > 0
            else np.nan
        ),
        "roc_auc": (
            roc_auc_score(y, probabilities)
            if failures > 0 and failures < n
            else np.nan
        ),
    }

    ranked = period[
        [
            "asset_id",
            "prediction_timestamp",
            "failure_within_30_days",
        ]
    ].copy()

    ranked["risk_probability"] = probabilities

    ranked = ranked.sort_values(
        "risk_probability",
        ascending=False,
    ).reset_index(drop=True)

    for fraction in [0.01, 0.05, 0.10]:

        k = max(1, int(n * fraction))

        selected = ranked.head(k)

        captured = int(
            selected["failure_within_30_days"].sum()
        )

        result[f"top_{int(fraction * 100)}pct_precision"] = (
            captured / k
        )

        result[f"top_{int(fraction * 100)}pct_recall"] = (
            captured / failures
            if failures
            else np.nan
        )

    return result


def main():

    print("=" * 80)
    print("RAIL-YOJNA V3 TEMPORAL BACKTEST")
    print("=" * 80)

    print("\nLoading dataset...")
    df = pd.read_parquet(DATA)

    print(f"Rows: {len(df):,}")

    bundle = joblib.load(MODEL)

    model = bundle["model"]
    features = bundle["features"]

    test = df[df["split"] == "test"].copy()

    test["prediction_timestamp"] = pd.to_datetime(
        test["prediction_timestamp"],
        utc=True,
    )

    print(f"Test rows: {len(test):,}")
    print(
        "Test period:",
        test["prediction_timestamp"].min(),
        "->",
        test["prediction_timestamp"].max(),
    )

    # Six chronological windows across the held-out test period.
    test["period"] = (
        test["prediction_timestamp"]
        .dt.to_period("M")
        .astype(str)
    )

    periods = sorted(test["period"].unique())

    rows = []

    for period_name in periods:

        period = test[
            test["period"] == period_name
        ].copy()

        result = evaluate_period(
            period,
            features,
            model,
        )

        result["period"] = period_name

        rows.append(result)

    results = pd.DataFrame(rows)

    results = results[
        [
            "period",
            "period_start",
            "period_end",
            "rows",
            "failures",
            "failure_rate",
            "unique_assets",
            "pr_auc",
            "roc_auc",
            "top_1pct_precision",
            "top_1pct_recall",
            "top_5pct_precision",
            "top_5pct_recall",
            "top_10pct_precision",
            "top_10pct_recall",
        ]
    ]

    print("\n" + "=" * 80)
    print("MONTHLY TEMPORAL BACKTEST")
    print("=" * 80)

    print(
        results.to_string(
            index=False,
            formatters={
                "failure_rate": "{:.3%}".format,
                "pr_auc": "{:.6f}".format,
                "roc_auc": "{:.6f}".format,
                "top_1pct_precision": "{:.2%}".format,
                "top_1pct_recall": "{:.2%}".format,
                "top_5pct_precision": "{:.2%}".format,
                "top_5pct_recall": "{:.2%}".format,
                "top_10pct_precision": "{:.2%}".format,
                "top_10pct_recall": "{:.2%}".format,
            },
        )
    )

    results.to_csv(
        OUTPUT,
        index=False,
    )

    print("\nSaved:")
    print(OUTPUT)


if __name__ == "__main__":
    main()
