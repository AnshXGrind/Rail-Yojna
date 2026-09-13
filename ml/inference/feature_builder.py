from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "data/raw/rail_yojna_data"


FEATURES = [
    "condition_score",
    "degradation_rate",
    "measurement_value",
    "inspection_quality",
    "measurement_confidence",
    "previous_condition_score",
    "condition_change",
    "days_since_previous_measurement",
    "historical_mean_condition",
    "historical_min_condition",
    "historical_mean_degradation",
    "historical_observation_count",
    "design_life_years",
    "criticality_score",
    "asset_age_days",
    "defect_days_since_last",
    "defect_count_before",
    "inspection_days_since_last",
    "inspection_count_before",
    "maintenance_days_since_last",
    "maintenance_count_before",
    "incident_days_since_last",
    "incident_count_before",
]


def _utc_timestamp(value) -> pd.Timestamp:
    """
    Normalize any incoming timestamp to timezone-aware UTC.
    """
    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")

    return timestamp.tz_convert("UTC")


def _parse_utc(series: pd.Series) -> pd.Series:
    """
    Parse a datetime column and normalize every value to UTC.
    """
    return pd.to_datetime(
        series,
        format="mixed",
        errors="coerce",
        utc=True,
    )


class FeatureBuilder:
    """
    Builds the exact 23-feature contract expected by the V2 model.

    All internal timestamps are normalized to UTC-aware pandas timestamps.
    """

    def __init__(self):
        # ------------------------------------------------------------
        # Asset master data
        # ------------------------------------------------------------

        self.assets = pd.read_parquet(
            DATA_ROOT / "assets.parquet",
            columns=[
                "asset_id",
                "installation_date",
                "design_life_years",
                "criticality_score",
            ],
        ).copy()

        self.assets["installation_date"] = _parse_utc(
            self.assets["installation_date"]
        )

        self.assets = self.assets.set_index("asset_id")

        # ------------------------------------------------------------
        # Condition history
        # ------------------------------------------------------------

        self.condition = pd.read_parquet(
            DATA_ROOT / "asset_condition_history.parquet",
            columns=[
                "asset_id",
                "timestamp",
                "condition_score",
                "degradation_rate",
                "measurement_type",
                "measurement_value",
                "inspection_method",
                "inspection_quality",
                "measurement_confidence",
            ],
        ).copy()

        self.condition["timestamp"] = _parse_utc(
            self.condition["timestamp"]
        )

        self.condition = self.condition.dropna(
            subset=["asset_id", "timestamp"]
        )

        self.condition = self.condition.sort_values(
            ["asset_id", "timestamp"]
        )

        # ------------------------------------------------------------
        # Defect history
        # ------------------------------------------------------------

        self.defects = pd.read_parquet(
            DATA_ROOT / "defects.parquet",
            columns=[
                "asset_id",
                "detected_timestamp",
            ],
        ).copy()

        self.defects["detected_timestamp"] = _parse_utc(
            self.defects["detected_timestamp"]
        )

        self.defects = self.defects.dropna(
            subset=["asset_id", "detected_timestamp"]
        )

        # ------------------------------------------------------------
        # Inspection history
        # ------------------------------------------------------------

        self.inspections = pd.read_parquet(
            DATA_ROOT / "inspections.parquet",
            columns=[
                "asset_id",
                "inspection_date",
            ],
        ).copy()

        self.inspections["inspection_date"] = _parse_utc(
            self.inspections["inspection_date"]
        )

        self.inspections = self.inspections.dropna(
            subset=["asset_id", "inspection_date"]
        )

        # ------------------------------------------------------------
        # Maintenance history
        # ------------------------------------------------------------

        self.maintenance = pd.read_parquet(
            DATA_ROOT / "maintenance_tasks.parquet",
            columns=[
                "asset_id",
                "planned_date",
            ],
        ).copy()

        self.maintenance["planned_date"] = _parse_utc(
            self.maintenance["planned_date"]
        )

        self.maintenance = self.maintenance.dropna(
            subset=["asset_id", "planned_date"]
        )

        # ------------------------------------------------------------
        # Incident history
        # ------------------------------------------------------------

        self.incidents = pd.read_parquet(
            DATA_ROOT / "incidents.parquet",
            columns=[
                "asset_id",
                "timestamp",
            ],
        ).copy()

        self.incidents["timestamp"] = _parse_utc(
            self.incidents["timestamp"]
        )

        self.incidents = self.incidents.dropna(
            subset=["asset_id", "timestamp"]
        )

    @staticmethod
    def _history_before(
        frame: pd.DataFrame,
        asset_id: str,
        timestamp_column: str,
        timestamp: pd.Timestamp,
        inclusive: bool = False,
    ) -> pd.DataFrame:
        if inclusive:
            mask = frame[timestamp_column] <= timestamp
        else:
            mask = frame[timestamp_column] < timestamp

        rows = frame[
            (frame["asset_id"] == asset_id)
            & mask
        ]

        return rows.sort_values(timestamp_column)

    def build(
        self,
        asset_id: str,
        timestamp,
        condition_score: float,
        degradation_rate: float,
        measurement_value: float,
        inspection_quality: float,
        measurement_confidence: float,
    ) -> pd.DataFrame:

        timestamp = _utc_timestamp(timestamp)

        if asset_id not in self.assets.index:
            raise KeyError(
                f"Unknown asset_id: {asset_id}"
            )

        asset = self.assets.loc[asset_id]

        # ------------------------------------------------------------
        # Condition history
        # ------------------------------------------------------------

        history = self._history_before(
            self.condition,
            asset_id,
            "timestamp",
            timestamp,
        )

        if history.empty:
            previous_condition_score = np.nan
            condition_change = np.nan
            days_since_previous_measurement = np.nan
            historical_mean_condition = np.nan
            historical_min_condition = np.nan
            historical_mean_degradation = np.nan
            historical_observation_count = 0
        else:
            previous = history.iloc[-1]

            previous_condition_score = float(
                previous["condition_score"]
            )

            condition_change = (
                condition_score - previous_condition_score
            )

            days_since_previous_measurement = (
                timestamp - previous["timestamp"]
            ).total_seconds() / 86400.0

            historical_mean_condition = float(
                history["condition_score"].mean()
            )

            historical_min_condition = float(
                history["condition_score"].min()
            )

            historical_mean_degradation = float(
                history["degradation_rate"].mean()
            )

            historical_observation_count = len(history)

        # ------------------------------------------------------------
        # Asset age
        # ------------------------------------------------------------

        installation_date = asset["installation_date"]

        if pd.isna(installation_date):
            asset_age_days = np.nan
        else:
            asset_age_days = (
                timestamp - installation_date
            ).total_seconds() / 86400.0

        # ------------------------------------------------------------
        # Defects
        # ------------------------------------------------------------

        defects = self._history_before(
            self.defects,
            asset_id,
            "detected_timestamp",
            timestamp,
            inclusive=True,
        )

        defect_count_before = len(defects)

        if defects.empty:
            defect_days_since_last = np.nan
        else:
            defect_days_since_last = (
                timestamp
                - defects["detected_timestamp"].iloc[-1]
            ).total_seconds() / 86400.0

        # ------------------------------------------------------------
        # Inspections
        # ------------------------------------------------------------

        inspections = self._history_before(
            self.inspections,
            asset_id,
            "inspection_date",
            timestamp,
        )

        inspection_count_before = len(inspections)

        if inspections.empty:
            inspection_days_since_last = np.nan
        else:
            inspection_days_since_last = (
                timestamp
                - inspections["inspection_date"].iloc[-1]
            ).total_seconds() / 86400.0

        # ------------------------------------------------------------
        # Maintenance
        # ------------------------------------------------------------

        maintenance = self._history_before(
            self.maintenance,
            asset_id,
            "planned_date",
            timestamp,
        )

        maintenance_count_before = len(maintenance)

        if maintenance.empty:
            maintenance_days_since_last = np.nan
        else:
            maintenance_days_since_last = (
                timestamp
                - maintenance["planned_date"].iloc[-1]
            ).total_seconds() / 86400.0

        # ------------------------------------------------------------
        # Incidents
        # ------------------------------------------------------------

        incidents = self._history_before(
            self.incidents,
            asset_id,
            "timestamp",
            timestamp,
        )

        incident_count_before = len(incidents)

        if incidents.empty:
            incident_days_since_last = np.nan
        else:
            incident_days_since_last = (
                timestamp
                - incidents["timestamp"].iloc[-1]
            ).total_seconds() / 86400.0

        values = {
            "condition_score": condition_score,
            "degradation_rate": degradation_rate,
            "measurement_value": measurement_value,
            "inspection_quality": inspection_quality,
            "measurement_confidence": measurement_confidence,
            "previous_condition_score": previous_condition_score,
            "condition_change": condition_change,
            "days_since_previous_measurement": (
                days_since_previous_measurement
            ),
            "historical_mean_condition": (
                historical_mean_condition
            ),
            "historical_min_condition": (
                historical_min_condition
            ),
            "historical_mean_degradation": (
                historical_mean_degradation
            ),
            "historical_observation_count": (
                historical_observation_count
            ),
            "design_life_years": asset["design_life_years"],
            "criticality_score": asset["criticality_score"],
            "asset_age_days": asset_age_days,
            "defect_days_since_last": defect_days_since_last,
            "defect_count_before": defect_count_before,
            "inspection_days_since_last": (
                inspection_days_since_last
            ),
            "inspection_count_before": (
                inspection_count_before
            ),
            "maintenance_days_since_last": (
                maintenance_days_since_last
            ),
            "maintenance_count_before": (
                maintenance_count_before
            ),
            "incident_days_since_last": (
                incident_days_since_last
            ),
            "incident_count_before": incident_count_before,
        }

        return pd.DataFrame(
            [[values[name] for name in FEATURES]],
            columns=FEATURES,
        )
