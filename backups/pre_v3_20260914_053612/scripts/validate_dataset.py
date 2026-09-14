from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "raw" / "rail_yojna_data"
OUTPUT = ROOT / "data" / "validation"

OUTPUT.mkdir(parents=True, exist_ok=True)


def schema(path: Path):
    return pq.read_schema(path)


def load_column(path: Path, column: str) -> pd.Series:
    return pd.read_parquet(path, columns=[column])[column]


def get_relationships() -> pd.DataFrame:
    path = DATASET / "schema_relationships.csv"

    df = pd.read_csv(path)

    expected = {
        "table_name",
        "column_name",
        "referenced_table",
        "referenced_column",
        "relationship_type",
    }

    missing = expected - set(df.columns)

    if missing:
        raise RuntimeError(
            f"Missing relationship columns: {sorted(missing)}"
        )

    return df


def foreign_key_checks() -> list[dict]:
    relationships = get_relationships()
    results = []

    for _, row in relationships.iterrows():
        if str(row["relationship_type"]).lower() != "foreign_key":
            continue

        child_table = str(row["table_name"])
        child_column = str(row["column_name"])
        parent_table = str(row["referenced_table"])
        parent_column = str(row["referenced_column"])

        child_path = DATASET / f"{child_table}.parquet"
        parent_path = DATASET / f"{parent_table}.parquet"

        result = {
            "child_table": child_table,
            "child_column": child_column,
            "parent_table": parent_table,
            "parent_column": parent_column,
        }

        if not child_path.exists():
            result.update({
                "status": "FAIL",
                "reason": "child_table_missing",
                "violations": None,
            })
            results.append(result)
            continue

        if not parent_path.exists():
            result.update({
                "status": "FAIL",
                "reason": "parent_table_missing",
                "violations": None,
            })
            results.append(result)
            continue

        child_schema = schema(child_path)
        parent_schema = schema(parent_path)

        if child_column not in child_schema.names:
            result.update({
                "status": "FAIL",
                "reason": "child_column_missing",
                "violations": None,
            })
            results.append(result)
            continue

        if parent_column not in parent_schema.names:
            result.update({
                "status": "FAIL",
                "reason": "parent_column_missing",
                "violations": None,
            })
            results.append(result)
            continue

        child_values = (
            load_column(child_path, child_column)
            .dropna()
            .drop_duplicates()
        )

        parent_values = set(
            load_column(parent_path, parent_column)
            .dropna()
            .tolist()
        )

        invalid = child_values[
            ~child_values.isin(parent_values)
        ]

        result.update({
            "child_unique_values": int(child_values.nunique()),
            "parent_unique_values": len(parent_values),
            "violations": int(len(invalid)),
            "sample_invalid_values": json.dumps(
                invalid.head(10).tolist(),
                default=str,
            ),
            "status": "PASS" if invalid.empty else "FAIL",
            "reason": "",
        })

        results.append(result)

    return results


def primary_key_checks() -> list[dict]:
    results = []

    for path in sorted(DATASET.glob("*.parquet")):
        table = path.stem
        columns = schema(path).names

        candidate = f"{table}_id"

        if candidate not in columns:
            continue

        values = load_column(path, candidate)

        duplicates = int(
            values.dropna().duplicated().sum()
        )

        nulls = int(values.isna().sum())

        results.append({
            "table": table,
            "primary_key": candidate,
            "rows": len(values),
            "unique_values": int(values.nunique(dropna=True)),
            "null_values": nulls,
            "duplicate_values": duplicates,
            "status": (
                "PASS"
                if nulls == 0 and duplicates == 0
                else "FAIL"
            ),
        })

    return results


def null_checks() -> list[dict]:
    results = []

    for path in sorted(DATASET.glob("*.parquet")):
        table = path.stem
        parquet = pq.ParquetFile(path)

        # Read only the table in manageable batches.
        totals = {}

        for batch in parquet.iter_batches(batch_size=100_000):
            df = batch.to_pandas()

            for column in df.columns:
                if column not in totals:
                    totals[column] = {
                        "rows": 0,
                        "nulls": 0,
                    }

                totals[column]["rows"] += len(df)
                totals[column]["nulls"] += int(
                    df[column].isna().sum()
                )

        for column, stats in totals.items():
            null_pct = (
                stats["nulls"] / stats["rows"] * 100
                if stats["rows"]
                else 0
            )

            results.append({
                "table": table,
                "column": column,
                "rows": stats["rows"],
                "nulls": stats["nulls"],
                "null_percent": round(null_pct, 4),
            })

    return results


