from fastapi import APIRouter, HTTPException, Query
from backend.app.audit.audit_service import list_events, record_event
from backend.app.schemas.planning import PlanningDecisionRequest

from backend.app.schemas.risk import AssetRiskResponse
from backend.app.schemas.planning import PlanningSummary
from backend.app.services.risk_service import (
    get_asset_risk,
    get_top_risk_assets,
)
from backend.app.services.planning_service import (
    get_plan,
    get_plan_summary,
    get_plan_metrics,
    get_plan_task,
)


router = APIRouter(
    prefix="/api/v1",
)


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
        le=500,
    ),
):
    return {
        "items": get_plan(limit),
        "data_mode": "synthetic",
    }
