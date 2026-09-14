from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]

DATA = ROOT / "data" / "processed" / "failure_30d_dataset_v3.parquet"

OUTPUT = (
    ROOT
    / "ml"
    / "models"
    / "failure_30d_v3_expanding_backtest.csv"
)

FEATURES = [
    "condition_score",
    "degradation_rate",
    "measurement_value",
    "inspection_quality",
    "measurement_confidence",
    "previous_condition_score",
    "condition_change",
    "days_since_previous_measurement",
    "historical_mean_condition",
    "historical_min_condition",
    "historical_mean_degradation",
    "historical_observation_count",
    "design_life_years",
    "criticality_score",
    "asset_age_days",
    "defect_days_since_last",
    "defect_count_before",
    "inspection_days_since_last",
    "inspection_count_before",
    "maintenance_days_since_last",
    "maintenance_count_before",
    "incident_days_since_last",
    "incident_count_before",
]

TARGET = "failure_within_30_days"


def make_model() -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    max_iter=1000,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )


def evaluate_period(model, period: pd.DataFrame) -> dict:
    X = period[FEATURES]
    y = period[TARGET].astype(int).to_numpy()

    probabilities = model.predict_proba(X)[:, 1]

    n = len(period)
    failures = int(y.sum())

    ranked = period[
        ["asset_id", "prediction_timestamp", TARGET]
    ].copy()

    ranked["risk_probability"] = probabilities

    ranked = ranked.sort_values(
        "risk_probability",
        ascending=False,
    ).reset_index(drop=True)

    result = {
        "period": period["prediction_timestamp"].dt.to_period("M").iloc[0].strftime("%Y-%m"),
        "rows": n,
        "failures": failures,
        "failure_rate": failures / n if n else np.nan,
        "unique_assets": period["asset_id"].nunique(),
        "pr_auc": (
            average_precision_score(y, probabilities)
            if 0 < failures < n
            else np.nan
        ),
        "roc_auc": (
            roc_auc_score(y, probabilities)
            if 0 < failures < n
            else np.nan
        ),
    }

    for fraction in [0.01, 0.05, 0.10]:
        k = max(1, int(n * fraction))
        selected = ranked.head(k)
        captured = int(selected[TARGET].sum())

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
    print("RAIL-YOJNA V3 EXPANDING-WINDOW BACKTEST")
    print("=" * 80)

    df = pd.read_parquet(DATA)

    df["prediction_timestamp"] = pd.to_datetime(
        df["prediction_timestamp"],
        utc=True,
    )

    df = df.sort_values("prediction_timestamp").reset_index(drop=True)

    test = df[df["split"] == "test"].copy()

    periods = sorted(
        test["prediction_timestamp"]
        .dt.to_period("M")
        .astype(str)
        .unique()
    )

    results = []

    for period_name in periods:
        period_start = pd.Timestamp(
            f"{period_name}-01",
            tz="UTC",
        )

        next_period = period_start + pd.offsets.MonthBegin(1)

        evaluation = test[
            (test["prediction_timestamp"] >= period_start)
            & (test["prediction_timestamp"] < next_period)
        ].copy()

        if evaluation.empty:
            continue

        # 30-day label embargo.
        training_cutoff = period_start - pd.Timedelta(days=30)

        training = df[
            (df["prediction_timestamp"] < training_cutoff)
            & (
                df["split"].isin(
                    ["train", "validation", "test"]
                )
            )
        ].copy()

        # Do not train on observations with the same prediction timestamp
        # as the evaluation window or later.
        training = training[
            training["prediction_timestamp"] < training_cutoff
        ]

        if training.empty:
            print(f"{period_name}: no training data; skipped")
            continue

        print(
            f"\n{period_name}"
            f" | train={len(training):,}"
            f" | eval={len(evaluation):,}"
            f" | failures={int(evaluation[TARGET].sum())}"
        )

        model = make_model()

        model.fit(
            training[FEATURES],
            training[TARGET].astype(int),
        )

        result = evaluate_period(
            model,
            evaluation,
        )

        result["training_cutoff"] = training_cutoff
        result["training_rows"] = len(training)

        results.append(result)

    results = pd.DataFrame(results)

    print("\n" + "=" * 80)
    print("EXPANDING-WINDOW RESULTS")
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
