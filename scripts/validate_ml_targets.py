from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "raw" / "rail_yojna_data"
OUTPUT = ROOT / "data" / "validation"

OUTPUT.mkdir(parents=True, exist_ok=True)

HORIZON_DAYS = 30


def read_parquet(table: str, columns: list[str]) -> pd.DataFrame:
    return pd.read_parquet(
        DATASET / f"{table}.parquet",
        columns=columns,
    )


def check_required_columns(
    table: str,
    columns: list[str],
) -> None:
    schema = pq.read_schema(
        DATASET / f"{table}.parquet"
    )

    missing = [
        column
        for column in columns
        if column not in schema.names
    ]

    if missing:
        raise RuntimeError(
            f"{table}: missing columns: {missing}"
        )


def load_observations() -> pd.DataFrame:
    check_required_columns(
        "asset_condition_history",
        ["measurement_id", "asset_id", "timestamp"],
    )

    df = read_parquet(
        "asset_condition_history",
        [
            "measurement_id",
            "asset_id",
            "timestamp",
            "condition_score",
            "degradation_rate",
            "measurement_type",
            "measurement_value",
            "measurement_unit",
            "inspection_quality",
            "measurement_confidence",
        ],
    )

    df["prediction_timestamp"] = pd.to_datetime(
        df["timestamp"],
        format="mixed",
        errors="coerce",
        utc=True,
    )

    return df


def load_failure_events() -> pd.DataFrame:
    # ---------------------------------------------------------
    # Incident-based failure events
    # ---------------------------------------------------------
    check_required_columns(
        "incidents",
        ["incident_id", "timestamp", "asset_id"],
    )

    incidents = read_parquet(
        "incidents",
        [
            "incident_id",
            "timestamp",
            "asset_id",
        ],
    ).copy()

    incidents["failure_timestamp"] = pd.to_datetime(
        incidents["timestamp"],
        format="mixed",
        errors="coerce",
        utc=True,
    )

    incidents = incidents[
        incidents["asset_id"].notna()
        & incidents["failure_timestamp"].notna()
    ].copy()

    incidents = incidents[
        [
            "incident_id",
            "asset_id",
            "failure_timestamp",
        ]
    ]

    incidents["failure_source"] = "incident"

    # ---------------------------------------------------------
    # Emergency-maintenance failure events
    # ---------------------------------------------------------
    check_required_columns(
        "emergency_maintenance",
        [
            "emergency_id",
            "asset_id",
            "failure_time",
        ],
    )

    emergency = read_parquet(
        "emergency_maintenance",
        [
            "emergency_id",
            "asset_id",
            "failure_time",
        ],
    ).copy()

    emergency["failure_timestamp"] = pd.to_datetime(
        emergency["failure_time"],
        format="mixed",
        errors="coerce",
        utc=True,
    )

    emergency = emergency[
        emergency["asset_id"].notna()
        & emergency["failure_timestamp"].notna()
    ].copy()

    # Use emergency_id as the event identifier.
    emergency = emergency[
        [
            "emergency_id",
            "asset_id",
            "failure_timestamp",
        ]
    ].rename(
        columns={
            "emergency_id": "incident_id"
        }
    )

    emergency["failure_source"] = "emergency_maintenance"

    # ---------------------------------------------------------
    # Force identical, unique schemas
    # ---------------------------------------------------------
    columns = [
        "incident_id",
        "asset_id",
        "failure_timestamp",
        "failure_source",
    ]

    incidents = incidents[columns].copy()
    emergency = emergency[columns].copy()

    assert incidents.columns.is_unique
    assert emergency.columns.is_unique

    events = pd.concat(
        [incidents, emergency],
        ignore_index=True,
    )

    # The same failure may be represented in both tables.
    events = events.drop_duplicates(
        subset=[
            "asset_id",
            "failure_timestamp",
        ]
    )

    return (
        events
        .sort_values(
            ["asset_id", "failure_timestamp"]
        )
        .reset_index(drop=True)
    )

def build_30_day_labels(
    observations: pd.DataFrame,
    failures: pd.DataFrame,
) -> pd.DataFrame:

    observations = observations.copy()
    failures = failures.copy()

    observations = observations.sort_values(
        ["asset_id", "prediction_timestamp"]
    )

    failures = failures.sort_values(
        ["asset_id", "failure_timestamp"]
    )

    labels = []

    # Process one asset at a time. This avoids an enormous
    # Cartesian merge across all observations and failures.
    failure_groups = {
        asset_id: group["failure_timestamp"].tolist()
        for asset_id, group
        in failures.groupby("asset_id")
    }

    for asset_id, group in observations.groupby("asset_id"):
        event_times = failure_groups.get(asset_id, [])

        for _, row in group.iterrows():
            timestamp = row["prediction_timestamp"]

            if pd.isna(timestamp):
                labels.append(0)
                continue

            horizon = timestamp + pd.Timedelta(
                days=HORIZON_DAYS
            )

            label = int(
                any(
                    timestamp < failure_time <= horizon
                    for failure_time in event_times
                )
            )

            labels.append(label)

    observations["failure_within_30_days"] = labels

    return observations


