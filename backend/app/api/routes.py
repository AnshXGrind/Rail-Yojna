from backend.app.services.window_optimizer import optimize_windows
from fastapi import APIRouter, HTTPException, Query
from backend.app.audit.audit_service import list_events, record_event
from backend.app.schemas.planning import PlanningDecisionRequest

from backend.app.schemas.risk import AssetRiskResponse
from backend.app.schemas.planning import PlanningSummary
from backend.app.services.risk_service import (
    get_asset_risk,
    get_top_risk_assets,
)
from backend.app.services.block_service import (
    generate_block_candidates,
    get_block_plan,
)
from backend.app.services.block_assessment_service import assess_block_completely
from backend.app.services.recommendation_service import recommend_blocks
from backend.app.services.operational_service import assess_block
from backend.app.services.resource_service import assess_resources
from backend.app.services.planning_service import (
    get_plan,
    get_plan_summary,
    get_plan_metrics,
    get_plan_task,
)


router = APIRouter(
    prefix="/api/v1",
)

from pydantic import BaseModel, Field


class BlockDecisionRequest(BaseModel):
    decision: str = Field(
        pattern="^(approve|modify|reject)$"
    )
    actor: str = "planner"
    note: str = ""
    task_ids: list[str] = []




@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "rail-yojna-backend",
        "data_mode": "synthetic",
    }


@router.get(
    "/assets/{asset_id}/risk",
    response_model=AssetRiskResponse,
)
def asset_risk(asset_id: str):
    try:
        return get_asset_risk(asset_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Asset not found: {asset_id}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@router.get("/assets/risk/top")
def top_risk_assets(
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
):
    return {
        "items": get_top_risk_assets(limit),
        "data_mode": "synthetic",
    }


@router.get(
    "/planning/summary",
    response_model=PlanningSummary,
)
def planning_summary():
    return get_plan_summary()


@router.get("/planning/plan")
def planning_plan(
    limit: int = Query(
        default=50,
        ge=1,
        le=1500,
    ),
):
    return {
        "items": get_plan(limit),
        "data_mode": "synthetic",
    }





@router.get(
    "/planning/blocks/recommendations"
)
def planning_block_recommendations(
    planned_date: str | None = Query(default=None),
    section_id: str | None = Query(default=None),
    track_id: str | None = Query(default=None),
    candidate_limit: int = Query(
        default=30,
        ge=1,
        le=100,
    ),
    assessment_limit: int = Query(
        default=15,
        ge=1,
        le=30,
    ),
):
    return recommend_blocks(
        planned_date=planned_date,
        section_id=section_id,
        track_id=track_id,
        candidate_limit=candidate_limit,
        assessment_limit=assessment_limit,
    )


@router.get("/planning/blocks/candidates")
def planning_block_candidates(
    planned_date: str | None = Query(default=None),
    section_id: str | None = Query(default=None),
    track_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    return generate_block_candidates(
        planned_date=planned_date,
        section_id=section_id,
        track_id=track_id,
        limit=limit,
    )




@router.get(
    "/planning/blocks/{block_id}/resource-assessment"
)
def planning_block_resource_assessment(
    block_id: str,
    planned_date: str | None = Query(default=None),
):
    return assess_resources(
        block_id,
        planned_date=planned_date,
    )



@router.get(
    "/planning/blocks/{block_id}/assessment"
)
def planning_block_assessment(
    block_id: str,
    planned_date: str | None = Query(default=None),
):
    return assess_block_completely(
        block_id,
        planned_date=planned_date,
    )


@router.get("/planning/blocks/{block_id}/operational-assessment")
def planning_block_operational_assessment(
    block_id: str,
    planned_date: str | None = Query(default=None),
):
    return assess_block(
        block_id,
        planned_date=planned_date,
    )


@router.post("/planning/blocks/{block_id}/decision")
def planning_block_decision(
    block_id: str,
    request: BlockDecisionRequest,
):
    event_type = {
        "approve": "BLOCK_APPROVED",
        "modify": "BLOCK_MODIFIED",
        "reject": "BLOCK_REJECTED",
    }[request.decision]

    event = record_event(
        event_type,
        actor=request.actor,
        recommendation_id=block_id,
        model_version="maintenance_plan_v2",
        payload={
            "block_id": block_id,
            "decision": request.decision,
            "task_ids": request.task_ids,
            "note": request.note,
            "human_reviewed": True,
            "decision_mode": "decision_support",
            "operational_authority": False,
        },
    )

    return {
        "decision_id": event["event_id"],
        "block_id": block_id,
        "decision": request.decision,
        "actor": request.actor,
        "note": request.note,
        "human_approval_required": True,
        "decision_mode": "decision_support",
    }


@router.get("/planning/blocks")
def planning_blocks(
    planned_date: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000),
):
    return get_block_plan(
        planned_date=planned_date,
        limit=limit,
    )


@router.get("/planning/metrics")
def planning_metrics():
    return get_plan_metrics()


@router.get("/planning/tasks/{task_id}")
def planning_task(task_id: str):
    try:
        return get_plan_task(task_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Planning task not found: {task_id}",
        )


@router.post("/planning/tasks/{task_id}/decision")
def planning_decision(
    task_id: str,
    request: PlanningDecisionRequest,
):
    try:
        task = get_plan_task(task_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Planning task not found: {task_id}",
        )

    event_type = {
        "approve": "PLANNING_APPROVED",
        "modify": "PLANNING_MODIFIED",
        "reject": "PLANNING_REJECTED",
    }[request.decision]

    event = record_event(
        event_type,
        actor=request.actor,
        asset_id=str(task["asset_id"]),
        recommendation_id=str(task_id),
        model_version="maintenance_plan_v2",
        payload={
            "task": task_id,
            "decision": request.decision,
            "note": request.note,
            "human_reviewed": True,
            "decision_mode": "decision_support",
        },
    )

    return {
        "decision_id": event["event_id"],
        "task_id": task_id,
        "decision": request.decision,
        "actor": request.actor,
        "note": request.note,
        "human_approval_required": True,
        "decision_mode": "decision_support",
    }


@router.get("/audit/events")
def audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    event_type: str | None = Query(default=None),
    asset_id: str | None = Query(default=None),
):
    return {
        "items": list_events(
            limit=limit,
            event_type=event_type,
            asset_id=asset_id,
        ),
        "data_mode": "synthetic",
    }



