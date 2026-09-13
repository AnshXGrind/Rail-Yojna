from pydantic import BaseModel


class PlanningSummary(BaseModel):
    candidate_tasks: int
    selected_tasks: int
    deferred_tasks: int
    selected_minutes: int
    selected_hours: float
    risk_mass: float
    data_mode: str
