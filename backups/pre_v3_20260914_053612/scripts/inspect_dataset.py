from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "raw" / "rail_yojna_data"
OUTPUT = ROOT / "data" / "metadata"

OUTPUT.mkdir(parents=True, exist_ok=True)


def inspect_parquet(path: Path) -> dict:
    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow

    columns = []
    for field in schema:
        columns.append(
            {
                "column": field.name,
                "dtype": str(field.type),
                "nullable": field.nullable,
            }
        )

    return {
        "table": path.stem,
        "format": "parquet",
        "rows": parquet.metadata.num_rows,
        "columns": parquet.metadata.num_columns,
        "file_size_mb": round(path.stat().st_size / 1024**2, 2),
        "schema": columns,
    }


def inspect_csv(path: Path) -> dict:
    # Only read a small sample. We do not load the complete CSV.
    sample = pd.read_csv(path, nrows=1000)

    return {
        "table": path.stem,
        "format": "csv",
        "sample_rows": len(sample),
        "columns": len(sample.columns),
        "file_size_mb": round(path.stat().st_size / 1024**2, 2),
        "columns_info": [
            {
                "column": column,
                "dtype": str(sample[column].dtype),
                "nulls_in_sample": int(sample[column].isna().sum()),
            }
            for column in sample.columns
        ],
    }


def main() -> None:
    if not DATASET.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET}")

    parquet_files = sorted(DATASET.glob("*.parquet"))
    csv_files = sorted(DATASET.glob("*.csv"))

    print(f"Dataset: {DATASET}")
    print(f"Parquet files: {len(parquet_files)}")
    print(f"CSV files: {len(csv_files)}")

    parquet_report = []
    for path in parquet_files:
        print(f"Inspecting Parquet: {path.name}")
        parquet_report.append(inspect_parquet(path))

    csv_report = []
    for path in csv_files:
        print(f"Inspecting CSV sample: {path.name}")
        csv_report.append(inspect_csv(path))

    report = {
        "dataset_path": str(DATASET),
        "parquet_tables": parquet_report,
        "csv_tables": csv_report,
    }

    output_file = OUTPUT / "dataset_inventory.json"
    output_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Human-readable table summary.
    rows = [
        {
            "table": item["table"],
            "format": item["format"],
            "rows": item["rows"],
            "columns": item["columns"],
            "file_size_mb": item["file_size_mb"],
        }
        for item in parquet_report
    ]

    summary = pd.DataFrame(rows).sort_values("rows", ascending=False)

    summary_file = OUTPUT / "dataset_inventory.csv"
    summary.to_csv(summary_file, index=False)

    print("\nGenerated:")
    print(f"  {output_file}")
    print(f"  {summary_file}")

    print("\nLargest tables:")
    print(summary.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
