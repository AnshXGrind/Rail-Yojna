from backend.app.core.rules_engine import classify_risk, evaluate_risk


def test_low_risk():
    assert classify_risk(0.01) == "low"


def test_medium_risk():
    assert classify_risk(0.10) == "medium"


def test_high_risk():
    assert classify_risk(0.30) == "high"


def test_critical_risk():
    assert classify_risk(0.75) == "critical"


def test_critical_triggers_review():
    rules = evaluate_risk(0.75)

    assert "RISK-001" in rules
    assert "RISK-002" in rules
    assert "SAFETY-001" in rules