@router.get("/planning/blocks/{block_id}/optimized-windows")
def planning_block_optimized_windows(block_id: str):
    """
    Decision-support window assessment.

    Does not grant block authority, possession, signalling authority,
    dispatch authority, or train movement authority.
    """

    from backend.app.services.block_assessment_service import (
        assess_block_completely,
    )

    match = re.match(
        r"^BLK-(\d{8})",
        block_id,
    )

    if not match:
        raise HTTPException(
            status_code=400,
            detail="Invalid block_id format; expected BLK-YYYYMMDD...",
        )

    planned_date = (
        f"{match.group(1)[:4]}-"
        f"{match.group(1)[4:6]}-"
        f"{match.group(1)[6:8]}"
    )

    try:
        assessment = assess_block_completely(
            block_id=block_id,
            planned_date=planned_date,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Block assessment failed: {exc}",
        )

    trains = assessment.get("trains") or {}
    resources = assessment.get("resources") or {}
    materials = assessment.get("materials") or {}

    return {
        "block_id": block_id,
        "planned_date": planned_date,
        "overall_status": assessment.get("overall_status"),
        "maintenance": assessment.get("maintenance"),
        "safety": assessment.get("safety"),
        "trains": trains,
        "resources": resources,
        "materials": materials,
        "alternative_windows": assessment.get(
            "alternative_windows",
            [],
        ),
        "window_optimizer_status": assessment.get(
            "window_optimizer_status",
            "DATA_GAP",
        ),
        "window_optimizer": assessment.get(
            "window_optimizer",
            {},
        ),
        "planner_safety_note": (
            "Decision support only. Final railway operating and "
            "safety procedures remain authoritative."
        ),
    }
