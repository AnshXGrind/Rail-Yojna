from pydantic import BaseModel


class AssetRiskResponse(BaseModel):
    asset_id: str
    risk: float
    condition_score: float
    degradation_rate: float
    risk_horizon_days: int
    prediction_timestamp: str | None
    data_mode: str
