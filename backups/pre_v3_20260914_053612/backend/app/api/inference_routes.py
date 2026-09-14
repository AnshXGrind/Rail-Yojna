from fastapi import APIRouter, HTTPException

from backend.app.schemas.inference import RiskPredictionRequest
from ml.inference.predictor import predict


router = APIRouter(
    prefix="/api/v1/risk",
    tags=["risk"],
)


@router.post("/predict")
def predict_risk(request: RiskPredictionRequest):
    try:
        return predict(
            asset_id=request.asset_id,
            timestamp=request.timestamp,
            condition_score=request.condition_score,
            degradation_rate=request.degradation_rate,
            measurement_value=request.measurement_value,
            inspection_quality=request.inspection_quality,
            measurement_confidence=request.measurement_confidence,
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )
