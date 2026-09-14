from __future__ import annotations

from pathlib import Path

import yaml


RULES_PATH = Path("railway/india/rules/risk_rules.yaml")


def _load_rules() -> dict:
    with RULES_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify_risk(probability: float) -> str:
    rules = _load_rules()["risk_levels"]

    for rule in rules:
        if rule["min"] <= probability < rule["max"]:
            return rule["id"]

    if probability >= 1.0:
        return "critical"

    return "low"


def evaluate_risk(probability: float) -> list[str]:
    triggered: list[str] = []

    if probability >= 0.50:
        triggered.append("RISK-001")

    if probability >= 0.20:
        triggered.append("RISK-002")

    triggered.append("SAFETY-001")

    return triggered
