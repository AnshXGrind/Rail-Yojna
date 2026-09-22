
from backend.app.services.recommendation_service import (
    _candidate_score,
)


def test_data_gap_is_not_operationally_verified():
    candidate = {
        "risk_covered": 0.8,
        "criticality_score": 0.9,
        "priority_score": 1.0,
        "utilization": 0.5,
        "task_count": 3,
    }

    assessment = {
        "overall_status": "TRAIN_DATA_GAP"
    }

    result = _candidate_score(
        candidate,
        assessment,
    )

    assert result["operationally_verified"] is False
    assert result["assessment_status"] == "TRAIN_DATA_GAP"


def test_ready_candidate_is_operationally_verified():
    candidate = {
        "risk_covered": 0.3,
        "criticality_score": 0.8,
        "priority_score": 1.0,
        "utilization": 0.7,
        "task_count": 2,
    }

    assessment = {
        "overall_status":
            "READY_FOR_HUMAN_REVIEW"
    }

    result = _candidate_score(
        candidate,
        assessment,
    )

    assert result["operationally_verified"] is True
