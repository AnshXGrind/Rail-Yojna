from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "raw" / "rail_yojna_data"
OUTPUT = ROOT / "data" / "processed"

OUTPUT.mkdir(parents=True, exist_ok=True)


def load_labeled_observations() -> pd.DataFrame:
    observations = pd.read_parquet(
        DATASET / "asset_condition_history.parquet"
    )

    observations["prediction_timestamp"] = pd.to_datetime(
        observations["timestamp"],
        format="mixed",
        utc=True,
    )

    failures = pd.read_parquet(
        DATASET / "incidents.parquet",
        columns=[
            "timestamp",
            "asset_id",
        ],
    )

    failures["failure_timestamp"] = pd.to_datetime(
        failures["timestamp"],
        format="mixed",
        utc=True,
    )

    failures = failures.dropna(
        subset=[
            "asset_id",
            "failure_timestamp",
        ]
    )

    failure_times = {
        asset_id: group[
            "failure_timestamp"
        ].tolist()
        for asset_id, group
        in failures.groupby("asset_id")
    }

    observations = observations.sort_values(
        ["asset_id", "prediction_timestamp"]
    ).reset_index(drop=True)

    labels = []

    for asset_id, group in observations.groupby(
        "asset_id",
        sort=False,
    ):
        events = failure_times.get(
            asset_id,
            [],
        )

        for timestamp in group[
            "prediction_timestamp"
        ]:
            horizon = timestamp + pd.Timedelta(days=30)

            label = int(
                any(
                    timestamp < event <= horizon
                    for event in events
                )
            )

            labels.append(label)

    observations["failure_within_30_days"] = labels

    return observations


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(
        ["asset_id", "prediction_timestamp"]
    ).copy()

    grouped = df.groupby(
        "asset_id",
        sort=False,
    )

    df["previous_condition_score"] = (
        grouped["condition_score"]
        .shift(1)
    )

    df["condition_change"] = (
        df["condition_score"]
        - df["previous_condition_score"]
    )

    previous_timestamp = (
        grouped["prediction_timestamp"]
        .shift(1)
    )

    df["days_since_previous_measurement"] = (
        (
            df["prediction_timestamp"]
            - previous_timestamp
        )
        .dt.total_seconds()
        / 86400
    )

    # Only history available BEFORE the current observation.
    df["historical_mean_condition"] = (
        grouped["condition_score"]
        .transform(
            lambda x:
            x.shift(1)
            .expanding()
            .mean()
        )
    )

    df["historical_min_condition"] = (
        grouped["condition_score"]
        .transform(
            lambda x:
            x.shift(1)
            .expanding()
            .min()
        )
    )

    df["historical_mean_degradation"] = (
        grouped["degradation_rate"]
        .transform(
            lambda x:
            x.shift(1)
            .expanding()
            .mean()
        )
    )

    df["historical_observation_count"] = (
        grouped.cumcount()
    )

    feature_columns = [
        "asset_id",
        "prediction_timestamp",

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

        "failure_within_30_days",
    ]

    return df[feature_columns]


def create_split(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(
        "prediction_timestamp"
    ).copy()

    timestamps = df["prediction_timestamp"]

    train_cutoff = timestamps.quantile(0.70)
    validation_cutoff = timestamps.quantile(0.85)

    df["split"] = "test"

    df.loc[
        timestamps <= train_cutoff,
        "split",
    ] = "train"

    df.loc[
        (timestamps > train_cutoff)
        & (timestamps <= validation_cutoff),
        "split",
    ] = "validation"

    return df


def main() -> None:
    print("Loading observations...")
    df = load_labeled_observations()

    print(
        f"Observations: {len(df):,}"
    )

    print("Building historical features...")
    df = build_features(df)

    print("Creating time split...")
    df = create_split(df)

    output = (
        OUTPUT
        / "failure_30d_features.parquet"
    )

    df.to_parquet(
        output,
        index=False,
    )

    print()
    print("=" * 70)
    print("FEATURE DATASET CREATED")
    print("=" * 70)

    print(
        f"Rows: {len(df):,}"
    )

    print(
        f"Columns: {len(df.columns)}"
    )

    print(
        f"Positive labels: "
        f"{df['failure_within_30_days'].sum():,}"
    )

    print("\nSplit:")
    print(
        df["split"]
        .value_counts()
        .to_string()
    )

    print("\nOutput:")
    print(output)


if __name__ == "__main__":
    main()
