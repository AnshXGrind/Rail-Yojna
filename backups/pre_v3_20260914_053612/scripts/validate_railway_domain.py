from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "raw" / "rail_yojna_data"
OUTPUT = ROOT / "data" / "validation"

OUTPUT.mkdir(parents=True, exist_ok=True)


def load(table: str, columns: list[str] | None = None) -> pd.DataFrame:
    return pd.read_parquet(
        DATASET / f"{table}.parquet",
        columns=columns,
    )


def check_required_columns(
    table: str,
    columns: list[str],
) -> list[dict]:
    df = load(table)

    results = []

    for column in columns:
        exists = column in df.columns

        results.append(
            {
                "category": "schema",
                "table": table,
                "check": f"required_column:{column}",
                "violations": 0 if exists else 1,
                "status": "PASS" if exists else "FAIL",
            }
        )

    return results


def check_fk(
    child_table: str,
    child_column: str,
    parent_table: str,
    parent_column: str,
) -> dict:
    child = load(child_table, [child_column])
    parent = load(parent_table, [parent_column])

    child_values = set(
        child[child_column].dropna().tolist()
    )

    parent_values = set(
        parent[parent_column].dropna().tolist()
    )

    invalid = child_values - parent_values

    return {
        "category": "relationship",
        "table": child_table,
        "check": (
            f"{child_column} -> "
            f"{parent_table}.{parent_column}"
        ),
        "violations": len(invalid),
        "sample_invalid_values": list(invalid)[:10],
        "status": "PASS" if not invalid else "FAIL",
    }


