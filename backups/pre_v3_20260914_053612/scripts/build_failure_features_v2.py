from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "raw" / "rail_yojna_data"
OUTPUT = ROOT / "data" / "processed"
OUTPUT.mkdir(parents=True, exist_ok=True)

HORIZON_DAYS = 30


def parse_time(s: pd.Series) -> pd.Series:
    return pd.to_datetime(
        s,
        format="mixed",
        errors="coerce",
        utc=True,
    )


def load_observations() -> pd.DataFrame:
    df = pd.read_parquet(DATASET / "asset_condition_history.parquet")

    df["prediction_timestamp"] = parse_time(df["timestamp"])

    return df.dropna(
        subset=["asset_id", "prediction_timestamp"]
    ).sort_values(
        ["asset_id", "prediction_timestamp"]
    )


def load_asset_info() -> pd.DataFrame:
    df = pd.read_parquet(
        DATASET / "assets.parquet",
        columns=[
            "asset_id",
            "installation_date",
            "design_life_years",
            "criticality_score",
        ],
    )

    df["installation_date"] = parse_time(
        df["installation_date"]
    )

    return df


def load_historical_table(
    table: str,
    columns: list[str],
    time_column: str,
) -> pd.DataFrame:
    df = pd.read_parquet(
        DATASET / f"{table}.parquet",
        columns=columns,
    )

    df[time_column] = parse_time(df[time_column])

    return df.dropna(
        subset=["asset_id", time_column]
    ).sort_values(
        ["asset_id", time_column]
    )


def build_base_condition_features(
    observations: pd.DataFrame,
) -> pd.DataFrame:
    df = observations.copy()

    g = df.groupby("asset_id", sort=False)

    df["previous_condition_score"] = (
        g["condition_score"].shift(1)
    )

    df["condition_change"] = (
        df["condition_score"]
        - df["previous_condition_score"]
    )

    previous_timestamp = (
        g["prediction_timestamp"].shift(1)
    )

    df["days_since_previous_measurement"] = (
        (
            df["prediction_timestamp"]
            - previous_timestamp
        ).dt.total_seconds() / 86400
    )

    df["historical_mean_condition"] = (
        g["condition_score"]
        .transform(
            lambda x: x.shift(1).expanding().mean()
        )
    )

    df["historical_min_condition"] = (
        g["condition_score"]
        .transform(
            lambda x: x.shift(1).expanding().min()
        )
    )

    df["historical_mean_degradation"] = (
        g["degradation_rate"]
        .transform(
            lambda x: x.shift(1).expanding().mean()
        )
    )

    df["historical_observation_count"] = (
        g.cumcount()
    )

    return df


def add_asset_features(
    df: pd.DataFrame,
    assets: pd.DataFrame,
) -> pd.DataFrame:

    df = df.merge(
        assets,
        on="asset_id",
        how="left",
        validate="many_to_one",
    )

    df["asset_age_days"] = (
        df["prediction_timestamp"]
        - df["installation_date"]
    ).dt.total_seconds() / 86400

    return df


def add_asof_count_and_recency(
    observations: pd.DataFrame,
    history: pd.DataFrame,
    history_time: str,
    prefix: str,
) -> pd.DataFrame:
    """
    For each observation at time T, calculate historical information
    from the same asset using only records with event_time <= T.

    All timestamp comparisons are converted to UTC nanoseconds so
    timezone-aware and timezone-naive representations cannot conflict.
    """

    left = observations[
        ["asset_id", "prediction_timestamp"]
    ].copy()

    right = history[
        ["asset_id", history_time]
    ].copy()

    left["asset_id"] = left["asset_id"].astype("string")
    right["asset_id"] = right["asset_id"].astype("string")

    left["prediction_timestamp"] = pd.to_datetime(
        left["prediction_timestamp"],
        format="mixed",
        errors="coerce",
        utc=True,
    )

    right[history_time] = pd.to_datetime(
        right[history_time],
        format="mixed",
        errors="coerce",
        utc=True,
    )

    left = left.dropna(
        subset=["asset_id", "prediction_timestamp"]
    )

    right = right.dropna(
        subset=["asset_id", history_time]
    )

    # merge_asof requires the time keys to be sorted globally.
    left = left.sort_values(
        ["prediction_timestamp", "asset_id"]
    ).reset_index(drop=True)

    right = right.sort_values(
        [history_time, "asset_id"]
    ).reset_index(drop=True)

    merged = pd.merge_asof(
        left,
        right,
        left_on="prediction_timestamp",
        right_on=history_time,
        by="asset_id",
        direction="backward",
        allow_exact_matches=True,
    )

    merged[f"{prefix}_days_since_last"] = (
        (
            merged["prediction_timestamp"]
            - merged[history_time]
        )
        .dt.total_seconds()
        / 86400.0
    )

    # Convert timestamps to UTC nanoseconds for robust comparison.
    right_times = right[history_time].astype("int64")

    events_by_asset = {}

    for asset_id, group in right.assign(
        _time_ns=right_times
    ).groupby(
        "asset_id",
        sort=False,
    ):
        events_by_asset[asset_id] = (
            group["_time_ns"]
            .sort_values()
            .to_numpy()
        )

    left_time_ns = (
        left["prediction_timestamp"]
        .astype("int64")
        .to_numpy()
    )

    counts = []

    for asset_id, timestamp_ns in zip(
        left["asset_id"],
        left_time_ns,
    ):
        events = events_by_asset.get(asset_id)

        if events is None:
            counts.append(0)
            continue

        # Number of events with event_time <= prediction_time.
        counts.append(
            int(
                (events <= timestamp_ns).sum()
            )
        )

    merged[f"{prefix}_count_before"] = counts

    return merged[
        [
            "asset_id",
            "prediction_timestamp",
            f"{prefix}_days_since_last",
            f"{prefix}_count_before",
        ]
    ]

