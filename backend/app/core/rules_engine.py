from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
RULES_PATH = (
    ROOT
    / "railway"
    / "india"
    / "rules"
    / "risk_rules.yaml"
)


def _load_rules() -> dict:
    with RULES_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify_risk(probability: float) -> str:
    probability = float(probability)

    if not 0.0 <= probability <= 1.0:
        raise ValueError(
            f"Risk probability must be within [0, 1], got {probability}"
        )

    rules = _load_rules()["risk_levels"]

    for rule in rules:
        if rule["min"] <= probability < rule["max"]:
            return rule["id"]

    if probability == 1.0:
        return "critical"

    raise ValueError(
        f"No risk level matched probability {probability}"
    )


def evaluate_risk(probability: float) -> list[str]:
    probability = float(probability)

    if not 0.0 <= probability <= 1.0:
        raise ValueError(
            f"Risk probability must be within [0, 1], got {probability}"
        )

    triggered: list[str] = []

    # Preserve the project's established rule contract.
    if probability >= 0.50:
        triggered.append("RISK-001")

    if probability >= 0.20:
        triggered.append("RISK-002")

    # Every AI prediction remains decision support and requires
    # human review before operational action.
    triggered.append("SAFETY-001")

    return triggered


def requires_human_review(
    probability: float,
    risk_level: str,
) -> bool:
    _ = probability
    _ = risk_level
    return True
