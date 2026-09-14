from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


PAYLOAD = {
    "asset_id": "AST00015579",
    "timestamp": "2025-12-31T23:59:59Z",
    "condition_score": 14.697,
    "degradation_rate": 1.541,
    "measurement_value": 85.9196,
    "inspection_quality": 0.9347,
    "measurement_confidence": 0.8431,
}


def test_health():
    response = client.get("/api/v1/health")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "ok"
    assert body["service"] == "rail-yojna-backend"


def test_live_prediction_contract():
    response = client.post(
        "/api/v1/risk/predict",
        json=PAYLOAD,
    )

    assert response.status_code == 200

    body = response.json()

    required = {
        "asset_id",
        "timestamp",
        "raw_probability",
        "risk_probability",
        "risk_level",
        "rules_triggered",
        "review_required",
        "human_approval_required",
        "decision_mode",
        "prediction_horizon_days",
        "model_version",
        "calibration",
        "data_mode",
    }

    assert required.issubset(body.keys())

    assert body["asset_id"] == PAYLOAD["asset_id"]
    assert body["prediction_horizon_days"] == 30
    assert body["model_version"] == "failure_30d_v3_logistic"
    assert body["calibration"] == "platt_sigmoid"
    assert body["data_mode"] == "synthetic"

    assert 0.0 <= body["raw_probability"] <= 1.0
    assert 0.0 <= body["risk_probability"] <= 1.0

    assert body["risk_level"] in {
        "low",
        "medium",
        "high",
        "critical",
    }

    assert body["review_required"] is True
    assert body["human_approval_required"] is True
    assert body["decision_mode"] == "decision_support"

    assert "SAFETY-001" in body["rules_triggered"]


def test_risk_threshold_contract():
    # This directly verifies the deterministic rules
    # without relying on a particular model probability.
    from backend.app.core.rules_engine import classify_risk

    assert classify_risk(0.049999) == "low"
    assert classify_risk(0.05) == "medium"
    assert classify_risk(0.199999) == "medium"
    assert classify_risk(0.20) == "high"
    assert classify_risk(0.499999) == "high"
    assert classify_risk(0.50) == "critical"
    assert classify_risk(1.0) == "critical"


def test_system_status_contract():
    response = client.get("/api/v1/system/status")

    assert response.status_code == 200

    body = response.json()

    assert body["project"] == "Rail-Yojna"
    assert body["mode"] == "decision_support"

    assert body["model"]["version"] == "failure_30d_v3_logistic"
    assert body["model"]["target"] == "failure_within_30_days"
    assert body["model"]["horizon_days"] == 30
    assert body["model"]["feature_count"] == 23
    assert body["model"]["calibration"] == "platt_sigmoid"

    assert body["safety_policy"]["human_approval_required"] is True
    assert body["safety_policy"]["autonomous_signalling"] is False
    assert body["safety_policy"]["autonomous_train_control"] is False
    assert body["safety_policy"]["autonomous_block_authority"] is False

    assert body["artifacts"]["model"]["exists"] is True
    assert body["artifacts"]["calibrator"]["exists"] is True
    assert body["artifacts"]["metadata"]["exists"] is True
    assert body["artifacts"]["rules"]["exists"] is True