def temporal_checks() -> list[dict]:
    checks = []

    rules = [
        (
            "maintenance_execution",
            "actual_start",
            "actual_end",
        ),
        (
            "maintenance_execution",
            "planned_start",
            "planned_end",
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
    ]

    for table, start_col, end_col in rules:
        path = DATASET / f"{table}.parquet"

        if not path.exists():
            continue

        columns = schema(path).names

        if start_col not in columns or end_col not in columns:
            continue

        invalid = 0
        rows_checked = 0

        parquet = pq.ParquetFile(path)

        for batch in parquet.iter_batches(
            batch_size=100_000,
            columns=[start_col, end_col],
        ):
            df = batch.to_pandas()

            start = pd.to_datetime(
                df[start_col],
                errors="coerce",
            )

            end = pd.to_datetime(
                df[end_col],
                errors="coerce",
            )

            mask = (
                start.notna()
                & end.notna()
                & (start > end)
            )

            invalid += int(mask.sum())
            rows_checked += len(df)

        checks.append({
            "table": table,
            "start_column": start_col,
            "end_column": end_col,
            "rows_checked": rows_checked,
            "violations": invalid,
            "status": "PASS" if invalid == 0 else "FAIL",
        })

    return checks


def main() -> None:
    if not DATASET.exists():
        raise FileNotFoundError(
            f"Dataset not found: {DATASET}"
        )

    parquet_tables = sorted(
        DATASET.glob("*.parquet")
    )

    print("=" * 70)
    print("RAIL-YOJNA DATASET VALIDATION")
    print("=" * 70)

    print(f"Dataset : {DATASET}")
    print(f"Tables  : {len(parquet_tables)}")
    print()

    print("1. Foreign keys...")
    fk = foreign_key_checks()

    print("2. Primary keys...")
    pk = primary_key_checks()

    print("3. Null analysis...")
    nulls = null_checks()

    print("4. Temporal checks...")
    temporal = temporal_checks()

    fk_df = pd.DataFrame(fk)
    pk_df = pd.DataFrame(pk)
    null_df = pd.DataFrame(nulls)
    temporal_df = pd.DataFrame(temporal)

    fk_df.to_csv(
        OUTPUT / "foreign_key_checks.csv",
        index=False,
    )

    pk_df.to_csv(
        OUTPUT / "primary_key_checks.csv",
        index=False,
    )

    null_df.to_csv(
        OUTPUT / "null_summary.csv",
        index=False,
    )

    temporal_df.to_csv(
        OUTPUT / "temporal_checks.csv",
        index=False,
    )

    summary = {
        "foreign_keys": {
            "checked": len(fk_df),
            "failed": int(
                (fk_df["status"] == "FAIL").sum()
            ) if not fk_df.empty else 0,
        },
        "primary_keys": {
            "checked": len(pk_df),
            "failed": int(
                (pk_df["status"] == "FAIL").sum()
            ) if not pk_df.empty else 0,
        },
        "temporal": {
            "checked": len(temporal_df),
            "failed": int(
                (temporal_df["status"] == "FAIL").sum()
            ) if not temporal_df.empty else 0,
        },
    }

    (OUTPUT / "validation_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(
        f"Foreign keys : "
        f"{summary['foreign_keys']['failed']} failed / "
        f"{summary['foreign_keys']['checked']} checked"
    )

    print(
        f"Primary keys : "
        f"{summary['primary_keys']['failed']} failed / "
        f"{summary['primary_keys']['checked']} checked"
    )

    print(
        f"Temporal     : "
        f"{summary['temporal']['failed']} failed / "
        f"{summary['temporal']['checked']} checked"
    )

    print()
    print("Reports written to:")
    print(OUTPUT)


if __name__ == "__main__":
    main()
