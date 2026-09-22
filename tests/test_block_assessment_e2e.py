from pathlib import Path

import pandas as pd

from backend.app.services.operational_service import (
    _normalise_asset_type,
    _safety_rule_for_tasks,
)


BASE = Path("data/raw/rail_yojna_data")


def test_safety_mapping_known_and_unknown_types():
    assert _normalise_asset_type("OHE_maintenance") == "ohe"
    assert _normalise_asset_type("ballast_renewal") == "ballast"

    result = _safety_rule_for_tasks(
        [
            {
                "task_id": "T-OHE",
                "task_type": "OHE_maintenance",
            },
            {
                "task_id": "T-BALLAST",
                "task_type": "ballast_renewal",
            },
        ]
    )

    assert result["status"] == "PARTIAL"

    mapped = {
        rule["task_id"]
        for rule in result["rules"]
    }

    unmapped = {
        item["task_id"]
        for item in result["unmapped_tasks"]
    }

    assert "T-OHE" in mapped
    assert "T-BALLAST" in unmapped


def test_real_historical_train_maintenance_overlap_exists():
    maintenance = pd.read_csv(
        BASE / "maintenance_tasks.csv",
        usecols=[
            "task_id",
            "planned_date",
            "section_id",
            "track_id",
            "block_required",
        ],
    )

    movements = pd.read_csv(
        BASE / "train_movements.csv",
        usecols=[
            "movement_id",
            "date",
            "section_id",
            "track_id",
            "scheduled_entry",
            "scheduled_exit",
        ],
    )

    maintenance = maintenance[
        maintenance["block_required"].astype(bool)
    ].copy()

    maintenance["date"] = pd.to_datetime(
        maintenance["planned_date"],
        errors="coerce",
    ).dt.strftime("%Y-%m-%d")

    movements["date"] = pd.to_datetime(
        movements["date"],
        errors="coerce",
    ).dt.strftime("%Y-%m-%d")

    joined = maintenance.merge(
        movements,
        on=[
            "date",
            "section_id",
            "track_id",
        ],
        how="inner",
    )

    assert not joined.empty, (
        "No historical block-required maintenance task "
        "shares a date/section/track with a train movement."
    )


def test_safety_constraints_have_india_hard_rules():
    constraints = pd.read_csv(
        BASE / "safety_constraints.csv"
    )

    india = constraints[
        constraints["jurisdiction"]
        .astype(str)
        .str.strip()
        .str.upper()
        == "INDIA"
    ]

    assert not india.empty

    hard = india[
        india["hard_constraint"].astype(bool)
    ]

    assert not hard.empty

    required = {
        "minimum_block_duration_minutes",
        "minimum_clearance_minutes",
        "required_personnel",
    }

    assert required.issubset(
        set(hard.columns)
    )
