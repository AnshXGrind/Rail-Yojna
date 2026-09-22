
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from backend.app.services.block_service import (
    generate_block_candidates,
)
from backend.app.services.block_assessment_service import (
    assess_block_completely,
)


STATUS_RANK = {
    "READY_FOR_HUMAN_REVIEW": 1.00,
    "TRAIN_CONFLICT": 0.25,
    "RESOURCE_CONFLICT": 0.20,
    "SAFETY_REVIEW": 0.15,
    "TRAIN_DATA_GAP": 0.10,
    "RESOURCE_DATA_GAP": 0.10,
    "SAFETY_DATA_GAP": 0.10,
    "MAINTENANCE_INFEASIBLE": 0.00,
    "NOT_FOUND": 0.00,
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _priority_score(priority) -> float:
    return {
        "P1": 1.00,
        "P2": 0.75,
        "P3": 0.50,
        "P4": 0.25,
    }.get(str(priority).upper(), 0.0)


def _candidate_score(candidate: dict, assessment: dict) -> dict:
    maintenance = assessment.get("maintenance", {})
    status = assessment.get("overall_status", "UNKNOWN")

    risk = _clamp(
        float(candidate.get("risk_covered") or 0)
        / 1.0
    )

    criticality = _clamp(
        float(candidate.get("criticality_score") or 0)
    )

    priority = _clamp(
        float(candidate.get("priority_score") or 0)
    )

    utilization = _clamp(
        float(candidate.get("utilization") or 0)
    )

    task_bundle = _clamp(
        float(candidate.get("task_count") or 0)
        / 5.0
    )

    status_score = STATUS_RANK.get(status, 0.0)

    # Risk and criticality dominate.
    raw = (
        risk * 0.30
        + criticality * 0.20
        + priority * 0.15
        + utilization * 0.10
        + task_bundle * 0.10
        + status_score * 0.15
    )

    # Never allow an unknown operational state to become
    # a top recommendation simply through high risk.
    operationally_unverified = status in {
        "TRAIN_DATA_GAP",
        "RESOURCE_DATA_GAP",
        "SAFETY_DATA_GAP",
        "MATERIAL_DATA_GAP",
        "SAFETY_REVIEW",
        "MATERIAL_CONFLICT",
        "TRAIN_CONFLICT",
        "RESOURCE_CONFLICT",
    }

    if status in {
        "TRAIN_CONFLICT",
        "RESOURCE_CONFLICT",
        "MATERIAL_CONFLICT",
        "MAINTENANCE_INFEASIBLE",
    }:
        raw *= 0.20
    elif operationally_unverified:
        raw *= 0.55

    return {
        "recommendation_score": round(
            raw,
            6,
        ),
        "score_components": {
            "risk": round(risk, 6),
            "criticality": round(criticality, 6),
            "priority": round(priority, 6),
            "window_utilization": round(
                utilization,
                6,
            ),
            "task_bundle": round(
                task_bundle,
                6,
            ),
            "operational_status": status,
        },
        "operationally_verified": not operationally_unverified,
        "assessment_status": status,
    }


def _recommendation_reason(
    candidate: dict,
    assessment: dict,
    score: dict,
) -> list[str]:

    reasons = []

    if float(candidate.get("risk_covered") or 0) >= 0.20:
        reasons.append(
            "covers meaningful predicted failure risk"
        )

    if float(candidate.get("criticality_score") or 0) >= 0.70:
        reasons.append(
            "covers high-criticality assets"
        )

    if str(candidate.get("priority")) == "P1":
        reasons.append(
            "contains high-priority maintenance work"
        )

    if int(candidate.get("task_count") or 0) >= 2:
        reasons.append(
            "bundles compatible maintenance tasks"
        )

    status = assessment.get(
        "overall_status"
    )

    if status == "READY_FOR_HUMAN_REVIEW":
        reasons.append(
            "passes the currently implemented "
            "operational checks"
        )
    elif status.endswith("DATA_GAP"):
        reasons.append(
            "requires additional operational data "
            "before clearance"
        )
    elif status in {
        "TRAIN_CONFLICT",
        "RESOURCE_CONFLICT",
    }:
        reasons.append(
            "has an identified operational conflict"
        )

    return reasons


def recommend_blocks(
    *,
    planned_date: str | None = None,
    section_id: str | None = None,
    track_id: str | None = None,
    candidate_limit: int = 30,
    assessment_limit: int = 15,
) -> dict:

    candidates = generate_block_candidates(
        planned_date=planned_date,
        section_id=section_id,
        track_id=track_id,
        limit=candidate_limit,
    )

    source = candidates.get("items", [])

    assessed = []

    for candidate in source[:max(1, assessment_limit)]:
        block_id = candidate["block_id"]

        assessment = assess_block_completely(
            block_id,
            planned_date=planned_date
            or candidate["planned_date"][:10],
        )

        scoring = _candidate_score(
            candidate,
            assessment,
        )

        reasons = _recommendation_reason(
            candidate,
            assessment,
            scoring,
        )

        assessed.append({
            "block_id": block_id,
            "planned_date": candidate["planned_date"],
            "section_id": candidate["section_id"],
            "track_id": candidate["track_id"],
            "task_ids": candidate["task_ids"],
            "task_count": candidate["task_count"],
            "total_duration_hours": candidate[
                "total_duration_hours"
            ],
            "risk_covered": candidate["risk_covered"],
            "average_risk": candidate["average_risk"],
            "criticality_score": candidate[
                "criticality_score"
            ],
            "priority_score": candidate[
                "priority_score"
            ],
            "utilization": candidate["utilization"],
            "window_start": candidate["window_start"],
            "window_finish": candidate["window_finish"],
            "feasible": candidate["feasible"],
            "assessment_status": assessment[
                "overall_status"
            ],
            "operationally_verified":
                scoring["operationally_verified"],
            "recommendation_score":
                scoring["recommendation_score"],
            "score_components":
                scoring["score_components"],
            "reasons": reasons,
            "assessment": assessment,
        })

    # Put genuinely verified candidates ahead of
    # operationally unverified candidates. Within the same
    # class, rank by recommendation score.
    assessed.sort(
        key=lambda item: (
            item["operationally_verified"],
            item["assessment_status"]
            == "READY_FOR_HUMAN_REVIEW",
            item["recommendation_score"],
            item["risk_covered"],
        ),
        reverse=True,
    )

    # Assign stable recommendation rank.
    for index, item in enumerate(
        assessed,
        start=1,
    ):
        item["rank"] = index

    return {
        "items": assessed,
        "summary": {
            "candidates_considered": len(source),
            "assessments_run": len(assessed),
            "verified":
                sum(
                    x["operationally_verified"]
                    for x in assessed
                ),
            "data_gaps":
                sum(
                    x["assessment_status"].endswith(
                        "DATA_GAP"
                    )
                    for x in assessed
                )
                + sum(
                    x["assessment_status"] in {
                        "SAFETY_REVIEW",
                        "MATERIAL_CONFLICT",
                        "TRAIN_CONFLICT",
                        "RESOURCE_CONFLICT",
                    }
                    for x in assessed
                ),
            "conflicts":
                sum(
                    x["assessment_status"] in {
                        "TRAIN_CONFLICT",
                        "RESOURCE_CONFLICT",
                    }
                    for x in assessed
                ),
        },
        "selection_policy": {
            "verified_before_unverified": True,
            "risk_weight": 0.30,
            "criticality_weight": 0.20,
            "priority_weight": 0.15,
            "window_weight": 0.10,
            "bundle_weight": 0.10,
            "operational_weight": 0.15,
        },
        "safety_note": (
            "Recommendations are decision support only. "
            "They do not grant railway possession, signalling "
            "authority or train movement authority."
        ),
        "data_mode": "synthetic",
        "planner_version": "maintenance_plan_v2",
    }
