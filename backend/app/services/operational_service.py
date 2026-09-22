# Phase 22: train occupancy remains independently evaluated; missing train data must not erase safety/resource findings.

from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd

from backend.app.services.block_service import (
    generate_block_candidates,
)


BASE = "data/raw/rail_yojna_data"


@lru_cache(maxsize=1)
def _movements() -> pd.DataFrame:
    df = pd.read_csv(
        f"{BASE}/train_movements.csv",
        usecols=[
            "movement_id",
            "train_id",
            "date",
            "section_id",
            "track_id",
            "scheduled_entry",
            "scheduled_exit",
            "actual_entry",
            "actual_exit",
        ],
    )

    for col in [
        "scheduled_entry",
        "scheduled_exit",
        "actual_entry",
        "actual_exit",
    ]:
        df[col] = pd.to_datetime(
            df[col],
            utc=True,
            errors="coerce",
        )

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
    ).dt.strftime("%Y-%m-%d")

    return df


@lru_cache(maxsize=1)
def _safety_constraints() -> pd.DataFrame:
    df = pd.read_csv(
        f"{BASE}/safety_constraints.csv"
    )

    return df


def _normalise_asset_type(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip().lower()

    aliases = {
        "ohe": "ohe",
        "ohe_maintenance": "ohe",
        "ohe_inspection": "ohe",

        "rail": "rail",
        "rail_replacement": "rail",
        "rail_grinding": "rail",
        "rail_inspection": "rail",

        "ballast": "ballast",
        "ballast_renewal": "ballast",

        "point_machine": "point_machine",
        "point_machine_replacement": "point_machine",

        "signal": "signal",
        "signal_replacement": "signal",

        "axle_counter": "axle_counter",
        "track_circuit": "track_circuit",

        "turnout": "turnout",
        "bridge": "bridge",
        "level_crossing": "level_crossing",

        "platform_equipment": "platform_equipment",

        "signalling_equipment": "signalling_equipment",
        "signalling_maintenance": "signalling_equipment",
        "signalling_inspection": "signalling_equipment",
    }

    return aliases.get(text)


def _safety_rule_for_tasks(tasks: list[dict]) -> dict:
    constraints = _safety_constraints()

    if constraints.empty:
        return {
            "status": "DATA_GAP",
            "reason": "No safety constraints available.",
            "rules": [],
            "unmapped_tasks": [],
        }

    india = constraints[
        constraints["jurisdiction"]
        .astype(str)
        .str.strip()
        .str.upper()
        == "INDIA"
    ].copy()

    rules = []
    unmapped_tasks = []

    for task in tasks:
        raw_task_type = task.get("task_type")
        asset_type = _normalise_asset_type(
            raw_task_type
        )

        if not asset_type:
            unmapped_tasks.append({
                "task_id": task.get("task_id"),
                "task_type": raw_task_type,
                "reason": "Task type could not be normalized.",
            })
            continue

        constraint_types = (
            india["asset_type"]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        match = india[
            constraint_types == asset_type.lower()
        ]

        if match.empty:
            unmapped_tasks.append({
                "task_id": task.get("task_id"),
                "task_type": raw_task_type,
                "asset_type": asset_type,
                "reason": (
                    "No India safety rule exists for this "
                    "asset/task type."
                ),
            })
            continue

        hard = match[
            match["hard_constraint"].astype(bool)
        ]

        row = (
            hard.iloc[0]
            if not hard.empty
            else match.iloc[0]
        )

        rules.append({
            "task_id": task.get("task_id"),
            "task_type": raw_task_type,
            "asset_type": asset_type,
            "rule_code": row["rule_code"],
            "minimum_block_duration_minutes": float(
                row["minimum_block_duration_minutes"]
            ),
            "minimum_clearance_minutes": float(
                row["minimum_clearance_minutes"]
            ),
            "required_isolation": row[
                "required_isolation"
            ],
            "required_protection": row[
                "required_protection"
            ],
            "required_personnel": int(
                row["required_personnel"]
            ),
            "hard_constraint": bool(
                row["hard_constraint"]
            ),
        })

    if not rules and unmapped_tasks:
        return {
            "status": "DATA_GAP",
            "reason": (
                "No applicable India safety rule could be "
                "mapped to the selected tasks."
            ),
            "rules": [],
            "unmapped_tasks": unmapped_tasks,
        }

    if unmapped_tasks:
        return {
            "status": "PARTIAL",
            "reason": (
                "Safety rules were mapped for only part of "
                "the candidate workload."
            ),
            "rules": rules,
            "unmapped_tasks": unmapped_tasks,
        }

    return {
        "status": "EVALUATED",
        "reason": (
            "Applicable India safety rules were found for "
            "all selected tasks."
        ),
        "rules": rules,
        "unmapped_tasks": [],
    }


def _movement_interval(row) -> tuple[pd.Timestamp, pd.Timestamp]:
    actual_start = row["actual_entry"]
    actual_finish = row["actual_exit"]

    if pd.notna(actual_start) and pd.notna(actual_finish):
        return actual_start, actual_finish

    return row["scheduled_entry"], row["scheduled_exit"]


def _find_windows(
    *,
    window_start: pd.Timestamp,
    window_finish: pd.Timestamp,
    duration_minutes: float,
    clearance_minutes: float,
    movements: pd.DataFrame,
):
    effective_duration = (
        duration_minutes + 2 * clearance_minutes
    )

    if effective_duration <= 0:
        return [], [], True

    relevant = movements.copy()

    occupied = []

    for _, row in relevant.iterrows():
        start, finish = _movement_interval(row)

        if pd.isna(start) or pd.isna(finish):
            continue

        # Add clearance around each movement.
        occupied_start = (
            start - pd.Timedelta(minutes=clearance_minutes)
        )

        occupied_finish = (
            finish + pd.Timedelta(minutes=clearance_minutes)
        )

        if (
            occupied_finish > window_start
            and occupied_start < window_finish
        ):
            occupied.append({
                "movement_id": row["movement_id"],
                "train_id": row["train_id"],
                "start": max(
                    occupied_start,
                    window_start,
                ),
                "finish": min(
                    occupied_finish,
                    window_finish,
                ),
            })

    occupied.sort(key=lambda x: x["start"])

    available = []

    cursor = window_start

    for item in occupied:
        if item["start"] > cursor:
            gap = (
                item["start"] - cursor
            ).total_seconds() / 60

            if gap >= effective_duration:
                available.append({
                    "start": cursor,
                    "finish": (
                        cursor
                        + pd.Timedelta(
                            minutes=effective_duration
                        )
                    ),
                    "duration_minutes": effective_duration,
                })

        if item["finish"] > cursor:
            cursor = item["finish"]

    if cursor < window_finish:
        gap = (
            window_finish - cursor
        ).total_seconds() / 60

        if gap >= effective_duration:
            available.append({
                "start": cursor,
                "finish": (
                    cursor
                    + pd.Timedelta(
                        minutes=effective_duration
                    )
                ),
                "duration_minutes": effective_duration,
            })

    return (
        available[:10],
        occupied[:100],
        len(available) > 0,
    )


def assess_block(
    block_id: str,
    *,
    planned_date: str | None = None,
    limit: int = 200,
) -> dict:

    result = generate_block_candidates(
        planned_date=planned_date,
        limit=limit,
    )

    candidates = [
        item
        for item in result.get("items", [])
        if item.get("block_id") == block_id
    ]

    if not candidates:
        return {
            "block_id": block_id,
            "status": "NOT_FOUND",
            "reason": "Block candidate not found.",
        }

    candidate = candidates[0]

    planned_date_value = (
        candidate["planned_date"][:10]
        if candidate.get("planned_date")
        else None
    )

    movement_df = _movements()

    # --------------------------------------------------------
    # SAFETY IS EVALUATED FIRST.
    #
    # Missing train movement data must not prevent safety
    # assessment from being returned.
    # --------------------------------------------------------

    safety = _safety_rule_for_tasks(
        candidate.get("tasks", [])
    )

    safety_payload = {
        "status": safety.get("status"),
        "rules": safety.get("rules", []),
        "unmapped_tasks": safety.get(
            "unmapped_tasks", []
        ),
    }

    # --------------------------------------------------------
    # Operational train evidence.
    # --------------------------------------------------------

    date_movements = movement_df[
        movement_df["date"].astype(str)
        == str(planned_date_value)
    ].copy()

    section = str(candidate.get("section_id"))
    track = str(candidate.get("track_id"))

    movement_matches = (
        date_movements[
            (
                date_movements["section_id"].astype(str)
                == section
            )
            &
            (
                date_movements["track_id"].astype(str)
                == track
            )
        ].copy()
        if not date_movements.empty
        else date_movements.copy()
    )

    safety_mapping_gap = safety["status"] in {
        "NOT_MAPPED",
        "DATA_GAP",
        "PARTIAL",
    }

    rules = safety.get("rules", [])

    # --------------------------------------------------------
    # No train movement data for this exact planned date.
    # Keep safety result intact, but continue with a complete
    # component assessment.
    # --------------------------------------------------------

    if date_movements.empty:
        return {
            "block_id": block_id,
            # Train status is DATA_GAP because train data is
            # independently unavailable for this exact date.
            "status": "DATA_GAP",
            "reason": (
                "No train movement records are available "
                "for the candidate planned date."
            ),
            "planned_date": planned_date_value,
            "candidate": candidate,
            "safety": safety_payload,
            "safety_mapping_gap": safety_mapping_gap,
            "data_coverage": {
                "movement_records": 0,
                "same_track_records": 0,
                "movement_min_date": (
                    movement_df["date"].min()
                ),
                "movement_max_date": (
                    movement_df["date"].max()
                ),
            },
            "train_conflicts": [],
            "available_windows": [],
        }

    minimum_block_duration = max(
        [r["minimum_block_duration_minutes"]
         for r in rules] or [0]
    )

    clearance = max(
        [r["minimum_clearance_minutes"]
         for r in rules] or [0]
    )

    requested_duration = float(
        candidate.get("total_duration_minutes") or 0
    )

    required_duration = max(
        requested_duration,
        minimum_block_duration,
    )

    window_start = pd.to_datetime(
        candidate.get("window_start"),
        utc=True,
        errors="coerce",
    )

    window_finish = pd.to_datetime(
        candidate.get("window_finish"),
        utc=True,
        errors="coerce",
    )

    if (
        pd.isna(window_start)
        or pd.isna(window_finish)
    ):
        return {
            "block_id": block_id,
            "status": "DATA_GAP",
            "reason": "Candidate has no valid planning window.",
            "candidate": candidate,
            "safety": safety,
        }

    windows, occupied, feasible = _find_windows(
        window_start=window_start,
        window_finish=window_finish,
        duration_minutes=required_duration,
        clearance_minutes=clearance,
        movements=movement_matches,
    )

    conflict_count = len(occupied)

    if feasible:
        status = "OPERATIONALLY_FEASIBLE"
        reason = (
            "A train-free maintenance window exists after "
            "applying the mapped safety clearance."
        )
    elif conflict_count:
        status = "TRAIN_CONFLICT"
        reason = (
            "No continuous maintenance window of the "
            "required duration remains after train occupancy "
            "and clearance are applied."
        )
    else:
        status = "WINDOW_INSUFFICIENT"
        reason = (
            "The maintenance planning window is shorter than "
            "the required operational duration."
        )

    return {
        "block_id": block_id,
        "status": status,
        "reason": reason,
        "planned_date": planned_date_value,
        "section_id": section,
        "track_id": track,
        "candidate": candidate,
        "data_coverage": {
            "movement_records": int(len(date_movements)),
            "same_track_records": int(
                len(movement_matches)
            ),
            "movement_min_date": movement_df["date"].min(),
            "movement_max_date": movement_df["date"].max(),
        },
        "safety": {
            "status": "EVALUATED",
            "minimum_block_duration_minutes":
                minimum_block_duration,
            "minimum_clearance_minutes": clearance,
            "required_duration_minutes":
                required_duration,
            "rules": rules,
        },
        "train_conflicts": [
            {
                "movement_id": item["movement_id"],
                "train_id": item["train_id"],
                "occupied_start": item["start"].isoformat(),
                "occupied_finish": item["finish"].isoformat(),
            }
            for item in occupied
        ],
        "available_windows": [
            {
                "start": item["start"].isoformat(),
                "finish": item["finish"].isoformat(),
                "duration_minutes":
                    item["duration_minutes"],
            }
            for item in windows
        ],
        "operational_constraints": {
            "train_occupancy": "evaluated",
            "safety_clearance": "evaluated",
            "minimum_block_duration": "evaluated",
            "crew_conflicts": "not_evaluated",
            "machine_conflicts": "not_evaluated",
            "material_conflicts": "not_evaluated",
            "signalling_authority": "not_evaluated",
        },
    }