def validate_target_dataset(
    labeled: pd.DataFrame,
    failures: pd.DataFrame,
) -> pd.DataFrame:

    results = []

    invalid_timestamp = int(
        labeled["prediction_timestamp"].isna().sum()
    )

    results.append({
        "check": "valid_prediction_timestamp",
        "violations": invalid_timestamp,
        "status": (
            "PASS"
            if invalid_timestamp == 0
            else "FAIL"
        ),
    })

    missing_assets = int(
        labeled["asset_id"].isna().sum()
    )

    results.append({
        "check": "observation_asset_id_present",
        "violations": missing_assets,
        "status": (
            "PASS"
            if missing_assets == 0
            else "FAIL"
        ),
    })

    invalid_failure_asset = int(
        failures["asset_id"].isna().sum()
    )

    results.append({
        "check": "failure_asset_id_present",
        "violations": invalid_failure_asset,
        "status": (
            "PASS"
            if invalid_failure_asset == 0
            else "FAIL"
        ),
    })

    positive = int(
        labeled["failure_within_30_days"].sum()
    )

    total = len(labeled)

    results.append({
        "check": "positive_class_count",
        "violations": 0,
        "value": positive,
        "status": "PASS",
    })

    results.append({
        "check": "negative_class_count",
        "violations": 0,
        "value": total - positive,
        "status": "PASS",
    })

    results.append({
        "check": "positive_class_rate",
        "violations": 0,
        "value": (
            positive / total
            if total
            else 0
        ),
        "status": "PASS",
    })

    # Every positive label must have a future failure event
    # inside the 30-day window. Sample-check the generated
    # labels against the event table.
    sample = labeled[
        labeled["failure_within_30_days"] == 1
    ].head(5000)

    failure_map = {
        asset_id: group["failure_timestamp"].tolist()
        for asset_id, group
        in failures.groupby("asset_id")
    }

    false_positive_labels = 0

    for _, row in sample.iterrows():
        times = failure_map.get(row["asset_id"], [])
        t = row["prediction_timestamp"]
        end = t + pd.Timedelta(days=HORIZON_DAYS)

        exists = any(
            t < failure_time <= end
            for failure_time in times
        )

        if not exists:
            false_positive_labels += 1

    results.append({
        "check": "positive_label_semantic_check",
        "violations": false_positive_labels,
        "status": (
            "PASS"
            if false_positive_labels == 0
            else "FAIL"
        ),
    })

    return pd.DataFrame(results)


def create_time_split(
    labeled: pd.DataFrame,
) -> pd.DataFrame:

    df = labeled.sort_values(
        "prediction_timestamp"
    ).copy()

    timestamps = df["prediction_timestamp"]

    train_cutoff = timestamps.quantile(0.70)
    validation_cutoff = timestamps.quantile(0.85)

    df["split"] = "test"

    df.loc[
        timestamps <= train_cutoff,
        "split"
    ] = "train"

    df.loc[
        (timestamps > train_cutoff)
        & (timestamps <= validation_cutoff),
        "split"
    ] = "validation"

    return df


def main() -> None:

    print("=" * 70)
    print("RAIL-YOJNA ML TARGET VALIDATION")
    print("=" * 70)

    print("\nLoading observations...")
    observations = load_observations()

    print(
        f"Observations: {len(observations):,}"
    )

    print("\nLoading failure events...")
    failures = load_failure_events()

    print(
        f"Failure events: {len(failures):,}"
    )

    print("\nBuilding 30-day labels...")
    labeled = build_30_day_labels(
        observations,
        failures,
    )

    print("\nCreating temporal split...")
    labeled = create_time_split(labeled)

    print("\nValidating target...")
    validation = validate_target_dataset(
        labeled,
        failures,
    )

    validation.to_csv(
        OUTPUT / "ml_target_validation.csv",
        index=False,
    )

    # Save a small preview for manual inspection.
    labeled.head(10000).to_parquet(
        OUTPUT / "failure_within_30_days_preview.parquet",
        index=False,
    )

    # Dataset statistics.
    class_counts = (
        labeled["failure_within_30_days"]
        .value_counts()
        .sort_index()
    )

    split_stats = (
        labeled.groupby(
            ["split", "failure_within_30_days"]
        )
        .size()
        .reset_index(name="rows")
    )

    split_stats.to_csv(
        OUTPUT / "ml_target_split_stats.csv",
        index=False,
    )

    print("\n" + "=" * 70)
    print("TARGET SUMMARY")
    print("=" * 70)

    print(
        f"Total observations : {len(labeled):,}"
    )

    print(
        f"Positive labels    : "
        f"{int(class_counts.get(1, 0)):,}"
    )

    print(
        f"Negative labels    : "
        f"{int(class_counts.get(0, 0)):,}"
    )

    print(
        f"Positive rate      : "
        f"{labeled['failure_within_30_days'].mean():.4%}"
    )

    print("\nTime split:")
    print(
        labeled["split"]
        .value_counts()
        .to_string()
    )

    print("\nValidation:")
    print(validation.to_string(index=False))

    failed = validation[
        validation["status"] == "FAIL"
    ]

    print(
        f"\nValidation failures: {len(failed)}"
    )

    print("\nGenerated:")
    print(
        "  data/validation/ml_target_validation.csv"
    )
    print(
        "  data/validation/ml_target_split_stats.csv"
    )
    print(
        "  data/validation/failure_within_30_days_preview.parquet"
    )


if __name__ == "__main__":
    main()
