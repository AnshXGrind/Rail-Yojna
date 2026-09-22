
from __future__ import annotations

import hashlib
from typing import Any
from functools import lru_cache

import pandas as pd

from backend.app.services.planning_service import load_plan


@lru_cache(maxsize=1)
def _cached_plan():
    return load_plan()


def _clean(value: Any):
    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass

    return value


def _iso(value):
    value = pd.to_datetime(value, utc=True, errors="coerce")

    if pd.isna(value):
        return None

    return value.isoformat()


def _priority_score(value) -> float:
    mapping = {
        "P1": 1.00,
        "P2": 0.75,
        "P3": 0.50,
        "P4": 0.25,
    }

    return mapping.get(str(value).upper(), 0.0)


def _candidate_id(
    planned_date,
    section_id,
    track_id,
    task_ids,
) -> str:
    raw = "|".join(
        [
            str(planned_date),
            str(section_id),
            str(track_id),
            ",".join(sorted(map(str, task_ids))),
        ]
    )

    digest = hashlib.sha1(raw.encode()).hexdigest()[:8]

    date_part = str(planned_date).replace("-", "")
    section_part = str(section_id or "UNKNOWN").replace(" ", "_")
    track_part = str(track_id or "UNKNOWN").replace(" ", "_")

    return f"BLK-{date_part}-{section_part}-{track_part}-{digest}"


def _base_block_rows(df: pd.DataFrame, planned_date: str | None = None):
    blocks = df[
        (df["selected"] == 1)
        & (df["block_required"].astype(bool))
    ].copy()

    if planned_date:
        dates = pd.to_datetime(
            blocks["planned_date"],
            utc=True,
            errors="coerce",
        ).dt.strftime("%Y-%m-%d")

        blocks = blocks[dates == planned_date]

    return blocks


def _task_payload(row) -> dict:
    return {
        "task_id": _clean(row["task_id"]),
        "asset_id": _clean(row["asset_id"]),
        "section_id": _clean(row.get("section_id")),
        "track_id": _clean(row.get("track_id")),
        "task_type": _clean(row.get("task_type")),
        "priority": _clean(row.get("priority")),
        "risk": float(_clean(row.get("calibrated_risk")) or 0),
        "condition_score": float(
            _clean(row.get("condition_score")) or 0
        ),
        "criticality": float(
            _clean(row.get("criticality")) or 0
        ),
        "duration_minutes": float(
            _clean(row.get("estimated_duration_minutes")) or 0
        ),
        "planned_date": _iso(row.get("planned_date")),
        "earliest_start": _iso(row.get("earliest_start")),
        "latest_finish": _iso(row.get("latest_finish")),
    }


def _window_minutes(start, finish) -> float:
    if pd.isna(start) or pd.isna(finish):
        return 0.0

    return max(
        0.0,
        (finish - start).total_seconds() / 60.0,
    )


def _make_candidate(group: pd.DataFrame) -> dict | None:
    if group.empty:
        return None

    group = group.copy()

    group["start_sort"] = pd.to_datetime(
        group["earliest_start"],
        utc=True,
        errors="coerce",
    )

    group["finish_sort"] = pd.to_datetime(
        group["latest_finish"],
        utc=True,
        errors="coerce",
    )

    if group["start_sort"].isna().any():
        return None

    if group["finish_sort"].isna().any():
        return None

    common_start = group["start_sort"].max()
    common_finish = group["finish_sort"].min()

    available_minutes = _window_minutes(
        common_start,
        common_finish,
    )

    total_minutes = float(
        group["estimated_duration_minutes"].fillna(0).sum()
    )

    feasible = (
        available_minutes > 0
        and total_minutes <= available_minutes
    )

    task_ids = group["task_id"].astype(str).tolist()

    risk_covered = float(
        group["calibrated_risk"].fillna(0).sum()
    )

    avg_risk = (
        risk_covered / len(group)
        if len(group)
        else 0.0
    )

    priority_score = float(
        group["priority"]
        .map(_priority_score)
        .mean()
    )

    criticality = float(
        group.get(
            "criticality",
            pd.Series([0] * len(group), index=group.index),
        )
        .fillna(0)
        .mean()
    )

    utilization = (
        total_minutes / available_minutes
        if available_minutes > 0
        else 0.0
    )

    score = (
        min(risk_covered, 5.0) / 5.0 * 0.45
        + priority_score * 0.20
        + min(criticality, 1.0) * 0.15
        + min(utilization, 1.0) * 0.20
    )

    section_id = _clean(group["section_id"].iloc[0])
    track_id = _clean(group["track_id"].iloc[0])
    planned_date = _iso(group["planned_date"].iloc[0])

    reasons = []

    if risk_covered >= 0.20:
        reasons.append("meaningful predicted-risk coverage")

    if priority_score >= 0.75:
        reasons.append("high-priority maintenance included")

    if criticality >= 0.70:
        reasons.append("high-criticality assets included")

    if utilization >= 0.50:
        reasons.append("good use of available planning window")

    if len(group) > 1:
        reasons.append("compatible same-track tasks can be grouped")

    if not reasons:
        reasons.append("fits the available maintenance planning window")

    return {
        "block_id": _candidate_id(
            planned_date,
            section_id,
            track_id,
            task_ids,
        ),
        "planned_date": planned_date,
        "section_id": section_id,
        "track_id": track_id,
        "task_ids": task_ids,
        "tasks": [
            _task_payload(row)
            for _, row in group.iterrows()
        ],
        "task_count": int(len(group)),
        "total_duration_minutes": total_minutes,
        "total_duration_hours": total_minutes / 60.0,
        "window_start": _iso(common_start),
        "window_finish": _iso(common_finish),
        "available_window_minutes": available_minutes,
        "utilization": utilization,
        "risk_covered": risk_covered,
        "average_risk": avg_risk,
        "priority_score": priority_score,
        "criticality_score": criticality,
        "score": score,
        "feasible": bool(feasible),
        "status": (
            "FEASIBLE"
            if feasible
            else "WINDOW_INSUFFICIENT"
        ),
        "reasons": reasons,
        "constraint_status": {
            "maintenance_window": "evaluated",
            "same_track_grouping": "evaluated",
            "train_conflicts": "not_evaluated",
            "crew_conflicts": "not_evaluated",
            "machine_conflicts": "not_evaluated",
            "material_conflicts": "not_evaluated",
            "signalling_authority": "not_evaluated",
        },
    }


