from __future__ import annotations

from pathlib import Path

import pandas as pd
import joblib


ROOT = Path(__file__).resolve().parents[1]

FEATURE_FILE = (
    ROOT
    / "data"
    / "processed"
    / "failure_30d_features_v2.parquet"
)

TARGET_FILE = (
    ROOT
    / "data"
    / "processed"
    / "failure_30d_target_v3.parquet"
)

MODEL_FILE = (
    ROOT
    / "ml"
    / "models"
    / "failure_30d_v2_logistic.joblib"
)

OUTPUT_FILE = (
    ROOT
    / "data"
    / "processed"
    / "failure_30d_dataset_v3.parquet"
)

KEYS = [
    "asset_id",
    "prediction_timestamp",
]

TARGET = "failure_within_30_days"


def main() -> None:
    print("=" * 72)
    print("RAIL-YOJNA V3 DATASET ASSEMBLY")
    print("=" * 72)

    print("\nLoading feature dataset...")
    features = pd.read_parquet(FEATURE_FILE)

    print(f"Feature rows: {len(features):,}")

    print("\nLoading V3 target...")
    target = pd.read_parquet(TARGET_FILE)

    print(f"Target rows: {len(target):,}")

    # ---------------------------------------------------------
    # Normalize timestamps
    # ---------------------------------------------------------
    features["prediction_timestamp"] = pd.to_datetime(
        features["prediction_timestamp"],
        format="mixed",
        errors="coerce",
        utc=True,
    )

    target["prediction_timestamp"] = pd.to_datetime(
        target["prediction_timestamp"],
        format="mixed",
        errors="coerce",
        utc=True,
    )

    # ---------------------------------------------------------
    # Validate keys
    # ---------------------------------------------------------
    for name, frame in [
        ("features", features),
        ("target", target),
    ]:
        null_keys = frame[KEYS].isna().any(axis=1).sum()

        if null_keys:
            raise RuntimeError(
                f"{name} contains {null_keys} rows "
                "with null alignment keys."
            )

        duplicates = frame.duplicated(
            subset=KEYS
        ).sum()

        if duplicates:
            raise RuntimeError(
                f"{name} contains {duplicates} "
                "duplicate alignment rows."
            )

    print("\nKey validation: PASSED")

    # ---------------------------------------------------------
    # Exact key coverage
    # ---------------------------------------------------------
    feature_keys = pd.MultiIndex.from_frame(
        features[KEYS]
    )

    target_keys = pd.MultiIndex.from_frame(
        target[KEYS]
    )

    missing_in_target = feature_keys.difference(
        target_keys
    )

    missing_in_features = target_keys.difference(
        feature_keys
    )

    if len(missing_in_target):
        raise RuntimeError(
            f"{len(missing_in_target)} feature rows "
            "have no matching V3 target."
        )

    if len(missing_in_features):
        raise RuntimeError(
            f"{len(missing_in_features)} V3 target rows "
            "have no matching feature row."
        )

    print("Exact key coverage: PASSED")

    # ---------------------------------------------------------
    # Important: compare old V2 target with canonical V3 target
    # ---------------------------------------------------------
    if TARGET in features.columns:
        print(
            "\nExisting V2 target found in feature dataset."
        )
        print(
            "Comparing V2 target against canonical V3 target..."
        )

        comparison = features[
            KEYS + [TARGET]
        ].merge(
            target[
                KEYS + [TARGET]
            ],
            on=KEYS,
            how="inner",
            validate="one_to_one",
            suffixes=("_v2", "_v3"),
        )

        comparison["target_match"] = (
            comparison[f"{TARGET}_v2"]
            == comparison[f"{TARGET}_v3"]
        )

        mismatches = int(
            (~comparison["target_match"]).sum()
        )

        print(
            f"Target rows compared : {len(comparison):,}"
        )
        print(
            f"Target mismatches    : {mismatches:,}"
        )

        if mismatches:
            print("\nFIRST TARGET MISMATCHES:")
            print(
                comparison[
                    ~comparison["target_match"]
                ].head(20).to_string(index=False)
            )

            raise RuntimeError(
                "V2 and canonical V3 targets differ. "
                "Refusing to silently replace the target."
            )

        print(
            "V2 ↔ V3 target equality: PASSED"
        )

        # Remove old target before adding canonical target.
        features = features.drop(
            columns=[TARGET]
        )

    # ---------------------------------------------------------
    # Add canonical V3 target
    # ---------------------------------------------------------
    target_small = target[
        KEYS + [TARGET]
    ].copy()

    dataset = features.merge(
        target_small,
        on=KEYS,
        how="inner",
        validate="one_to_one",
    )

    if len(dataset) != len(features):
        raise RuntimeError(
            "Merged dataset row count differs "
            "from feature dataset."
        )

    # ---------------------------------------------------------
    # Validate target
    # ---------------------------------------------------------
    unique_target = sorted(
        dataset[TARGET]
        .dropna()
        .unique()
        .tolist()
    )

    if unique_target != [0, 1]:
        raise RuntimeError(
            f"Unexpected target values: {unique_target}"
        )

    # ---------------------------------------------------------
    # Validate model features
    # ---------------------------------------------------------
    artifact = joblib.load(MODEL_FILE)
    model_features = artifact["features"]

    missing_features = [
        feature
        for feature in model_features
        if feature not in dataset.columns
    ]

    if missing_features:
        raise RuntimeError(
            f"Missing model features: {missing_features}"
        )

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------
    positives = int(
        dataset[TARGET].sum()
    )

    print()
    print("-" * 72)
    print("V3 DATASET SUMMARY")
    print("-" * 72)

    print(
        f"Rows               : {len(dataset):,}"
    )

    print(
        f"Columns            : {len(dataset.columns)}"
    )

    print(
        f"Model features     : {len(model_features)}"
    )

    print(
        f"Positive labels    : {positives:,}"
    )

    print(
        f"Positive rate      : "
        f"{dataset[TARGET].mean():.4%}"
    )

    print(
        f"Timestamp min      : "
        f"{dataset['prediction_timestamp'].min()}"
    )

    print(
        f"Timestamp max      : "
        f"{dataset['prediction_timestamp'].max()}"
    )

    # ---------------------------------------------------------
    # Save
    # ---------------------------------------------------------
    dataset.to_parquet(
        OUTPUT_FILE,
        index=False,
    )

    print()
    print(
        f"Saved: {OUTPUT_FILE}"
    )

    print()
    print("=" * 72)
    print("V3 DATASET ASSEMBLY PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
