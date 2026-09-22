
from __future__ import annotations

from backend.app.services.window_optimizer import optimize_windows
from typing import Any

from backend.app.services.block_service import (
    generate_block_candidates,
)
from backend.app.services.operational_service import (
    assess_block,
)
from backend.app.services.resource_service import (
    assess_resources,
)


def _status(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    return str(value).upper()


def _base_assess_block_completely(
    block_id: str,
    *,
    planned_date: str | None = None,
) -> dict:

    candidate_result = generate_block_candidates(
        planned_date=planned_date,
        limit=200,
    )

    candidate = next(
        (
            item
            for item in candidate_result.get("items", [])
            if item.get("block_id") == block_id
        ),
        None,
    )

    if candidate is None:
        return {
            "block_id": block_id,
            "overall_status": "NOT_FOUND",
            "reason": "Block candidate not found.",
        }

    operational = assess_block(
        block_id,
        planned_date=planned_date,
    )

    resources = assess_resources(
        block_id,
        planned_date=planned_date,
    )

    maintenance_status = (
        "PASS"
        if candidate.get("feasible")
        else "FAIL"
    )

    safety = operational.get("safety", {})
    safety_status = _status(
        safety.get("status")
    )

    train_status = _status(
        operational.get("status")
    )

    resource_status = _status(
        resources.get("status")
    )

    material_summary = resources.get(
        "material_summary",
        {},
    )

    material_conflicts = int(
        material_summary.get(
            "material_conflicts",
            0,
        ) or 0
    )

    material_data_gaps = int(
        material_summary.get(
            "material_data_gaps",
            0,
        ) or 0
    )

    if material_conflicts > 0:
        material_result = "CONFLICT"
    elif material_data_gaps > 0:
        material_result = "DATA_GAP"
    else:
        material_result = "PASS"

    # --------------------------------------------------------
    # Normalize component statuses.
    # --------------------------------------------------------

    if safety_status == "EVALUATED":
        safety_result = "PASS"
    elif safety_status in {
        "NOT_MAPPED",
        "DATA_GAP",
        "SAFETY_MAPPING_GAP",
        "PARTIAL",
    }:
        safety_result = "DATA_GAP"
    else:
        safety_result = "REVIEW"

    if train_status == "OPERATIONALLY_FEASIBLE":
        train_result = "PASS"
    elif train_status == "TRAIN_CONFLICT":
        train_result = "CONFLICT"
    elif train_status in {
        "DATA_GAP",
        "NOT_FOUND",
    }:
        train_result = "DATA_GAP"
    else:
        train_result = "REVIEW"

    if resource_status == "RESOURCE_FEASIBLE":
        resource_result = "PASS"
    elif resource_status == "RESOURCE_CONFLICT":
        resource_result = "CONFLICT"
    elif resource_status in {
        "RESOURCE_DATA_GAP",
        "DATA_GAP",
    }:
        resource_result = "DATA_GAP"
    else:
        resource_result = "REVIEW"

    # --------------------------------------------------------
    # Overall decision.
    #
    # DATA_GAP is deliberately not converted into PASS.
    # --------------------------------------------------------

    if maintenance_status == "FAIL":
        overall = "MAINTENANCE_INFEASIBLE"

    elif train_result == "CONFLICT":
        overall = "TRAIN_CONFLICT"

    elif resource_result == "CONFLICT":
        overall = "RESOURCE_CONFLICT"

    elif material_result == "CONFLICT":
        overall = "MATERIAL_CONFLICT"

    elif safety_result == "REVIEW":
        overall = "SAFETY_REVIEW"

    elif safety_result == "DATA_GAP":
        overall = "SAFETY_DATA_GAP"

    elif train_result == "DATA_GAP":
        overall = "TRAIN_DATA_GAP"

    elif resource_result == "DATA_GAP":
        overall = "RESOURCE_DATA_GAP"

    elif material_result == "DATA_GAP":
        overall = "MATERIAL_DATA_GAP"

    else:
        overall = "READY_FOR_HUMAN_REVIEW"

    reasons = []

    if maintenance_status == "PASS":
        reasons.append(
            "maintenance duration fits the planning window"
        )
    else:
        reasons.append(
            "maintenance duration does not fit the planning window"
        )

    if safety_result == "PASS":
        reasons.append(
            "applicable safety constraints were evaluated"
        )
    elif safety_result == "DATA_GAP":
        reasons.append(
            "safety mapping is incomplete"
        )

    if train_result == "PASS":
        reasons.append(
            "a train-free operational window was found"
        )
    elif train_result == "CONFLICT":
        reasons.append(
            "train occupancy prevents the candidate window"
        )
    elif train_result == "DATA_GAP":
        reasons.append(
            "train movement data is unavailable for the planned date"
        )

    if resource_result == "PASS":
        reasons.append(
            "mapped resource availability supports the candidate"
        )
    elif resource_result == "CONFLICT":
        reasons.append(
            "resource availability blocks the candidate"
        )
    elif resource_result == "DATA_GAP":
        reasons.append(
            "resource availability evidence is incomplete"
        )

    if material_result == "PASS":
        reasons.append(
            "required materials are available"
        )
    elif material_result == "CONFLICT":
        reasons.append(
            "one or more required materials are insufficient"
        )
    elif material_result == "DATA_GAP":
        reasons.append(
            "material availability evidence is incomplete"
        )

    return {
        "block_id": block_id,
        "overall_status": overall,
        "reasons": reasons,

        "maintenance": {
            "status": maintenance_status,
            "duration_hours": candidate.get(
                "total_duration_hours"
            ),
            "window_start": candidate.get(
                "window_start"
            ),
            "window_finish": candidate.get(
                "window_finish"
            ),
            "task_count": candidate.get(
                "task_count"
            ),
            "risk_covered": candidate.get(
                "risk_covered"
            ),
        },

        "safety": {
            "status": safety_result,
            "minimum_block_duration_minutes":
                safety.get(
                    "minimum_block_duration_minutes"
                ),
            "minimum_clearance_minutes":
                safety.get(
                    "minimum_clearance_minutes"
                ),
            "required_duration_minutes":
                safety.get(
                    "required_duration_minutes"
                ),
            "rules": safety.get("rules", []),
        },

        "trains": {
            "status": train_result,
            "assessment_status": operational.get(
                "status"
            ),
            "reason": operational.get(
                "reason"
            ),
            "data_coverage": operational.get(
                "data_coverage", {}
            ),
            "conflicts": operational.get(
                "train_conflicts", []
            ),
            "available_windows": operational.get(
                "available_windows", []
            ),
        },

        "resources": {
            "status": resource_result,
            "reason": resources.get(
                "reason"
            ),
            "summary": resources.get(
                "resource_summary", {}
            ),
            "conflicts": resources.get(
                "resource_conflict_items", []
            ),
            "data_gaps": resources.get(
                "resource_data_gap_items", []
            ),
        },

        "materials": {
            "status": material_result,
            "summary": resources.get(
                "material_summary", {}
            ),
            "conflicts": resources.get(
                "material_conflict_items", []
            ),
            "data_gaps": resources.get(
                "material_data_gap_items", []
            ),
        },

        "candidate": candidate,

        "planner_note": (
            "This assessment is decision support only. "
            "It does not grant possession, issue signalling "
            "commands, authorize train movement, or create "
            "official railway block authority."
        ),

        "data_mode": "synthetic",
        "planner_version": "maintenance_plan_v2",
    }

# Phase 22 wrapper:
# Keep the original unified assessment as the authoritative component
# assessment, then independently evaluate alternative operational windows.
def assess_block_completely(
    block_id: str,
    planned_date,
):
    result = _base_assess_block_completely(
        block_id=block_id,
        planned_date=planned_date,
    )

    candidate = result.get("candidate")

    if not candidate:
        result["alternative_windows"] = []
        result["window_optimizer_status"] = "DATA_GAP"
        result["window_optimizer"] = {
            "status": "DATA_GAP",
            "alternative_windows": [],
            "reason": "candidate_not_returned_by_assessment",
        }
        return result

    try:
        window_result = optimize_windows(
            candidate,
            include_resource_check=True,
            limit=10,
        )
    except Exception as exc:
        window_result = {
            "status": "DATA_GAP",
            "alternative_windows": [],
            "error": str(exc),
        }

    result["alternative_windows"] = window_result.get(
        "alternative_windows",
        [],
    )
    result["window_optimizer_status"] = window_result.get(
        "status",
    )
    result["window_optimizer"] = window_result

    # Preserve independent component states.
    result.setdefault("safety", {})
    result.setdefault("trains", {})
    result.setdefault("resources", {})
    result.setdefault("materials", {})

    return result