def generate_block_candidates(
    *,
    planned_date: str | None = None,
    section_id: str | None = None,
    track_id: str | None = None,
    limit: int = 50,
) -> dict:

    df = _base_block_rows(
        _cached_plan(),
        planned_date,
    ).copy()

    if section_id:
        df = df[
            df["section_id"].astype(str) == str(section_id)
        ]

    if track_id:
        df = df[
            df["track_id"].astype(str) == str(track_id)
        ]

    if df.empty:
        return {
            "items": [],
            "summary": {
                "candidates": 0,
                "feasible": 0,
                "not_feasible": 0,
            },
            "data_mode": "synthetic",
            "planner_version": "maintenance_plan_v2",
        }

    df["start_sort"] = pd.to_datetime(
        df["earliest_start"],
        utc=True,
        errors="coerce",
    )

    df["finish_sort"] = pd.to_datetime(
        df["latest_finish"],
        utc=True,
        errors="coerce",
    )

    df["duration_num"] = pd.to_numeric(
        df["estimated_duration_minutes"],
        errors="coerce",
    ).fillna(0)

    df["risk_num"] = pd.to_numeric(
        df["calibrated_risk"],
        errors="coerce",
    ).fillna(0)

    df = df.dropna(
        subset=["start_sort", "finish_sort"]
    )

    candidates = []

    for group_key, group in df.groupby(
        ["planned_date", "section_id", "track_id"],
        dropna=False,
        sort=False,
    ):
        group = group.sort_values(
            ["start_sort", "priority", "risk_num"],
            ascending=[True, True, False],
        )

        current = []

        common_start = None
        common_finish = None
        total_minutes = 0.0

        for _, row in group.iterrows():
            row_start = row["start_sort"]
            row_finish = row["finish_sort"]
            row_duration = float(row["duration_num"])

            new_start = (
                row_start
                if common_start is None
                else max(common_start, row_start)
            )

            new_finish = (
                row_finish
                if common_finish is None
                else min(common_finish, row_finish)
            )

            available_minutes = max(
                0.0,
                (
                    new_finish - new_start
                ).total_seconds() / 60.0,
            )

            new_total = total_minutes + row_duration

            # Start a new block if adding this task breaks
            # the common maintenance window.
            if current and new_total > available_minutes:
                candidate = _make_candidate(
                    pd.DataFrame(current)
                )

                if candidate:
                    candidates.append(candidate)

                current = [row]
                common_start = row_start
                common_finish = row_finish
                total_minutes = row_duration
            else:
                current.append(row)
                common_start = new_start
                common_finish = new_finish
                total_minutes = new_total

        if current:
            candidate = _make_candidate(
                pd.DataFrame(current)
            )

            if candidate:
                candidates.append(candidate)

    # One candidate per unique task bundle.
    unique = {}

    for candidate in candidates:
        key = (
            candidate["planned_date"],
            candidate["section_id"],
            candidate["track_id"],
            tuple(sorted(candidate["task_ids"])),
        )

        unique[key] = candidate

    candidates = list(unique.values())

    candidates.sort(
        key=lambda item: (
            bool(item["feasible"]),
            float(item["score"]),
            float(item["risk_covered"]),
        ),
        reverse=True,
    )

    candidates = candidates[:max(1, min(int(limit), 200))]

    feasible_count = sum(
        bool(item["feasible"])
        for item in candidates
    )

    return {
        "items": candidates,
        "summary": {
            "candidates": len(candidates),
            "feasible": feasible_count,
            "not_feasible": (
                len(candidates) - feasible_count
            ),
        },
        "data_mode": "synthetic",
        "planner_version": "maintenance_plan_v2",
        "safety_note": (
            "Candidates are decision-support recommendations. "
            "Train occupancy, signalling authority, crew, "
            "machine and material conflicts are not currently "
            "evaluated."
        ),
    }


