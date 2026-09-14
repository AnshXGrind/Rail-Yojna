from __future__ import annotations

from pathlib import Path

import pandas as pd

from ml.core.failure_events import load_failure_events


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "raw" / "rail_yojna_data"
OUTPUT = ROOT / "data" / "processed"

HORIZON_DAYS = 30


def parse_time(series: pd.Series) -> pd.Series:
    return pd.to_datetime(
        series,
        format="mixed",
        errors="coerce",
        utc=True,
    )


def read_table(table: str) -> pd.DataFrame:
    parquet = DATASET / f"{table}.parquet"
    csv = DATASET / f"{table}.csv"

    if parquet.exists():
        return pd.read_parquet(parquet)

    if csv.exists():
        return pd.read_csv(csv)

    raise FileNotFoundError(
        f"Neither {parquet} nor {csv} exists."
    )


def load_observations() -> pd.DataFrame:
    observations = read_table(
        "asset_condition_history"
    ).copy()

    observations["prediction_timestamp"] = parse_time(
        observations["timestamp"]
    )

    observations = observations.dropna(
        subset=[
            "asset_id",
            "prediction_timestamp",
        ]
    )

    return observations.sort_values(
        [
            "asset_id",
            "prediction_timestamp",
        ]
    ).reset_index(drop=True)


def build_labels(
    observations: pd.DataFrame,
    failures: pd.DataFrame,
) -> pd.DataFrame:

    result = observations.copy()

    failure_groups = {
        asset_id: group["failure_timestamp"].tolist()
        for asset_id, group in failures.groupby("asset_id")
    }

    labels = []

    for asset_id, timestamp in zip(
        result["asset_id"],
        result["prediction_timestamp"],
    ):
        failure_times = failure_groups.get(asset_id, [])

        horizon = timestamp + pd.Timedelta(
            days=HORIZON_DAYS
        )

        label = int(
            any(
                timestamp < failure_time <= horizon
                for failure_time in failure_times
            )
        )

        labels.append(label)

    result["failure_within_30_days"] = labels

    return result


def main() -> None:
    print("=" * 72)
    print("RAIL-YOJNA V3 TARGET BUILD")
    print("=" * 72)

    print("\nLoading observations...")
    observations = load_observations()

    print(
        f"Observations: {len(observations):,}"
    )

    print("\nLoading canonical failure events...")
    failures = load_failure_events()

    print(
        f"Failure events: {len(failures):,}"
    )

    print("\nFailure sources:")
    print(
        failures["failure_source"]
        .value_counts(dropna=False)
        .to_string()
    )

    print("\nBuilding 30-day labels...")
    labeled = build_labels(
        observations,
        failures,
    )

    positives = int(
        labeled["failure_within_30_days"].sum()
    )

    negatives = len(labeled) - positives

    print("\n" + "-" * 72)
    print("V3 TARGET SUMMARY")
    print("-" * 72)

    print(
        f"Total observations : {len(labeled):,}"
    )
    print(
        f"Positive labels    : {positives:,}"
    )
    print(
        f"Negative labels    : {negatives:,}"
    )
    print(
        f"Positive rate      : "
        f"{labeled['failure_within_30_days'].mean():.4%}"
    )

    output = (
        OUTPUT
        / "failure_30d_target_v3.parquet"
    )

    labeled.to_parquet(
        output,
        index=False,
    )

    print()
    print(
        f"Saved: {output}"
    )

    print()
    print("=" * 72)
    print("V3 TARGET BUILD COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    main()