def add_defect_features(df: pd.DataFrame) -> pd.DataFrame:
    defects = load_historical_table(
        "defects",
        [
            "asset_id",
            "detected_timestamp",
        ],
        "detected_timestamp",
    )

    features = add_asof_count_and_recency(
        df,
        defects,
        "detected_timestamp",
        "defect",
    )

    return df.merge(
        features,
        on=["asset_id", "prediction_timestamp"],
        how="left",
        validate="one_to_one",
    )


def add_inspection_features(df: pd.DataFrame) -> pd.DataFrame:
    inspections = load_historical_table(
        "inspections",
        [
            "asset_id",
            "inspection_date",
        ],
        "inspection_date",
    )

    features = add_asof_count_and_recency(
        df,
        inspections,
        "inspection_date",
        "inspection",
    )

    return df.merge(
        features,
        on=["asset_id", "prediction_timestamp"],
        how="left",
        validate="one_to_one",
    )


def add_maintenance_features(df: pd.DataFrame) -> pd.DataFrame:
    tasks = load_historical_table(
        "maintenance_tasks",
        [
            "asset_id",
            "planned_date",
        ],
        "planned_date",
    )

    features = add_asof_count_and_recency(
        df,
        tasks,
        "planned_date",
        "maintenance",
    )

    return df.merge(
        features,
        on=["asset_id", "prediction_timestamp"],
        how="left",
        validate="one_to_one",
    )


def add_failure_features(df: pd.DataFrame) -> pd.DataFrame:
    incidents = load_historical_table(
        "incidents",
        [
            "asset_id",
            "timestamp",
        ],
        "timestamp",
    )

    features = add_asof_count_and_recency(
        df,
        incidents,
        "timestamp",
        "incident",
    )

    return df.merge(
        features,
        on=["asset_id", "prediction_timestamp"],
        how="left",
        validate="one_to_one",
    )


def build_target(df: pd.DataFrame) -> pd.DataFrame:
    incidents = pd.read_parquet(
        DATASET / "incidents.parquet",
        columns=["asset_id", "timestamp"],
    )

    incidents["failure_timestamp"] = parse_time(
        incidents["timestamp"]
    )

    incidents = incidents.dropna(
        subset=["asset_id", "failure_timestamp"]
    )

    failure_times = {
        asset_id: group["failure_timestamp"].tolist()
        for asset_id, group
        in incidents.groupby("asset_id")
    }

    labels = []

    for asset_id, timestamp in zip(
        df["asset_id"],
        df["prediction_timestamp"],
    ):
        events = failure_times.get(asset_id, [])

        end = timestamp + pd.Timedelta(
            days=HORIZON_DAYS
        )

        labels.append(
            int(
                any(
                    timestamp < event <= end
                    for event in events
                )
            )
        )

    df["failure_within_30_days"] = labels

    return df


def create_split(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(
        "prediction_timestamp"
    ).copy()

    train_cutoff = df["prediction_timestamp"].quantile(0.70)
    validation_cutoff = df["prediction_timestamp"].quantile(0.85)

    df["split"] = "test"

    df.loc[
        df["prediction_timestamp"] <= train_cutoff,
        "split",
    ] = "train"

    df.loc[
        (
            df["prediction_timestamp"] > train_cutoff
        )
        & (
            df["prediction_timestamp"] <= validation_cutoff
        ),
        "split",
    ] = "validation"

    return df


def main():
    print("Loading observations...")
    df = load_observations()

    print(f"Observations: {len(df):,}")

    print("Building condition-history features...")
    df = build_base_condition_features(df)

    print("Adding asset features...")
    df = add_asset_features(
        df,
        load_asset_info(),
    )

    print("Adding historical defect features...")
    df = add_defect_features(df)

    print("Adding historical inspection features...")
    df = add_inspection_features(df)

    print("Adding historical maintenance features...")
    df = add_maintenance_features(df)

    print("Adding historical incident features...")
    df = add_failure_features(df)

    print("Building target...")
    df = build_target(df)

    print("Creating time split...")
    df = create_split(df)

    output = OUTPUT / "failure_30d_features_v2.parquet"

    df.to_parquet(
        output,
        index=False,
    )

    print()
    print("=" * 70)
    print("FEATURE SET V2")
    print("=" * 70)

    print(f"Rows: {len(df):,}")
    print(f"Columns: {len(df.columns)}")
    print(
        "Positive labels:",
        int(df["failure_within_30_days"].sum()),
    )

    print("\nFeatures:")
    for column in df.columns:
        print(f"  {column}")

    print("\nSaved:")
    print(output)


if __name__ == "__main__":
    main()
