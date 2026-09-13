from datetime import datetime

from pydantic import BaseModel, Field


class RiskPredictionRequest(BaseModel):
    asset_id: str
    timestamp: datetime

    condition_score: float
    degradation_rate: float
    measurement_value: float
    inspection_quality: float = Field(ge=0.0)
    measurement_confidence: float = Field(ge=0.0, le=1.0)