def numeric_check(
    table: str,
    column: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> dict:
    df = load(table, [column])

    values = pd.to_numeric(
        df[column],
        errors="coerce",
    ).dropna()

    invalid = 0

    if minimum is not None:
        invalid += int((values < minimum).sum())

    if maximum is not None:
        invalid += int((values > maximum).sum())

    return {
        "category": "physical",
        "table": table,
        "check": (
            f"{column}"
            f"[{minimum},{maximum}]"
        ),
        "violations": invalid,
        "status": "PASS" if invalid == 0 else "FAIL",
    }


def time_order_check(
    table: str,
    start_column: str,
    end_column: str,
) -> dict:
    df = load(
        table,
        [start_column, end_column],
    )

    start = pd.to_datetime(
        df[start_column],
        errors="coerce",
    )

    end = pd.to_datetime(
        df[end_column],
        errors="coerce",
    )

    invalid = (
        start.notna()
        & end.notna()
        & (start > end)
    ).sum()

    return {
        "category": "temporal",
        "table": table,
        "check": (
            f"{start_column} <= {end_column}"
        ),
        "violations": int(invalid),
        "status": "PASS" if invalid == 0 else "FAIL",
    }


def distribution_check(
    table: str,
    column: str,
) -> dict:
    df = load(table, [column])

    missing = int(df[column].isna().sum())
    empty = int(
        (df[column].astype("string") == "").sum()
    )

    return {
        "category": "completeness",
        "table": table,
        "check": column,
        "nulls": missing,
        "empty_strings": empty,
        "status": (
            "PASS"
            if missing == 0 and empty == 0
            else "WARN"
        ),
    }


def run_checks() -> list[dict]:
    results = []

    # ---------------------------------------------------------
    # Infrastructure schema
    # ---------------------------------------------------------

    results.extend(
        check_required_columns(
            "stations",
            [
                "station_id",
                "network_id",
            ],
        )
    )

    results.extend(
        check_required_columns(
            "track_sections",
            [
                "section_id",
                "from_station_id",
                "to_station_id",
            ],
        )
    )

    results.extend(
        check_required_columns(
            "tracks",
            [
                "track_id",
                "section_id",
            ],
        )
    )

    results.extend(
        check_required_columns(
            "assets",
            [
                "asset_id",
                "track_id",
            ],
        )
    )

    # ---------------------------------------------------------
    # Infrastructure relationships
    # ---------------------------------------------------------

    results.append(
        check_fk(
            "stations",
            "network_id",
            "networks",
            "network_id",
        )
    )

    results.append(
        check_fk(
            "track_sections",
            "from_station_id",
            "stations",
            "station_id",
        )
    )

    results.append(
        check_fk(
            "track_sections",
            "to_station_id",
            "stations",
            "station_id",
        )
    )

    results.append(
        check_fk(
            "tracks",
            "section_id",
            "track_sections",
            "section_id",
        )
    )

    results.append(
        check_fk(
            "assets",
            "track_id",
            "tracks",
            "track_id",
        )
    )

    # ---------------------------------------------------------
    # Maintenance relationships
    # ---------------------------------------------------------

    results.append(
        check_fk(
            "asset_condition_history",
            "asset_id",
            "assets",
            "asset_id",
        )
    )

    results.append(
        check_fk(
            "inspections",
            "asset_id",
            "assets",
            "asset_id",
        )
    )

    results.append(
        check_fk(
            "defects",
            "asset_id",
            "assets",
            "asset_id",
        )
    )

    results.append(
        check_fk(
            "maintenance_tasks",
            "asset_id",
            "assets",
            "asset_id",
        )
    )

    results.append(
        check_fk(
            "maintenance_tasks",
            "track_id",
            "tracks",
            "track_id",
        )
    )

    results.append(
        check_fk(
            "maintenance_execution",
            "task_id",
            "maintenance_tasks",
            "task_id",
        )
    )

    # ---------------------------------------------------------
    # Planning relationships
    # ---------------------------------------------------------

    results.append(
        check_fk(
            "block_requests",
            "track_id",
            "tracks",
            "track_id",
        )
    )

    results.append(
        check_fk(
            "blocks",
            "track_id",
            "tracks",
            "track_id",
        )
    )

    results.append(
        check_fk(
            "blocks",
            "request_id",
            "block_requests",
            "request_id",
        )
    )

    results.append(
        check_fk(
            "planning_decisions",
            "request_id",
            "block_requests",
            "request_id",
        )
    )

    # ---------------------------------------------------------
    # Operations
    # ---------------------------------------------------------

    results.append(
        check_fk(
            "train_movements",
            "train_id",
            "trains",
            "train_id",
        )
    )

    results.append(
        check_fk(
            "train_movements",
            "track_id",
            "tracks",
            "track_id",
        )
    )

    results.append(
        check_fk(
            "train_delays",
            "train_id",
            "trains",
            "train_id",
        )
    )

    results.append(
        check_fk(
            "train_delays",
            "station_id",
            "stations",
            "station_id",
        )
    )

    # ---------------------------------------------------------
    # Resources
    # ---------------------------------------------------------

    results.append(
        check_fk(
            "resource_availability",
            "resource_id",
            "resources",
            "resource_id",
        )
    )

    results.append(
        check_fk(
            "task_resources",
            "resource_id",
            "resources",
            "resource_id",
        )
    )

    results.append(
        check_fk(
            "task_resources",
            "task_id",
            "maintenance_tasks",
            "task_id",
        )
    )

    # ---------------------------------------------------------
    # Physical plausibility
    # ---------------------------------------------------------

    results.append(
        numeric_check(
            "track_sections",
            "length_km",
            minimum=0,
        )
    )

    results.append(
        numeric_check(
            "tracks",
            "maximum_speed_kmh",
            minimum=0,
        )
    )

    results.append(
        numeric_check(
            "assets",
            "criticality_score",
            minimum=0,
        )
    )

    results.append(
        numeric_check(
            "maintenance_tasks",
            "estimated_duration_minutes",
            minimum=0,
        )
    )

    results.append(
        numeric_check(
            "blocks",
            "duration_minutes",
            minimum=0,
        )
    )

    results.append(
        numeric_check(
            "train_movements",
            "scheduled_runtime_minutes",
            minimum=0,
        )
    )

    # ---------------------------------------------------------
    # Temporal logic
    # ---------------------------------------------------------

    for args in [
        (
            "maintenance_execution",
            "requested_start",
            "requested_end",
        ),
        (
            "maintenance_execution",
            "approved_start",
            "approved_end",
        ),
        (
            "maintenance_execution",
            "actual_start",
            "actual_end",
        ),
        (
            "blocks",
            "planned_start",
            "planned_end",
        ),
        (
            "blocks",
            "actual_start",
            "actual_end",
        ),
    ]:
        table = args[0]

        path = DATASET / f"{table}.parquet"

        if not path.exists():
            continue

        results.append(
            time_order_check(*args)
        )

    # ---------------------------------------------------------
    # Completeness
    # ---------------------------------------------------------

    results.append(
        distribution_check(
            "assets",
            "station_id",
        )
    )

    results.append(
        distribution_check(
            "planning_decisions",
            "request_id",
        )
    )

    return results


def main() -> None:
    print("=" * 70)
    print("RAIL-YOJNA RAILWAY DOMAIN VALIDATION")
    print("=" * 70)

    results = run_checks()

    output = pd.DataFrame(results)

    output.to_json(
        OUTPUT / "railway_domain_validation.json",
        orient="records",
        indent=2,
    )

    output.to_csv(
        OUTPUT / "railway_domain_validation.csv",
        index=False,
    )

    failed = output[
        output["status"] == "FAIL"
    ]

    warnings = output[
        output["status"] == "WARN"
    ]

    print()
    print(f"Checks run : {len(output)}")
    print(f"Failures   : {len(failed)}")
    print(f"Warnings   : {len(warnings)}")

    print()

    if not failed.empty:
        print("FAILURES:")
        print(
            failed[
                [
                    "category",
                    "table",
                    "check",
                    "violations",
                ]
            ].to_string(index=False)
        )

    if not warnings.empty:
        print("WARNINGS:")
        print(
            warnings[
                [
                    "category",
                    "table",
                    "check",
                    "nulls",
                    "empty_strings",
                ]
            ].to_string(index=False)
        )

    print()
    print("Reports:")
    print(
        OUTPUT / "railway_domain_validation.csv"
    )
    print(
        OUTPUT / "railway_domain_validation.json"
    )


if __name__ == "__main__":
    main()
