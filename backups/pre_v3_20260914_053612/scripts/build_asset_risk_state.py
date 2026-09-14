from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

DATA = (
    ROOT
    / "data"
    / "processed"
    / "failure_30d_features_v2.parquet"
)

MODEL = (
    ROOT
    / "ml"
    / "models"
    / "failure_30d_v2_logistic.joblib"
)

CALIBRATOR = (
    ROOT
    / "ml"
    / "models"
    / "failure_30d_probability_calibrator.joblib"
)

OUTPUT = ROOT / "ml" / "models"

OUTPUT.mkdir(parents=True, exist_ok=True)


def main():
    df = pd.read_parquet(DATA)

    bundle = joblib.load(MODEL)
    model = bundle["model"]
    features = bundle["features"]

    calibrator = joblib.load(CALIBRATOR)

    test = df[
        df["split"] == "test"
    ].copy()

    test["raw_risk"] = model.predict_proba(
        test[features]
    )[:, 1]

    # Apply exactly the same calibration used during evaluation.
    test["calibrated_risk"] = (
        calibrator.predict_proba(
            _safe_logit(
                test["raw_risk"]
            ).reshape(-1, 1)
        )[:, 1]
    )

    # Latest observation for each asset.
    test = test.sort_values(
        [
            "asset_id",
            "prediction_timestamp",
        ]
    )

    latest = (
        test.groupby(
            "asset_id",
            as_index=False,
        )
        .tail(1)
        .copy()
    )

    latest = latest[
        [
            "asset_id",
            "prediction_timestamp",
            "condition_score",
            "degradation_rate",
            "asset_age_days",
            "criticality_score",
            "defect_count_before",
            "inspection_count_before",
            "maintenance_count_before",
            "incident_count_before",
            "raw_risk",
            "calibrated_risk",
        ]
    ]

    latest = latest.sort_values(
        "calibrated_risk",
        ascending=False,
    ).reset_index(drop=True)

    output = (
        OUTPUT
        / "asset_risk_state_test.parquet"
    )

    latest.to_parquet(
        output,
        index=False,
    )

    print("=" * 80)
    print("ASSET RISK STATE")
    print("=" * 80)

    print(
        f"Assets evaluated: {len(latest):,}"
    )

    print("\nHighest-risk assets:")
    print(
        latest.head(20).to_string(
            index=False
        )
    )

    print("\nSaved:")
    print(output)


def _safe_logit(probabilities):
    p = probabilities.clip(
        lower=1e-8,
        upper=1 - 1e-8,
    )

    return (p / (1 - p)).apply(
        lambda x: __import__("math").log(x)
    ).to_numpy()


if __name__ == "__main__":
    main()
