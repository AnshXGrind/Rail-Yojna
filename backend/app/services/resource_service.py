
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from backend.app.services.block_service import (
    generate_block_candidates,
)
from backend.app.services.operational_service import (
    _safety_rule_for_tasks,
)


BASE = "data/raw/rail_yojna_data"


@lru_cache(maxsize=1)
def _resources():
    return pd.read_csv(
        f"{BASE}/resources.csv"
    )


@lru_cache(maxsize=1)
def _availability():
    df = pd.read_csv(
        f"{BASE}/resource_availability.csv"
    )

    for col in [
        "available_start",
        "available_end",
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
def _machines():
    return pd.read_csv(
        f"{BASE}/machines.csv"
    )


@lru_cache(maxsize=1)
def _materials():
    return pd.read_csv(
        f"{BASE}/materials.csv"
    )


@lru_cache(maxsize=1)
def _task_resources():
    return pd.read_csv(
        f"{BASE}/task_resources.csv"
    )


@lru_cache(maxsize=1)
def _task_materials():
    return pd.read_csv(
        f"{BASE}/task_materials.csv"
    )


def _find_candidate(block_id: str, planned_date=None):
    result = generate_block_candidates(
        planned_date=planned_date,
        limit=200,
    )

    for item in result.get("items", []):
        if item.get("block_id") == block_id:
            return item

    return None


def _resource_candidates_for_tasks(task_ids):
    assignments = _task_resources()

    return assignments[
        assignments["task_id"].astype(str).isin(
            [str(x) for x in task_ids]
        )
    ].copy()


def _material_requirements_for_tasks(task_ids):
    materials = _task_materials()

    return materials[
        materials["task_id"].astype(str).isin(
            [str(x) for x in task_ids]
        )
    ].copy()


def assess_resources(
    block_id: str,
    *,
    planned_date: str | None = None,
) -> dict:

    candidate = _find_candidate(
        block_id,
        planned_date,
    )

    if candidate is None:
        return {
            "block_id": block_id,
            "status": "NOT_FOUND",
            "reason": "Block candidate not found.",
        }

    task_ids = candidate.get("task_ids", [])
    tasks = candidate.get("tasks", [])

    assignment_df = _resource_candidates_for_tasks(
        task_ids
    )

    material_df = _material_requirements_for_tasks(
        task_ids
    )

    resources = _resources()
    availability = _availability()
    materials = _materials()

    # ------------------------------------------------------------
    # Historical task-resource evidence
    # ------------------------------------------------------------

    missing_task_resource_mapping = [
        task_id
        for task_id in task_ids
        if assignment_df[
            assignment_df["task_id"].astype(str)
            == str(task_id)
        ].empty
    ]

    resource_checks = []
    resource_conflicts = []
    resource_data_gaps = []

    if not assignment_df.empty:
        joined = assignment_df.merge(
            resources,
            on="resource_id",
            how="left",
            suffixes=("", "_resource"),
        )

        for _, row in joined.iterrows():
            resource_id = str(row["resource_id"])
            resource_type = row.get("resource_type")
            operating_status = row.get(
                "operating_status"
            )

            planned_start = pd.to_datetime(
                row.get("planned_start"),
                utc=True,
                errors="coerce",
            )
            planned_end = pd.to_datetime(
                row.get("planned_end"),
                utc=True,
                errors="coerce",
            )

            task_id = str(row["task_id"])

            date_value = (
                planned_date
                or candidate["planned_date"][:10]
            )

            avail = availability[
                (
                    availability["resource_id"]
                    .astype(str)
                    == resource_id
                )
                &
                (
                    availability["date"].astype(str)
                    == str(date_value)
                )
            ].copy()

            if avail.empty:
                resource_data_gaps.append({
                    "task_id": task_id,
                    "resource_id": resource_id,
                    "resource_type": resource_type,
                    "reason": (
                        "No availability record for the "
                        "candidate date."
                    ),
                })

                continue

            if pd.isna(planned_start):
                planned_start = pd.to_datetime(
                    candidate["window_start"],
                    utc=True,
                )

            if pd.isna(planned_end):
                planned_end = pd.to_datetime(
                    candidate["window_finish"],
                    utc=True,
                )

            available = False

            for _, av in avail.iterrows():
                av_start = av["available_start"]
                av_end = av["available_end"]

                if (
                    pd.notna(av_start)
                    and pd.notna(av_end)
                    and av_start <= planned_start
                    and av_end >= planned_end
                ):
                    available = True
                    break

            check = {
                "task_id": task_id,
                "resource_id": resource_id,
                "resource_type": resource_type,
                "role": row.get("role"),
                "operating_status": operating_status,
                "available_for_window": available,
            }

            resource_checks.append(check)

            if not available:
                resource_conflicts.append(check)

            if str(operating_status).lower() not in {
                "available",
                "maintenance",
            }:
                resource_conflicts.append({
                    **check,
                    "reason": "resource_not_available_status",
                })

    # ------------------------------------------------------------
    # Material checks
    # ------------------------------------------------------------

    material_checks = []
    material_conflicts = []
    material_data_gaps = []

    if not material_df.empty:
        for _, row in material_df.iterrows():
            material_id = str(row["material_id"])

            required = float(
                pd.to_numeric(
                    row["quantity_required"],
                    errors="coerce",
                )
                or 0
            )

            material_match = materials[
                materials["material_id"].astype(str)
                == material_id
            ]

            if material_match.empty:
                material_data_gaps.append({
                    "task_id": str(row["task_id"]),
                    "material_id": material_id,
                    "reason": "Material master record missing.",
                })
                continue

            material = material_match.iloc[0]

            available_qty = float(
                pd.to_numeric(
                    material["quantity_available"],
                    errors="coerce",
                )
                or 0
            )

            reserved_qty = float(
                pd.to_numeric(
                    material["reserved_quantity"],
                    errors="coerce",
                )
                or 0
            )

            usable_qty = max(
                0.0,
                available_qty - reserved_qty,
            )

            sufficient = usable_qty >= required

            check = {
                "task_id": str(row["task_id"]),
                "material_id": material_id,
                "required_quantity": required,
                "usable_quantity": usable_qty,
                "unit": material.get("unit"),
                "sufficient": sufficient,
                "storage_station_id": material.get(
                    "storage_station_id"
                ),
            }

            material_checks.append(check)

            if not sufficient:
                material_conflicts.append(check)

    # ------------------------------------------------------------
    # Safety personnel cross-check
    # ------------------------------------------------------------

    safety = _safety_rule_for_tasks(tasks)
    required_personnel = 0

    if safety.get("rules"):
        required_personnel = max(
            int(rule["required_personnel"])
            for rule in safety["rules"]
        )

    distinct_crew = set()

    if not assignment_df.empty:
        resource_join = assignment_df.merge(
            resources,
            on="resource_id",
            how="left",
        )

        for _, row in resource_join.iterrows():
            rtype = str(
                row.get("resource_type", "")
            ).lower()

            capability = str(
                row.get("capability", "")
            ).lower()

            if "crew" in rtype or "crew" in capability:
                distinct_crew.add(
                    str(row["resource_id"])
                )

    crew_count = len(distinct_crew)

    personnel_status = (
        "SATISFIED"
        if crew_count >= required_personnel
        else "INSUFFICIENT"
        if assignment_df.empty is False
        else "DATA_GAP"
    )

    # ------------------------------------------------------------
    # Overall resource decision
    # ------------------------------------------------------------

    if missing_task_resource_mapping:
        status = "RESOURCE_DATA_GAP"
        reason = (
            "At least one candidate task has no historical "
            "task-resource mapping. Resource feasibility "
            "cannot be established."
        )
    elif resource_data_gaps or material_data_gaps:
        status = "RESOURCE_DATA_GAP"
        reason = (
            "Resource or material availability data is missing "
            "for the candidate date."
        )
    elif resource_conflicts or material_conflicts:
        status = "RESOURCE_CONFLICT"
        reason = (
            "One or more required resources or materials "
            "cannot support the candidate block."
        )
    elif personnel_status == "INSUFFICIENT":
        status = "RESOURCE_CONFLICT"
        reason = (
            "The safety-derived minimum personnel requirement "
            "is not satisfied by the mapped crew resources."
        )
    else:
        status = "RESOURCE_FEASIBLE"
        reason = (
            "Mapped historical resources and materials are "
            "compatible with the candidate block."
        )

    return {
        "block_id": block_id,
        "status": status,
        "reason": reason,
        "candidate": {
            "section_id": candidate["section_id"],
            "track_id": candidate["track_id"],
            "planned_date": candidate["planned_date"],
            "task_ids": task_ids,
        },
        "resource_summary": {
            "mapped_resource_assignments": int(
                len(assignment_df)
            ),
            "distinct_crew": crew_count,
            "required_personnel": required_personnel,
            "personnel_status": personnel_status,
            "resource_conflicts": len(
                resource_conflicts
            ),
            "resource_data_gaps": len(
                resource_data_gaps
            ),
        },
        "material_summary": {
            "material_requirements": int(
                len(material_df)
            ),
            "material_conflicts": len(
                material_conflicts
            ),
            "material_data_gaps": len(
                material_data_gaps
            ),
        },
        "resource_checks": resource_checks[:100],
        "resource_conflict_items": resource_conflicts[:100],
        "resource_data_gap_items": resource_data_gaps[:100],
        "material_checks": material_checks[:100],
        "material_conflict_items": material_conflicts[:100],
        "material_data_gap_items": material_data_gaps[:100],
        "evidence": {
            "resource_requirements_source":
                "task_resources historical assignments",
            "material_requirements_source":
                "task_materials",
            "availability_source":
                "resource_availability",
            "personnel_requirement_source":
                "safety_constraints",
        },
        "safety_note": (
            "Resource feasibility is decision support. "
            "Historical task-resource assignments are used "
            "as evidence of required resource classes; they "
            "are not treated as authoritative future crew "
            "dispatch instructions."
        ),
    }
