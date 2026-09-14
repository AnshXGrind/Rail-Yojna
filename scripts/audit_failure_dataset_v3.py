from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import joblib


ROOT = Path(__file__).resolve().parents[1]

DATASET = (
    ROOT
    / "data"
    / "processed"
    / "failure_30d_dataset_v3.parquet"
)

MODEL = (
    ROOT
    / "ml"
    / "models"
    / "failure_30d_v2_logistic.joblib"
)

OUTPUT = (
    ROOT
    / "data"
    / "validation"
    / "failure_30d_v3_leakage_audit.csv"
)


def main() -> None:
    print("=" * 72)
    print("RAIL-YOJNA V3 LEAKAGE AUDIT")
    print("=" * 72)

    df = pd.read_parquet(DATASET)

    artifact = joblib.load(MODEL)
    features = artifact["features"]

    print()
    print(f"Rows       : {len(df):,}")
    print(f"Features   : {len(features)}")
    print(
        f"Time range : {df['prediction_timestamp'].min()} "
        f"-> {df['prediction_timestamp'].max()}"
    )

    checks = []

    # ---------------------------------------------------------
    # Basic dataset integrity
    # ---------------------------------------------------------
    checks.append(
        {
            "check": "row_count",
            "value": len(df),
            "status": "PASS" if len(df) == 600_000 else "WARN",
        }
    )

    duplicate_keys = df.duplicated(
        subset=[
            "asset_id",
            "prediction_timestamp",
        ]
    ).sum()

    checks.append(
        {
            "check": "duplicate_prediction_keys",
            "value": int(duplicate_keys),
            "status": (
                "PASS"
                if duplicate_keys == 0
                else "FAIL"
            ),
        }
    )

    # ---------------------------------------------------------
    # Target integrity
    # ---------------------------------------------------------
    invalid_target = (
        ~df["failure_within_30_days"]
        .isin([0, 1])
    ).sum()

    checks.append(
        {
            "check": "invalid_target_values",
            "value": int(invalid_target),
            "status": (
                "PASS"
                if invalid_target == 0
                else "FAIL"
            ),
        }
    )

    # ---------------------------------------------------------
    # Feature existence
    # ---------------------------------------------------------
    missing_features = [
        f for f in features
        if f not in df.columns
    ]

    checks.append(
        {
            "check": "missing_model_features",
            "value": len(missing_features),
            "status": (
                "PASS"
                if not missing_features
                else "FAIL"
            ),
        }
    )

    if missing_features:
        print(
            "\nMissing features:",
            missing_features,
        )
        raise SystemExit(1)

    # ---------------------------------------------------------
    # Explicit future-information checks
    # ---------------------------------------------------------

    # These features should never be negative.
    nonnegative_features = [
        "days_since_previous_measurement",
        "historical_observation_count",
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

    for feature in nonnegative_features:
        values = pd.to_numeric(
            df[feature],
            errors="coerce",
        )

        negative_count = int(
            (values < 0).sum()
        )

        checks.append(
            {
                "check": f"{feature}_nonnegative",
                "value": negative_count,
                "status": (
                    "PASS"
                    if negative_count == 0
                    else "FAIL"
                ),
            }
        )

    # ---------------------------------------------------------
    # Asset age cannot be negative
    # ---------------------------------------------------------
    asset_age = pd.to_numeric(
        df["asset_age_days"],
        errors="coerce",
    )

    negative_age = int(
        (asset_age < 0).sum()
    )

    checks.append(
        {
            "check": "asset_age_not_future",
            "value": negative_age,
            "status": (
                "PASS"
                if negative_age == 0
                else "FAIL"
            ),
        }
    )

    # ---------------------------------------------------------
    # Historical counts must be integers
    # ---------------------------------------------------------
    count_features = [
        "historical_observation_count",
        "defect_count_before",
        "inspection_count_before",
        "maintenance_count_before",
        "incident_count_before",
    ]

    for feature in count_features:
        values = pd.to_numeric(
            df[feature],
            errors="coerce",
        ).dropna()

        fractional = int(
            (~np.isclose(values, np.round(values))).sum()
        )

        checks.append(
            {
                "check": f"{feature}_integer",
                "value": fractional,
                "status": (
                    "PASS"
                    if fractional == 0
                    else "FAIL"
                ),
            }
        )

    # ---------------------------------------------------------
    # Condition-history consistency
    # ---------------------------------------------------------
    condition_check = df[
        [
            "condition_score",
            "previous_condition_score",
            "condition_change",
        ]
    ].dropna()

    expected_change = (
        condition_check["condition_score"]
        - condition_check["previous_condition_score"]
    )

    change_error = int(
        (~np.isclose(
            expected_change,
            condition_check["condition_change"],
            rtol=1e-7,
            atol=1e-7,
        )).sum()
    )

    checks.append(
        {
            "check": "condition_change_consistency",
            "value": change_error,
            "status": (
                "PASS"
                if change_error == 0
                else "FAIL"
            ),
        }
    )

    # ---------------------------------------------------------
    # Target prevalence
    # ---------------------------------------------------------
    positives = int(
        df["failure_within_30_days"].sum()
    )

    checks.append(
        {
            "check": "positive_labels",
            "value": positives,
            "status": "PASS",
        }
    )

    # ---------------------------------------------------------
    # Save audit
    # ---------------------------------------------------------
    audit = pd.DataFrame(checks)

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit.to_csv(
        OUTPUT,
        index=False,
    )

    print()
    print("-" * 72)
    print("LEAKAGE / INTEGRITY AUDIT")
    print("-" * 72)

    print(
        audit.to_string(index=False)
    )

    failed = audit[
        audit["status"] == "FAIL"
    ]

    print()
    print(
        f"Checks run : {len(audit)}"
    )
    print(
        f"Failures   : {len(failed)}"
    )

    print()
    print(
        f"Saved: {OUTPUT}"
    )

    if not failed.empty:
        raise SystemExit(
            "V3 leakage/integrity audit FAILED."
        )

    print()
    print("=" * 72)
    print("V3 LEAKAGE / INTEGRITY AUDIT PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