def get_block_plan(
    *,
    planned_date: str | None = None,
    limit: int = 500,
) -> dict:

    df = load_plan()

    blocks = _base_block_rows(
        df,
        planned_date,
    )

    blocks["planned_date_sort"] = pd.to_datetime(
        blocks["planned_date"],
        utc=True,
        errors="coerce",
    )

    blocks["earliest_sort"] = pd.to_datetime(
        blocks["earliest_start"],
        utc=True,
        errors="coerce",
    )

    blocks = blocks.sort_values(
        [
            "planned_date_sort",
            "earliest_sort",
            "section_id",
            "track_id",
        ]
    ).head(
        max(1, min(int(limit), 1000))
    )

    items = []

    for _, row in blocks.iterrows():
        items.append({
            "task_id": _clean(row["task_id"]),
            "asset_id": _clean(row["asset_id"]),
            "section_id": _clean(row.get("section_id")),
            "track_id": _clean(row.get("track_id")),
            "task_type": _clean(row["task_type"]),
            "priority": _clean(row["priority"]),
            "risk": _clean(row["calibrated_risk"]),
            "condition_score": _clean(row["condition_score"]),
            "duration_minutes": _clean(
                row["estimated_duration_minutes"]
            ),
            "planned_date": _iso(row["planned_date"]),
            "earliest_start": _iso(
                row.get("earliest_start")
            ),
            "latest_finish": _iso(
                row.get("latest_finish")
            ),
            "decision": _clean(row.get("decision")),
        })

    # Informational overlap detection only.
    conflicts = []

    conflict_df = blocks.dropna(
        subset=["earliest_sort"]
    ).copy()

    for track_id, group in conflict_df.groupby(
        conflict_df["track_id"].astype(str)
    ):
        group = group.sort_values("earliest_sort")
        rows = list(group.iterrows())

        for i in range(len(rows)):
            _, left = rows[i]

            left_start = left["earliest_sort"]

            left_finish = pd.to_datetime(
                left.get("latest_finish"),
                utc=True,
                errors="coerce",
            )

            if pd.isna(left_finish):
                continue

            for j in range(i + 1, len(rows)):
                _, right = rows[j]

                right_start = right["earliest_sort"]

                if pd.isna(right_start):
                    continue

                if right_start > left_finish:
                    break

                conflicts.append({
                    "track_id": track_id,
                    "task_a": _clean(left["task_id"]),
                    "task_b": _clean(right["task_id"]),
                    "section_a": _clean(
                        left.get("section_id")
                    ),
                    "section_b": _clean(
                        right.get("section_id")
                    ),
                })

                if len(conflicts) >= 100:
                    break

            if len(conflicts) >= 100:
                break

        if len(conflicts) >= 100:
            break

    unique_dates = (
        pd.to_datetime(
            df.loc[
                (df["selected"] == 1)
                & (df["block_required"].astype(bool)),
                "planned_date",
            ],
            utc=True,
            errors="coerce",
        )
        .dropna()
        .dt.strftime("%Y-%m-%d")
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    summary_source = _base_block_rows(df)

    return {
        "items": items,
        "summary": {
            "block_tasks": int(len(summary_source)),
            "planned_hours": float(
                summary_source[
                    "estimated_duration_minutes"
                ].sum() / 60
            ),
            "sections": int(
                summary_source["section_id"].nunique()
            ),
            "tracks": int(
                summary_source["track_id"].nunique()
            ),
            "schedule_overlaps": int(len(conflicts)),
        },
        "available_dates": unique_dates,
        "conflicts": conflicts,
        "data_mode": "synthetic",
        "planner_version": "maintenance_plan_v2",
        "map": {
            "network_source": (
                "OpenStreetMap + OpenRailwayMap"
            ),
            "asset_coordinates_available": False,
            "note": (
                "Current synthetic planning records do not "
                "contain geographic coordinates for "
                "asset/task mapping."
            ),
        },
    }
