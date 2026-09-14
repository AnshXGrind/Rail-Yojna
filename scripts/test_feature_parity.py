from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from ml.inference.feature_builder import FeatureBuilder


ROOT = Path(__file__).resolve().parents[1]

FEATURE_FILE = (
    ROOT
    / "data"
    / "processed"
    / "failure_30d_features_v2.parquet"
)

MODEL_FILE = (
    ROOT
    / "ml"
    / "models"
    / "failure_30d_v2_logistic.joblib"
)


def main() -> None:
    import joblib

    artifact = joblib.load(MODEL_FILE)
    features = artifact["features"]

    training = pd.read_parquet(FEATURE_FILE)

    required = [
        "asset_id",
        "prediction_timestamp",
        *features,
    ]

    missing = [
        col
        for col in required
        if col not in training.columns
    ]

    if missing:
        raise RuntimeError(
            f"Training feature file is missing columns: {missing}"
        )

    # Use observations with complete current observation inputs.
    candidates = training.dropna(
        subset=[
            "condition_score",
            "degradation_rate",
            "measurement_value",
            "inspection_quality",
            "measurement_confidence",
        ]
    ).copy()

    # Include the known golden observation and a deterministic sample.
    golden_asset = "AST00015579"
    golden_time = pd.Timestamp(
        "2025-12-31T23:59:59Z"
    )

    golden = candidates[
        (candidates["asset_id"] == golden_asset)
        & (
            candidates["prediction_timestamp"]
            == golden_time
        )
    ]

    if golden.empty:
        raise RuntimeError(
            "Golden observation was not found."
        )

    sample = pd.concat(
        [
            golden.head(1),
            candidates.sample(
                n=min(24, len(candidates)),
                random_state=42,
            ),
        ],
        ignore_index=True,
    ).drop_duplicates(
        subset=[
            "asset_id",
            "prediction_timestamp",
        ]
    )

    builder = FeatureBuilder()

    failures = []

    print("=" * 72)
    print("TRAINING ↔ INFERENCE FEATURE PARITY")
    print("=" * 72)

    for _, row in sample.iterrows():
        inferred = builder.build(
            asset_id=row["asset_id"],
            timestamp=row["prediction_timestamp"],
            condition_score=float(row["condition_score"]),
            degradation_rate=float(row["degradation_rate"]),
            measurement_value=float(row["measurement_value"]),
            inspection_quality=float(row["inspection_quality"]),
            measurement_confidence=float(
                row["measurement_confidence"]
            ),
        )

        actual = inferred.iloc[0]

        for feature in features:
            expected = row[feature]
            observed = actual[feature]

            if pd.isna(expected) and pd.isna(observed):
                continue

            if pd.isna(expected) != pd.isna(observed):
                failures.append(
                    (
                        row["asset_id"],
                        row["prediction_timestamp"],
                        feature,
                        expected,
                        observed,
                        "NaN mismatch",
                    )
                )
                continue

            if not np.isclose(
                float(expected),
                float(observed),
                rtol=1e-7,
                atol=1e-7,
            ):
                failures.append(
                    (
                        row["asset_id"],
                        row["prediction_timestamp"],
                        feature,
                        expected,
                        observed,
                        "value mismatch",
                    )
                )

    checked = len(sample)

    print(f"Observations checked : {checked}")
    print(f"Features per row     : {len(features)}")
    print(f"Comparisons          : {checked * len(features)}")
    print(f"Mismatches           : {len(failures)}")

    if failures:
        print()
        print("FIRST MISMATCHES:")
        for item in failures[:20]:
            print(item)

        raise SystemExit(1)

    print()
    print("PARITY CHECK PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
