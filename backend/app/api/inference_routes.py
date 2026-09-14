from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.audit.audit_service import record_event
from backend.app.core.rules_engine import (
    classify_risk,
    evaluate_risk,
    requires_human_review,
)
from backend.app.schemas.inference import RiskPredictionRequest
from ml.inference.predictor import predict


router = APIRouter(
    prefix="/api/v1/risk",
    tags=["risk-inference"],
)


@router.post("/predict")
def predict_risk(payload: RiskPredictionRequest):
    try:
        result = predict(
            asset_id=payload.asset_id,
            timestamp=payload.timestamp,
            condition_score=payload.condition_score,
            degradation_rate=payload.degradation_rate,
            measurement_value=payload.measurement_value,
            inspection_quality=payload.inspection_quality,
            measurement_confidence=payload.measurement_confidence,
        )

        risk_probability = float(result["risk_probability"])

        # Single operational source of truth for risk classification.
        risk_level = classify_risk(risk_probability)
        rules_triggered = evaluate_risk(risk_probability)
        review_required = requires_human_review(
            risk_probability,
            risk_level,
        )

        result["risk_level"] = risk_level
        result["rules_triggered"] = rules_triggered
        result["review_required"] = review_required
        result["human_approval_required"] = True
        result["decision_mode"] = "decision_support"

        record_event(
            "RISK_PREDICTION",
            actor="api",
            asset_id=payload.asset_id,
            model_version=result.get("model_version"),
            payload={
                "request": payload.model_dump(mode="json"),
                "result": result,
                "rules_triggered": rules_triggered,
            },
        )

        return result

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Prediction pipeline failed: {exc}",
        ) from exc
