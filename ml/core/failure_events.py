from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "raw" / "rail_yojna_data"


def _read_table(
    table: str,
    columns: list[str],
) -> pd.DataFrame:
    """
    Read a railway table from Parquet when available,
    otherwise fall back to CSV.

    This keeps the ML pipeline independent of the
    physical storage format.
    """

    parquet = DATASET / f"{table}.parquet"
    csv = DATASET / f"{table}.csv"

    if parquet.exists():
        return pd.read_parquet(
            parquet,
            columns=columns,
        )

    if csv.exists():
        return pd.read_csv(
            csv,
            usecols=columns,
        )

    raise FileNotFoundError(
        f"Neither {parquet} nor {csv} exists."
    )


def _parse_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(
        series,
        format="mixed",
        errors="coerce",
        utc=True,
    )


def load_failure_events() -> pd.DataFrame:
    """
    Canonical failure-event definition for Rail-Yojna.

    Failure sources:
      - incidents.timestamp
      - emergency_maintenance.failure_time

    If the same physical failure appears in both sources
    at the same asset and timestamp, it is treated as one
    failure event.
    """

    incidents = _read_table(
        "incidents",
        [
            "incident_id",
            "asset_id",
            "timestamp",
        ],
    ).copy()

    incidents["failure_timestamp"] = _parse_utc(
        incidents["timestamp"]
    )

    incidents = incidents[
        incidents["asset_id"].notna()
        & incidents["failure_timestamp"].notna()
    ][
        [
            "incident_id",
            "asset_id",
            "failure_timestamp",
        ]
    ].copy()

    incidents["failure_source"] = "incident"

    emergency = _read_table(
        "emergency_maintenance",
        [
            "emergency_id",
            "asset_id",
            "failure_time",
        ],
    ).copy()

    emergency["failure_timestamp"] = _parse_utc(
        emergency["failure_time"]
    )

    emergency = emergency[
        emergency["asset_id"].notna()
        & emergency["failure_timestamp"].notna()
    ][
        [
            "emergency_id",
            "asset_id",
            "failure_timestamp",
        ]
    ].rename(
        columns={
            "emergency_id": "incident_id",
        }
    )

    emergency["failure_source"] = "emergency_maintenance"

    events = pd.concat(
        [
            incidents,
            emergency,
        ],
        ignore_index=True,
    )

    events = (
        events
        .drop_duplicates(
            subset=[
                "asset_id",
                "failure_timestamp",
            ]
        )
        .sort_values(
            [
                "asset_id",
                "failure_timestamp",
            ]
        )
        .reset_index(drop=True)
    )

    return events
