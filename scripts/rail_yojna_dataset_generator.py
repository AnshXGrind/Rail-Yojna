#!/usr/bin/env python3
"""
Rail-Yojna synthetic railway maintenance & block-planning dataset generator.

This program GENERATES the dataset locally; it does not embed or return the
dataset itself. It produces a relational CSV ecosystem plus metadata,
validation reports, and reproducibility information.

Research/prototyping only. Synthetic data. Not for railway signalling,
train-control, dispatching, or safety-critical operational use.

Usage:
    python rail_yojna_dataset_generator.py --output ./rail_yojna_data
    python rail_yojna_dataset_generator.py --output ./rail_yojna_data --scale 0.5
    python rail_yojna_dataset_generator.py --output ./rail_yojna_data --seed 42

Dependencies:
    pip install numpy pandas
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import time
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


DATASET_NAME = "synthetic_research_dataset"
GENERATOR_VERSION = "1.0.0"

START_DATE = pd.Timestamp("2022-01-01", tz="UTC")
END_DATE = pd.Timestamp("2026-01-01", tz="UTC")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class Config:
    seed: int = 42
    scale: float = 1.0
    start_date: str = "2022-01-01"
    end_date: str = "2025-12-31 23:59:59"
    country_mix: dict[str, float] = field(default_factory=lambda: {
        "India": 0.78,
        "United Kingdom": 0.07,
        "Germany": 0.06,
        "Japan": 0.04,
        "Australia": 0.05,
    })

    # Baseline entities. scale=1 is intentionally above the minimum ranges.
    networks: int = 20
    stations: int = 180
    sections: int = 900
    tracks: int = 1800
    assets: int = 30000
    trains: int = 1800
    resources: int = 1800
    machines: int = 450
    materials: int = 400

    # Time-series controls. Defaults target several million rows.
    condition_obs_per_asset: int = 20
    inspection_rate_per_asset_year: float = 1.0
    train_days: int = 1461
    movements_per_train_day: float = 0.20
    weather_obs_per_section: int = 700
    forecast_per_section: int = 180

    # Relationship/event rates.
    defect_rate_per_asset_year: float = 0.08
    maintenance_tasks_per_asset_year: float = 0.18
    block_rate: float = 0.70
    traffic_delay_rate: float = 0.12
    incident_rate_per_section_year: float = 0.018

    # Data-quality experiments. Keep false for clean research data by default.
    introduce_corruption: bool = False
    corruption_rate: float = 0.005

    # Output.
    csv_compression: str | None = None  # None keeps output easy to inspect.
    write_parquet: bool = False
    write_sqlite: bool = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def uid(prefix: str, n: int) -> str:
    return f"{prefix}{n:08d}"


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-x))


def weighted_choice(rng: np.random.Generator, choices: list[str],
                    probabilities: list[float], size: int | None = None):
    return rng.choice(choices, size=size, p=np.array(probabilities) / np.sum(probabilities))


def ts_iso(x: pd.Timestamp | datetime) -> str:
    return pd.Timestamp(x).isoformat()


def random_timestamps(
    rng: np.random.Generator,
    start: pd.Timestamp,
    end: pd.Timestamp,
    n: int,
) -> pd.DatetimeIndex:
    span_seconds = max(1, int((end - start).total_seconds()))
    # pandas requires a tz-naive origin for integer epoch offsets.
    naive_start = pd.Timestamp(start).tz_convert("UTC").tz_localize(None)
    return pd.to_datetime(
        rng.integers(0, span_seconds, size=n),
        unit="s",
        origin=naive_start,
        utc=True,
    )


def add_dataframe_metadata(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    """No automatic provenance rows here: provenance is emitted separately."""
    df = df.copy()
    df.insert(0, "_table_name", table_name)
    return df


def strip_internal_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df[[c for c in df.columns if not c.startswith("_")]]


def choose_country(rng: np.random.Generator, mix: dict[str, float], n: int) -> np.ndarray:
    names = list(mix)
    p = np.array(list(mix.values()), dtype=float)
    p = p / p.sum()
    return rng.choice(names, size=n, p=p)


def country_config(country: str) -> dict[str, str]:
    cfg = {
        "India": dict(
            operator="Synthetic National Rail Network",
            timezone="Asia/Kolkata", gauge="1676 mm",
            electrification_type="25 kV AC OHE", voltage="25000",
            signalling_system="Automatic block / electronic interlocking",
            operating_ruleset_id="RULESET-IN-01",
            safety_ruleset_id="SAFE-IN-01", unit_system="metric",
        ),
        "United Kingdom": dict(
            operator="Synthetic UK Rail Network", timezone="Europe/London",
            gauge="1435 mm", electrification_type="25 kV AC OLE",
            voltage="25000", signalling_system="ETCS / conventional hybrid",
            operating_ruleset_id="RULESET-UK-01",
            safety_ruleset_id="SAFE-UK-01", unit_system="metric",
        ),
        "Germany": dict(
            operator="Synthetic European Rail Network", timezone="Europe/Berlin",
            gauge="1435 mm", electrification_type="15 kV AC OLE",
            voltage="15000", signalling_system="ETCS / electronic interlocking",
            operating_ruleset_id="RULESET-EU-01",
            safety_ruleset_id="SAFE-EU-01", unit_system="metric",
        ),
        "Japan": dict(
            operator="Synthetic Japanese Rail Network", timezone="Asia/Tokyo",
            gauge="1067 mm", electrification_type="AC/DC overhead",
            voltage="20000", signalling_system="ATC / electronic interlocking",
            operating_ruleset_id="RULESET-JP-01",
            safety_ruleset_id="SAFE-JP-01", unit_system="metric",
        ),
        "Australia": dict(
            operator="Synthetic Australian Rail Network", timezone="Australia/Sydney",
            gauge="1435 mm", electrification_type="25 kV AC OLE / diesel",
            voltage="25000", signalling_system="CBTC / electronic interlocking",
            operating_ruleset_id="RULESET-AU-01",
            safety_ruleset_id="SAFE-AU-01", unit_system="metric",
        ),
    }
    return cfg[country]


ASSET_TYPES = [
    "rail", "sleeper", "ballast", "turnout", "point_machine", "signal",
    "track_circuit", "axle_counter", "OHE", "bridge", "culvert",
    "level_crossing", "drainage", "platform_equipment", "signalling_equipment",
]
ASSET_TYPE_PROBS = [
    .20, .13, .10, .07, .06, .09, .06, .04, .08, .03, .03, .04, .04, .01, .02
]

DEFECT_TYPES = [
    ("rail", "head_checking"),
    ("rail", "crack"),
    ("rail", "wear"),
    ("sleeper", "broken_sleeper"),
    ("ballast", "poor_geometry"),
    ("turnout", "wear"),
    ("point_machine", "motor_failure"),
    ("signal", "lamp_or_led_fault"),
    ("track_circuit", "occupancy_fault"),
    ("axle_counter", "counting_fault"),
    ("OHE", "contact_wire_wear"),
    ("bridge", "corrosion"),
    ("culvert", "blockage"),
    ("level_crossing", "barrier_fault"),
    ("drainage", "blocked_drain"),
    ("signalling_equipment", "interlocking_fault"),
]

TASK_LIBRARY = {
    "rail": ["rail_inspection", "rail_grinding", "rail_replacement"],
    "sleeper": ["sleeper_replacement", "tamping"],
    "ballast": ["ballast_renewal", "tamping"],
    "turnout": ["turnout_inspection", "turnout_repair"],
    "point_machine": ["point_machine_service", "point_machine_replacement"],
    "signal": ["signal_maintenance", "signal_replacement"],
    "track_circuit": ["track_circuit_test", "track_circuit_repair"],
    "axle_counter": ["axle_counter_test", "axle_counter_repair"],
    "OHE": ["OHE_inspection", "OHE_maintenance"],
    "bridge": ["bridge_inspection", "bridge_repair"],
    "culvert": ["culvert_clearance", "culvert_repair"],
    "level_crossing": ["level_crossing_maintenance", "level_crossing_repair"],
    "drainage": ["drainage_clearance", "drainage_repair"],
    "platform_equipment": ["platform_equipment_service"],
    "signalling_equipment": ["signalling_test", "signalling_repair"],
}

TASK_BASE_DURATION = {
    "rail_inspection": 90, "rail_grinding": 180, "rail_replacement": 360,
    "sleeper_replacement": 150, "tamping": 240,
    "ballast_renewal": 420, "turnout_inspection": 150, "turnout_repair": 300,
    "point_machine_service": 180, "point_machine_replacement": 300,
    "signal_maintenance": 120, "signal_replacement": 210,
    "track_circuit_test": 100, "track_circuit_repair": 220,
    "axle_counter_test": 120, "axle_counter_repair": 250,
    "OHE_inspection": 160, "OHE_maintenance": 330,
    "bridge_inspection": 240, "bridge_repair": 600,
    "culvert_clearance": 180, "culvert_repair": 360,
    "level_crossing_maintenance": 150, "level_crossing_repair": 330,
    "drainage_clearance": 120, "drainage_repair": 270,
    "platform_equipment_service": 140,
    "signalling_test": 150, "signalling_repair": 300,
}

SAMPLE_VALUES = {
    "bool": [True, False],
    "task_status": ["planned", "approved", "completed", "cancelled", "postponed"],
}


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class RailYojnaGenerator:
    def __init__(self, config: Config):
        self.cfg = config
        self.rng = np.random.default_rng(config.seed)
        self.start = pd.Timestamp(config.start_date, tz="UTC")
        self.end = pd.Timestamp(config.end_date, tz="UTC")
        self.run_id = uuid.uuid4().hex[:12]
        self.tables: dict[str, pd.DataFrame] = {}
        self.schemas: dict[str, list[str]] = {}
        self.pk: dict[str, str] = {}
        self.fks: list[tuple[str, str, str, str]] = []
        self.table_counts: dict[str, int] = {}
        self.corruption_records: list[dict[str, Any]] = []

    def n(self, base: int) -> int:
        return max(1, int(round(base * self.cfg.scale)))

    def register(self, table: str, df: pd.DataFrame, primary_key: str | None = None):
        self.tables[table] = df
        self.schemas[table] = list(df.columns)
        if primary_key:
            self.pk[table] = primary_key
        self.table_counts[table] = len(df)

    # ------------------------------------------------------------------
    # Base network
    # ------------------------------------------------------------------

    def generate_networks(self):
        countries = choose_country(self.rng, self.cfg.country_mix, self.n(self.cfg.networks))
        rows = []
        for i, country in enumerate(countries, 1):
            c = country_config(str(country))
            rows.append({
                "network_id": uid("NET", i),
                "country": country,
                "railway_operator": c["operator"],
                "region": f"Region-{((i - 1) % 12) + 1:02d}",
                "timezone": c["timezone"],
                "gauge": c["gauge"],
                "electrification_type": c["electrification_type"],
                "voltage": c["voltage"],
                "signalling_system": c["signalling_system"],
                "operating_ruleset_id": c["operating_ruleset_id"],
                "safety_ruleset_id": c["safety_ruleset_id"],
                "unit_system": c["unit_system"],
            })
        self.register("networks", pd.DataFrame(rows), "network_id")

    def generate_stations(self):
        net = self.tables["networks"]
        rows = []
        for i in range(1, self.n(self.cfg.stations) + 1):
            nrow = net.iloc[(i - 1) % len(net)]
            # Synthetic geography: network-specific lat/lon clouds.
            base_lat = {"India": 22.0, "United Kingdom": 54.5,
                        "Germany": 51.0, "Japan": 36.0, "Australia": -27.0}[nrow.country]
            base_lon = {"India": 80.0, "United Kingdom": -2.0,
                        "Germany": 10.5, "Japan": 138.0, "Australia": 134.0}[nrow.country]
            lat = base_lat + self.rng.normal(0, 3.5)
            lon = base_lon + self.rng.normal(0, 4.5)
            stype = self.rng.choice(
                ["intermediate", "junction", "terminal", "major_terminal"],
                p=[.56, .18, .18, .08]
            )
            platforms = int(self.rng.integers(1, 9 if stype != "major_terminal" else 18))
            tracks = int(max(platforms, self.rng.integers(platforms, platforms + 8)))
            rows.append({
                "station_id": uid("STN", i),
                "network_id": nrow.network_id,
                "station_code": f"S{i:05d}",
                "station_name": f"Synthetic Station {i:05d}",
                "station_type": stype,
                "region": nrow.region,
                "latitude": round(float(lat), 6),
                "longitude": round(float(lon), 6),
                "elevation_m": round(float(max(-10, self.rng.normal(250, 180))), 1),
                "number_of_platforms": platforms,
                "number_of_tracks": tracks,
                "control_type": self.rng.choice(
                    ["local", "remote", "centralized"],
                    p=[.18, .30, .52]
                ),
                "junction_flag": stype in ("junction", "major_terminal"),
                "terminal_flag": stype in ("terminal", "major_terminal"),
            })
        self.register("stations", pd.DataFrame(rows), "station_id")

    def generate_track_sections(self):
        stations = self.tables["stations"]
        networks = self.tables["networks"]
        rows = []
        # A connected backbone plus additional branches. Each section connects
        # station i to station i+1 within the same network, then adds shortcuts.
        by_net = stations.groupby("network_id")["station_id"].apply(list).to_dict()
        idx = 0
        for net_id, ids in by_net.items():
            if len(ids) < 2:
                continue
            limit = max(1, int(round(len(ids) * 0.75)))
            for j in range(limit - 1):
                idx += 1
                a, b = ids[j], ids[j + 1]
                rows.append(self._make_section(idx, net_id, a, b, networks))
            # Branch edges.
            branch_count = max(1, int(round(len(ids) * 0.7)))
            for _ in range(branch_count):
                idx += 1
                a_i, b_i = self.rng.choice(len(ids), size=2, replace=False)
                a, b = ids[int(a_i)], ids[int(b_i)]
                if a == b:
                    continue
                rows.append(self._make_section(idx, net_id, a, b, networks))
        # Ensure requested scale is reached.
        all_st = stations.station_id.to_numpy()
        all_net = stations.network_id.to_numpy()
        target = self.n(self.cfg.sections)
        while len(rows) < target:
            ai, bi = self.rng.choice(len(all_st), 2, replace=False)
            if all_net[ai] != all_net[bi]:
                continue
            idx += 1
            rows.append(self._make_section(idx, str(all_net[ai]),
                                           str(all_st[ai]), str(all_st[bi]), networks))
        self.register("track_sections", pd.DataFrame(rows[:target]), "section_id")

    def _make_section(self, i: int, net_id: str, a: str, b: str, networks: pd.DataFrame):
        nrow = networks.loc[networks.network_id.eq(net_id)].iloc[0]
        gauge = nrow.gauge
        electrified = self.rng.random() < .88
        track_count = int(self.rng.choice([1, 2, 3], p=[.25, .68, .07]))
        length = float(np.clip(self.rng.lognormal(np.log(8.0), .55), 1.0, 42.0))
        max_speed = int(self.rng.choice([60, 80, 100, 120, 130, 160], p=[.05,.08,.16,.24,.25,.22]))
        criticality = float(np.clip(self.rng.beta(3.2, 2.0), .05, .99))
        return {
            "section_id": uid("SEC", i),
            "network_id": net_id,
            "from_station_id": a,
            "to_station_id": b,
            "section_name": f"Section {i:05d}",
            "section_type": self.rng.choice(["mainline", "branch", "yard", "approach"], p=[.72,.12,.08,.08]),
            "length_km": round(length, 3),
            "track_count": track_count,
            "directionality": "bidirectional" if track_count == 1 else "paired_direction",
            "gauge": gauge,
            "electrified": electrified,
            "voltage": nrow.voltage if electrified else "0",
            "maximum_permitted_speed_kmh": max_speed,
            "current_speed_limit_kmh": int(max_speed * self.rng.uniform(.80, 1.0)),
            "gradient_percent": round(float(self.rng.normal(0, .9)), 3),
            "curvature": self.rng.choice(["low", "medium", "high"], p=[.55,.32,.13]),
            "capacity_trains_per_day": int(np.clip(
                track_count * self.rng.normal(70, 12), 25, 220)),
            "criticality_score": round(criticality, 4),
        }

    def generate_tracks(self):
        sec = self.tables["track_sections"]
        rows = []
        i = 0
        for r in sec.itertuples(index=False):
            for k in range(int(r.track_count)):
                i += 1
                direction = "up" if r.track_count == 1 and k == 0 else ("up" if k % 2 == 0 else "down")
                rows.append({
                    "track_id": uid("TRK", i),
                    "section_id": r.section_id,
                    "track_name": f"{r.section_name} Track {k+1}",
                    "track_type": "running" if r.section_type != "yard" else "yard",
                    "direction": direction,
                    "electrification": "electrified" if r.electrified else "non_electrified",
                    "maximum_speed_kmh": r.maximum_permitted_speed_kmh,
                    "operational_status": self.rng.choice(["open", "open_restricted", "maintenance"], p=[.94,.04,.02]),
                    "signalling_area_id": f"SIGAREA-{int(self.rng.integers(1, max(3, len(sec)//15))):04d}",
                })
        self.register("tracks", pd.DataFrame(rows), "track_id")

    # ------------------------------------------------------------------
    # Assets and condition trajectories
    # ------------------------------------------------------------------

    def generate_assets(self):
        tracks = self.tables["tracks"]
        stations = self.tables["stations"]
        n = self.n(self.cfg.assets)
        track_idx = self.rng.integers(0, len(tracks), size=n)
        track_ids = tracks.track_id.to_numpy()[track_idx]
        section_ids = tracks.section_id.to_numpy()[track_idx]
        station_ids = stations.station_id.to_numpy()[self.rng.integers(0, len(stations), size=n)]

        types = weighted_choice(self.rng, ASSET_TYPES, ASSET_TYPE_PROBS, size=n)
        install_start = pd.Timestamp("2005-01-01", tz="UTC")
        install_end = pd.Timestamp("2024-01-01", tz="UTC")
        dates = random_timestamps(self.rng, install_start, install_end, n)

        rows = []
        for i in range(n):
            at = str(types[i])
            life = {
                "rail": 30, "sleeper": 25, "ballast": 15, "turnout": 30,
                "point_machine": 20, "signal": 25, "track_circuit": 20,
                "axle_counter": 18, "OHE": 35, "bridge": 75, "culvert": 60,
                "level_crossing": 25, "drainage": 20, "platform_equipment": 15,
                "signalling_equipment": 25,
            }[at]
            if at in ("rail", "sleeper", "ballast", "turnout", "OHE"):
                subtype = self.rng.choice(["standard", "heavy_duty", "renewal_grade"])
            else:
                subtype = self.rng.choice(["type_A", "type_B", "type_C"])
            chain_start = float(self.rng.uniform(0, 10000))
            span = float(max(2, self.rng.uniform(2, 250)))
            rows.append({
                "asset_id": uid("AST", i + 1),
                "asset_type": at,
                "asset_subtype": subtype,
                "track_id": track_ids[i],
                "section_id": section_ids[i],
                "station_id": station_ids[i] if at in ("platform_equipment", "signalling_equipment") else "",
                "chainage_start_m": round(chain_start, 2),
                "chainage_end_m": round(chain_start + span, 2),
                "installation_date": dates[i].date().isoformat(),
                "manufacturer": self.rng.choice(["SynthRail", "VectorWorks", "RailCore", "OmniTrack", "AxisInfra"]),
                "model": f"{at.upper()}-{int(self.rng.integers(100, 999))}",
                "design_life_years": life,
                "criticality_score": round(float(self.rng.beta(3.0, 2.5)), 4),
                "operational_status": self.rng.choice(["active", "active_restricted", "out_of_service"], p=[.955,.035,.01]),
            })
        df = pd.DataFrame(rows)
        df["_install_ts"] = pd.to_datetime(df.installation_date, utc=True)
        self.register("assets", df.drop(columns="_install_ts"), "asset_id")

    def _asset_latent_features(self) -> pd.DataFrame:
        a = self.tables["assets"].copy()
        install = pd.to_datetime(a.installation_date, utc=True)
        age = ((self.start - install).dt.days / 365.25).clip(lower=0)
        a["age_years"] = age
        a["traffic_exposure"] = self.rng.lognormal(mean=1.0, sigma=.6, size=len(a))
        a["environment_stress"] = self.rng.beta(2.3, 5.5, size=len(a))
        # Stable asset-specific susceptibility produces longitudinal consistency.
        a["susceptibility"] = self.rng.normal(0, 0.7, size=len(a))
        return a

    def generate_condition_history(self):
        a = self._asset_latent_features()
        n_obs = max(2, self.cfg.condition_obs_per_asset)
        rows = []
        measurement_types = ["geometry", "visual", "ultrasonic", "electrical", "functional"]
        methods = {
            "geometry": "track_recording_car",
            "visual": "field_inspection",
            "ultrasonic": "NDT_ultrasonic",
            "electrical": "electrical_test",
            "functional": "functional_test",
        }

        # One latent trajectory per asset, sampled at approximately even intervals,
        # with noise on measurement values rather than re-randomizing condition.
        for r in a.itertuples(index=False):
            installation = pd.Timestamp(
                r.installation_date,
                tz="UTC",
            )

            history_start = max(
                self.start,
                installation,
            )

            if history_start > self.end:
                continue

            times = pd.date_range(
                history_start,
                self.end,
                periods=n_obs,
                tz="UTC",
            )

            age_at_start_years = max(
                (
                    history_start - installation
                ).total_seconds()
                / (365.25 * 86400.0),
                0.0,
            )

            base = float(np.clip(
                94
                - age_at_start_years * 1.15
                - r.traffic_exposure * 1.8
                - r.environment_stress * 9
                + r.susceptibility,
                35,
                97,
            ))
            trend = np.clip(
                0.35 + 0.035 * max(r.age_years, 0)
                + 0.25 * r.environment_stress
                + 0.04 * r.traffic_exposure,
                0.15, 1.75
            )
            previous = base
            for t in times:
                seasonal = 1.0 + 0.06 * math.sin(2 * math.pi * (t.dayofyear / 365.25))
                decay = trend * seasonal + self.rng.normal(0, .14)
                condition = float(np.clip(previous - decay, 1, 100))
                previous = condition
                mtype = str(self.rng.choice(measurement_types))
                unit = {
                    "geometry": "mm", "visual": "score",
                    "ultrasonic": "%", "electrical": "score", "functional": "score"
                }[mtype]
                value = {
                    "geometry": max(0.05, (100 - condition) * .12 + self.rng.normal(0, .25)),
                    "visual": condition + self.rng.normal(0, 1.2),
                    "ultrasonic": max(0, 100 - condition + self.rng.normal(0, 1.5)),
                    "electrical": condition + self.rng.normal(0, 1.1),
                    "functional": condition + self.rng.normal(0, 1.4),
                }[mtype]
                quality = float(np.clip(self.rng.beta(8, 2), .5, .999))
                rows.append({
                    "measurement_id": uid("MSR", len(rows) + 1),
                    "asset_id": r.asset_id,
                    "timestamp": t.isoformat(),
                    "condition_score": round(condition, 3),
                    "degradation_rate": round(trend, 4),
                    "measurement_type": mtype,
                    "measurement_value": round(float(value), 4),
                    "measurement_unit": unit,
                    "inspection_method": methods[mtype],
                    "inspection_quality": round(quality, 4),
                    "measurement_confidence": round(float(np.clip(quality * self.rng.normal(.96, .04), .35, 1)), 4),
                })
        self.register("asset_condition_history", pd.DataFrame(rows), "measurement_id")

    # ------------------------------------------------------------------
    # Inspections, defects, maintenance
    # ------------------------------------------------------------------

    def generate_inspections(self):
        a = self.tables["assets"]
        n = max(self.n(1), int(len(a) * self.cfg.inspection_rate_per_asset_year * 4.0))
        asset_idx = self.rng.integers(0, len(a), n)
        subset = a.iloc[asset_idx]
        dates = random_timestamps(self.rng, self.start, self.end, n)
        cond = self._condition_at_random_times(subset.asset_id.to_numpy(), dates)
        p_def = sigmoid((65 - cond) / 9)
        detected = self.rng.random(n) < p_def
        rows = []
        for i in range(n):
            count = int(self.rng.poisson(max(.05, float(p_def[i]) * 1.8))) if detected[i] else 0
            rows.append({
                "inspection_id": uid("INSP", i + 1),
                "asset_id": subset.asset_id.iloc[i],
                "inspection_date": dates[i].isoformat(),
                "inspection_type": self.rng.choice(["routine", "special", "post_incident", "pre_maintenance"],
                                                   p=[.62,.12,.06,.20]),
                "inspector_id": f"INSPPERSON-{int(self.rng.integers(1, 2600)):05d}",
                "condition_score": round(float(cond[i]), 3),
                "defect_detected": bool(detected[i]),
                "defect_count": count,
                "inspection_duration_minutes": int(np.clip(self.rng.normal(55 + count * 12, 15), 15, 240)),
                "inspection_method": self.rng.choice(["visual", "NDT", "instrumented", "functional"]),
                "inspection_quality": round(float(np.clip(self.rng.beta(8, 2), .45, 1)), 4),
                "follow_up_required": bool(detected[i] or count > 1),
            })
        self.register("inspections", pd.DataFrame(rows), "inspection_id")

    def _condition_at_random_times(self, asset_ids: np.ndarray, times: pd.DatetimeIndex) -> np.ndarray:
        history = self.tables["asset_condition_history"]
        # Fast enough for generated synthetic data: group by asset and interpolate.
        grouped = {
            k: g.sort_values("timestamp")
            for k, g in history.groupby("asset_id", sort=False)
        }
        out = np.empty(len(asset_ids), dtype=float)
        for i, (aid, t) in enumerate(zip(asset_ids, times)):
            g = grouped.get(aid)
            if g is None:
                out[i] = 75
                continue
            x = pd.to_datetime(g.timestamp, utc=True, format="mixed").astype("int64").to_numpy()
            y = g.condition_score.to_numpy(float)
            xi = pd.Timestamp(t).value
            out[i] = float(np.interp(xi, x, y))
        return out

    def generate_defects(self):
        a = self.tables["assets"]
        hist = self.tables["asset_condition_history"]
        # Defects are sampled from actual condition observations, not independently.
        by_asset = hist.groupby("asset_id", sort=False)
        rows = []
        for aid, g in by_asset:
            asset = a.loc[a.asset_id.eq(aid)].iloc[0]
            # A small number of candidate events, based on observed low condition.
            q = float(np.clip((72 - g.condition_score.mean()) / 38, .005, .30))
            count = int(self.rng.poisson(q * len(g)))
            if count == 0 and g.condition_score.min() < 55 and self.rng.random() < .35:
                count = 1
            if count <= 0:
                continue
            picks = self.rng.choice(len(g), size=min(count, len(g)), replace=False)
            for p in picks:
                h = g.iloc[int(p)]
                condition = float(h.condition_score)
                severity_num = int(np.clip(round(1 + 4 * sigmoid((58 - condition) / 7)), 1, 5))
                sev = ["low","moderate","high","critical","critical"][severity_num-1]
                priority = ["P4","P3","P2","P1","P1"][severity_num-1]
                failure_prob = float(sigmoid((48 - condition) / 7) * .20)
                fail = bool(self.rng.random() < failure_prob)
                detected = pd.Timestamp(h.timestamp)
                resolved = detected + pd.Timedelta(minutes=int(self.rng.integers(60, 30 * 24 * 6)))
                dtype, subtype = DEFECT_TYPES[int(self.rng.integers(len(DEFECT_TYPES)))]
                # Keep type correlated with actual asset where possible.
                if dtype != asset.asset_type and self.rng.random() < .72:
                    dtype = asset.asset_type
                    candidates = [x[1] for x in DEFECT_TYPES if x[0] == dtype]
                    subtype = candidates[int(self.rng.integers(len(candidates)))] if candidates else subtype
                speed_flag = bool(severity_num >= 3 and self.rng.random() < .55)
                rows.append({
                    "defect_id": uid("DEF", len(rows) + 1),
                    "asset_id": aid,
                    "section_id": asset.section_id,
                    "detected_timestamp": detected.isoformat(),
                    "defect_type": dtype,
                    "defect_subtype": subtype,
                    "severity": sev,
                    "priority": priority,
                    "location_chainage_m": round(float((asset.chainage_start_m + asset.chainage_end_m) / 2 + self.rng.normal(0, 3)), 2),
                    "detection_method": h.inspection_method if "inspection_method" in h else "condition_monitoring",
                    "description": f"Synthetic {subtype} detected at condition {condition:.1f}",
                    "temporary_action": self.rng.choice(["monitor", "speed_restriction", "isolate_asset", "none"],
                                                        p=[.30,.35,.08,.27]),
                    "speed_restriction_applied": speed_flag,
                    "speed_restriction_kmh": int(self.rng.choice([20, 40, 60, 80])) if speed_flag else 0,
                    "failure_occurred": fail,
                    "resolved_timestamp": resolved.isoformat() if not fail else "",
                    "root_cause": self.rng.choice(["age", "wear", "environment", "traffic_load", "component_fault", "unknown"]),
                    "resolution_type": self.rng.choice(["repair", "replacement", "adjustment", "monitoring", "pending"]),
                })
        self.register("defects", pd.DataFrame(rows), "defect_id")

    def generate_maintenance_tasks(self):
        a = self.tables["assets"]
        defects = self.tables["defects"]
        rows = []
        # Base preventive tasks tied to asset criticality/condition.
        for r in a.itertuples(index=False):
            if self.rng.random() < self.cfg.maintenance_tasks_per_asset_year * 4:
                task_type = str(self.rng.choice(TASK_LIBRARY[r.asset_type]))
                cond = self._latest_condition(r.asset_id)
                risk = clamp(
                    .45 * (1 - cond / 100)
                    + .35 * float(r.criticality_score)
                    + .20 * self.rng.random(), 0, 1)
                priority = "P1" if risk > .78 else "P2" if risk > .58 else "P3" if risk > .35 else "P4"
                planned = self.start + pd.Timedelta(days=int(self.rng.integers(15, 1300)))
                base = TASK_BASE_DURATION[task_type]
                complexity = 1 + .35 * risk + .10 * (1 + abs(self.rng.normal()))
                minimum = int(max(30, base * .72))
                maximum = int(base * (1.45 + .4 * risk) * complexity)
                estimated = int(np.clip(self.rng.normal(base * complexity, base * .15), minimum, maximum))
                earliest = planned - pd.Timedelta(hours=int(self.rng.integers(0, 72)))
                latest = planned + pd.Timedelta(days=int(self.rng.integers(1, 16)))
                rows.append(self._task_row(
                    len(rows)+1, r, task_type, priority, risk, planned, earliest, latest,
                    estimated, minimum, maximum
                ))

        # Defect-driven corrective tasks are always linked to a real defect.
        for d in defects.itertuples(index=False):
            if self.rng.random() < (.45 if d.severity in ("high", "critical") else .28):
                r = a.loc[a.asset_id.eq(d.asset_id)].iloc[0]
                task_type = str(self.rng.choice(TASK_LIBRARY[r.asset_type]))
                risk = {"low":.25,"moderate":.45,"high":.72,"critical":.92}[d.severity]
                priority = d.priority
                planned = pd.Timestamp(d.detected_timestamp) + pd.Timedelta(days=int(self.rng.integers(1, 30)))
                base = TASK_BASE_DURATION[task_type]
                minimum = int(max(30, base * .70))
                maximum = int(base * (1.35 + .5 * risk))
                estimated = int(np.clip(self.rng.normal(base, base * .18), minimum, maximum))
                rows.append(self._task_row(
                    len(rows)+1, r, task_type, priority, risk, planned,
                    planned - pd.Timedelta(hours=12), planned + pd.Timedelta(days=10),
                    estimated, minimum, maximum
                ))
        self.register("maintenance_tasks", pd.DataFrame(rows), "task_id")

    def _task_row(self, i, asset, task_type, priority, risk, planned, earliest, latest,
                  estimated, minimum, maximum):
        weather_sensitive = task_type in {"rail_grinding", "tamping", "OHE_maintenance", "drainage_repair"}
        return {
            "task_id": uid("TASK", i),
            "asset_id": asset.asset_id,
            "section_id": asset.section_id,
            "track_id": asset.track_id,
            "task_type": task_type,
            "task_category": "corrective" if priority in ("P1","P2") else "preventive",
            "priority": priority,
            "criticality": round(float(clamp(.55*float(asset.criticality_score)+.45*risk,0,1)),4),
            "task_description": f"Synthetic {task_type.replace('_',' ')} for {asset.asset_type}",
            "planned_date": planned.date().isoformat(),
            "earliest_start": pd.Timestamp(earliest).isoformat(),
            "latest_finish": pd.Timestamp(latest).isoformat(),
            "estimated_duration_minutes": int(estimated),
            "minimum_duration_minutes": int(minimum),
            "maximum_duration_minutes": int(maximum),
            "setup_time_minutes": int(self.rng.integers(15, 60)),
            "cleanup_time_minutes": int(self.rng.integers(10, 45)),
            "safety_margin_minutes": int(self.rng.integers(10, 45)),
            "block_required": bool(priority in ("P1","P2") or weather_sensitive or self.rng.random()<.55),
            "block_type": self.rng.choice(["track_block", "possession", "line_block", "electrical_block"]),
            "electrical_isolation_required": bool(self.rng.random() < .32),
            "signalling_isolation_required": bool(self.rng.random() < .27),
            "weather_sensitive": weather_sensitive,
            "temperature_constraint": "none" if not weather_sensitive else self.rng.choice(["avoid_extreme_heat", "avoid_heavy_rain", "avoid_high_wind"]),
            "dependency_task_id": "",
            "task_status": self.rng.choice(["planned","approved","postponed","cancelled"], p=[.53,.27,.12,.08]),
        }

    def _latest_condition(self, asset_id: str) -> float:
        g = self.tables["asset_condition_history"]
        x = g[g.asset_id.eq(asset_id)].sort_values("timestamp")
        return float(x.condition_score.iloc[-1]) if len(x) else 75.0

    def generate_executions_and_blocks(self):
        tasks = self.tables["maintenance_tasks"]
        rows_exec, rows_req, rows_block = [], [], []
        for r in tasks.itertuples(index=False):
            if r.task_status == "cancelled":
                continue
            requested_start = pd.Timestamp(r.earliest_start) + pd.Timedelta(hours=int(self.rng.integers(0,72)))
            requested_end = requested_start + pd.Timedelta(minutes=int(r.estimated_duration_minutes))
            conflict = float(np.clip(self.rng.beta(2.2, 2.8),0,1))
            # Priority and safety dominate conflict.
            safety_need = 1.0 if r.priority == "P1" else .55 if r.priority == "P2" else .20
            approval_score = .60*safety_need + .25*(1-conflict) + .15*self.rng.random()
            decision = "approved" if approval_score > .63 else (
                "modified" if approval_score > .48 else (
                    "postponed" if r.task_status != "approved" else "rejected"))
            modified_shift = int(self.rng.integers(-90, 181)) if decision == "modified" else 0
            approved_start = requested_start + pd.Timedelta(minutes=modified_shift)
            approved_end = approved_start + pd.Timedelta(minutes=max(
                r.minimum_duration_minutes,
                int(r.estimated_duration_minutes * self.rng.uniform(.9, 1.15))))
            req_id = uid("REQ", len(rows_req)+1)
            rows_req.append({
                "request_id": req_id,
                "task_id": r.task_id,
                "section_id": r.section_id,
                "track_id": r.track_id,
                "request_timestamp": (requested_start - pd.Timedelta(days=int(self.rng.integers(1,12)))).isoformat(),
                "requested_start": requested_start.isoformat(),
                "requested_end": requested_end.isoformat(),
                "requested_duration_minutes": int(r.estimated_duration_minutes),
                "requesting_department": self.rng.choice(["track_engineering","signalling","electrical","asset_management"]),
                "priority": r.priority,
                "reason": r.task_description,
                "trains_affected_count": int(np.clip(self.rng.poisson(2 + 10*conflict),0,80)),
                "operational_conflict_score": round(conflict,4),
                "decision": decision,
                "decision_timestamp": (requested_start - pd.Timedelta(minutes=int(self.rng.integers(10, 24*60)))).isoformat(),
                "decision_reason": "safety priority" if safety_need > .8 and decision=="approved" else
                                   "traffic conflict" if conflict>.70 else "standard planning decision",
                "approved_start": approved_start.isoformat() if decision in ("approved","modified") else "",
                "approved_end": approved_end.isoformat() if decision in ("approved","modified") else "",
            })
            if decision not in ("approved","modified"):
                continue
            actual_start = approved_start + pd.Timedelta(minutes=int(self.rng.normal(0, 15)))
            planned = int(max(r.minimum_duration_minutes,
                              (approved_end - approved_start).total_seconds()/60))
            complexity = (r.maximum_duration_minutes / max(1,r.minimum_duration_minutes))
            actual_dur = int(np.clip(
                self.rng.normal(planned * (1 + .08*(complexity-1)), planned*.14),
                r.minimum_duration_minutes, r.maximum_duration_minutes))
            actual_end = actual_start + pd.Timedelta(minutes=actual_dur)
            overrun = max(0, actual_dur - planned)
            completion = "completed" if self.rng.random() < .88 else self.rng.choice(["completed_late","cancelled","partial"])
            if completion == "completed_late":
                overrun = max(overrun, int(self.rng.integers(5, 120)))
                actual_end = actual_start + pd.Timedelta(minutes=planned+overrun)
            rows_exec.append({
                "execution_id": uid("EXEC", len(rows_exec)+1),
                "task_id": r.task_id,
                "requested_start": requested_start.isoformat(),
                "requested_end": requested_end.isoformat(),
                "approved_start": approved_start.isoformat(),
                "approved_end": approved_end.isoformat(),
                "actual_start": actual_start.isoformat(),
                "actual_end": actual_end.isoformat(),
                "planned_duration_minutes": planned,
                "actual_duration_minutes": int(actual_dur + (overrun if completion=="completed_late" else 0)),
                "completion_status": completion,
                "delay_minutes": int(max(0, (actual_start-approved_start).total_seconds()/60)),
                "cancellation_flag": completion == "cancelled",
                "cancellation_reason": "resource conflict" if completion == "cancelled" else "",
                "block_requested": bool(r.block_required),
                "block_granted": True,
                "block_granted_duration_minutes": planned + r.safety_margin_minutes,
                "block_actual_duration_minutes": int(planned + overrun + r.safety_margin_minutes),
                "overrun_minutes": int(overrun),
                "overrun_reason": self.rng.choice(["weather","unknown","resource_delay","scope_growth","access_delay"]) if overrun > 0 else "",
            })
            if r.block_required and self.rng.random() < self.cfg.block_rate:
                block_id = uid("BLK", len(rows_block)+1)
                rows_block.append({
                    "block_id": block_id,
                    "request_id": req_id,
                    "section_id": r.section_id,
                    "track_id": r.track_id,
                    "block_type": r.block_type,
                    "purpose": r.task_category,
                    "planned_start": approved_start.isoformat(),
                    "planned_end": approved_end.isoformat(),
                    "actual_start": actual_start.isoformat(),
                    "actual_end": actual_end.isoformat(),
                    "duration_minutes": planned + r.safety_margin_minutes,
                    "actual_duration_minutes": int(planned + overrun + r.safety_margin_minutes),
                    "safety_margin_minutes": int(r.safety_margin_minutes),
                    "protection_required": True,
                    "electrical_isolation_required": bool(r.electrical_isolation_required),
                    "signalling_isolation_required": bool(r.signalling_isolation_required),
                    "affected_routes": f"ROUTE-{int(self.rng.integers(1, max(3, self.n(self.cfg.trains)//4))):05d}",
                    "status": "completed" if completion != "cancelled" else "cancelled",
                    "overrun_minutes": int(overrun),
                    "cancellation_reason": "maintenance cancelled" if completion == "cancelled" else "",
                })
        self.register("maintenance_execution", pd.DataFrame(rows_exec), "execution_id")
        self.register("block_requests", pd.DataFrame(rows_req), "request_id")
        self.register("blocks", pd.DataFrame(rows_block), "block_id")

    # ------------------------------------------------------------------
    # Trains, routes, movement and delays
    # ------------------------------------------------------------------

    def generate_trains(self):
        stations = self.tables["stations"]
        n = self.n(self.cfg.trains)
        rows = []
        for i in range(1,n+1):
            origin, dest = self.rng.choice(stations.station_id.to_numpy(), size=2, replace=False)
            ttype = self.rng.choice(["passenger","express","regional","commuter","freight","maintenance","inspection"],
                                    p=[.20,.12,.22,.20,.15,.07,.04])
            service = "passenger" if ttype in ("passenger","express","regional","commuter") else (
                "freight" if ttype=="freight" else "engineering")
            dep = self.start + pd.Timedelta(days=int(self.rng.integers(0,self.cfg.train_days)),
                                            minutes=int(self.rng.integers(0,1440)))
            distance = float(self.rng.lognormal(np.log(180),.65))
            speed = {"express":105,"passenger":75,"regional":65,"commuter":52,"freight":55,
                     "maintenance":35,"inspection":45}[ttype] * self.rng.uniform(.85,1.12)
            runtime = int(max(20, distance/speed*60))
            rows.append({
                "train_id": uid("TRAIN",i),
                "train_number": f"{int(self.rng.integers(10000,99999))}",
                "train_type": ttype,
                "service_type": service,
                "priority": "high" if ttype=="express" else "normal",
                "origin_station_id": origin,
                "destination_station_id": dest,
                "scheduled_departure": dep.isoformat(),
                "scheduled_arrival": (dep+pd.Timedelta(minutes=runtime)).isoformat(),
                "average_speed_kmh": round(float(speed),1),
                "capacity": int(self.rng.integers(300,1600) if service=="passenger" else self.rng.integers(500,4000)),
                "passenger_capacity": int(self.rng.integers(250,1600)) if service=="passenger" else 0,
                "freight_capacity": int(self.rng.integers(500,4000)) if service=="freight" else 0,
            })
        self.register("trains", pd.DataFrame(rows), "train_id")

    def generate_routes(self):
        sec = self.tables["track_sections"]
        stations = self.tables["stations"]
        adjacency: dict[str,list[tuple[str,str,float]]] = {}
        for r in sec.itertuples(index=False):
            adjacency.setdefault(r.from_station_id, []).append((r.to_station_id,r.section_id,r.length_km))
            adjacency.setdefault(r.to_station_id, []).append((r.from_station_id,r.section_id,r.length_km))
        rows=[]
        for i, tr in enumerate(self.tables["trains"].itertuples(index=False),1):
            # Bounded BFS-like greedy path. Falls back to a direct valid section.
            origin, dest = tr.origin_station_id, tr.destination_station_id
            path_stations=[origin]; path_sections=[]; dist=0.0
            current=origin; visited={origin}
            for _ in range(30):
                if current==dest: break
                nbrs=adjacency.get(current, [])
                candidates=[x for x in nbrs if x[0] not in visited]
                if not candidates:
                    break
                # Prefer destination if directly reachable; otherwise shortest available.
                direct=[x for x in candidates if x[0]==dest]
                if direct:
                    nxt=direct[0]
                else:
                    # Stable, process-independent choice; do not use Python hash().
                    def stable_score(x):
                        return sum(ord(ch) for ch in (x[0] + dest)) % 10000
                    nxt=min(candidates, key=stable_score)
                current, sid, length=nxt
                path_stations.append(current); path_sections.append(sid); dist+=length; visited.add(current)
            if current != dest or not path_sections:
                srow=sec.iloc[int(self.rng.integers(len(sec)))]
                path_sections=[srow.section_id]; path_stations=[srow.from_station_id,srow.to_station_id]; dist=srow.length_km
            rows.append({
                "route_id": uid("ROUTE",i),
                "origin_station_id": tr.origin_station_id,
                "destination_station_id": tr.destination_station_id,
                "section_sequence": "|".join(path_sections),
                "track_sequence": "",
                "direction": "up" if self.rng.random()<.5 else "down",
                "distance_km": round(dist,3),
                "estimated_runtime_minutes": int(max(10, tr.average_speed_kmh and dist/tr.average_speed_kmh*60)),
                "route_type": "through" if len(path_sections)>1 else "local",
            })
        self.register("routes", pd.DataFrame(rows), "route_id")

    def generate_movements_delays(self):
        sec = self.tables["track_sections"]
        tracks = self.tables["tracks"]
        trains = self.tables["trains"]
        blocks = self.tables["blocks"]
        weather = None  # generated later; delay drivers are represented from block/traffic/incidents.
        rows_m, rows_d = [], []
        section_len = sec.set_index("section_id")["length_km"].to_dict()
        track_by_sec = tracks.groupby("section_id")["track_id"].apply(list).to_dict()
        n_target = max(self.n(500_000), int(len(trains) * self.cfg.train_days * self.cfg.movements_per_train_day))
        active_blocks = blocks.copy()
        if len(active_blocks):
            active_blocks["_start"]=pd.to_datetime(active_blocks.actual_start,utc=True,format="mixed")
            active_blocks["_end"]=pd.to_datetime(active_blocks.actual_end,utc=True,format="mixed")
        for i in range(n_target):
            tr = trains.iloc[i % len(trains)]
            sec_id = str(sec.section_id.iloc[int(self.rng.integers(len(sec)))] )
            track_id = str(track_by_sec[sec_id][int(self.rng.integers(len(track_by_sec[sec_id])))] )
            date = self.start + pd.Timedelta(days=int(self.rng.integers(0,self.cfg.train_days)))
            entry = date.normalize() + pd.Timedelta(minutes=int(self.rng.integers(0,1440)))
            runtime = int(max(3, section_len[sec_id] / max(25, tr.average_speed_kmh) * 60))
            exit_ = entry + pd.Timedelta(minutes=runtime)
            # Operational drivers: block overlap and stochastic congestion.
            block_overlap = False
            if len(active_blocks) and self.rng.random()<.08:
                cand = active_blocks.iloc[int(self.rng.integers(len(active_blocks)))]
                block_overlap = (entry < cand["_end"]) and (exit_ > cand["_start"]) and (track_id == cand.track_id)
            congestion = self.rng.beta(2.1, 5.0)
            weather_factor = self.rng.beta(1.8, 7.0)
            incident_factor = self.rng.random() < self.cfg.incident_rate_per_section_year
            delay = float(np.clip(
                self.rng.normal(1.3*congestion + 0.8*weather_factor, 2.0)
                + (self.rng.integers(5,60) if block_overlap else 0)
                + (self.rng.integers(8,80) if incident_factor else 0),
                0, 180
            ))
            actual_entry=entry+pd.Timedelta(minutes=delay)
            actual_runtime=max(1,runtime+int(self.rng.normal(delay*.08,2)))
            actual_exit=actual_entry+pd.Timedelta(minutes=actual_runtime)
            rows_m.append({
                "movement_id": uid("MOVE",i+1), "train_id": tr.train_id,
                "date": date.date().isoformat(), "section_id": sec_id, "track_id": track_id,
                "scheduled_entry": entry.isoformat(), "scheduled_exit": exit_.isoformat(),
                "actual_entry": actual_entry.isoformat(), "actual_exit": actual_exit.isoformat(),
                "scheduled_runtime_minutes": runtime, "actual_runtime_minutes": actual_runtime,
                "delay_entry_minutes": round(float(delay),2),
                "delay_exit_minutes": round(float(max(delay, delay + self.rng.normal(0,1.5))),2),
                "speed_kmh": round(float(np.clip(section_len[sec_id]/(actual_runtime/60),10,160)),2),
            })
            if delay >= 2 or block_overlap or incident_factor:
                primary = "maintenance" if block_overlap else (
                    "incident" if incident_factor else self.rng.choice(["congestion","weather","infrastructure"]))
                reasons = ["maintenance","infrastructure","weather","rolling_stock","congestion","signalling"]
                rows_d.append({
                    "delay_id": uid("DELAY",len(rows_d)+1),
                    "train_id": tr.train_id, "date": date.date().isoformat(),
                    "station_id": tr.origin_station_id, "section_id": sec_id,
                    "delay_minutes": round(float(delay),2),
                    "delay_reason": primary,
                    "primary_reason": primary,
                    "secondary_reason": self.rng.choice(reasons),
                    "maintenance_related": primary=="maintenance",
                    "infrastructure_related": primary in ("infrastructure","maintenance"),
                    "weather_related": primary=="weather",
                    "rolling_stock_related": primary=="rolling_stock",
                    "congestion_related": primary=="congestion",
                    "signalling_related": primary=="signalling",
                })
        self.register("train_movements", pd.DataFrame(rows_m), "movement_id")
        self.register("train_delays", pd.DataFrame(rows_d), "delay_id")

    # ------------------------------------------------------------------
    # Resources / machines / weather / constraints / other tables
    # ------------------------------------------------------------------

    def generate_resources(self):
        stations=self.tables["stations"]
        n=self.n(self.cfg.resources)
        types=["maintenance_crew","engineering_crew","inspection_crew","signalling_crew","electrical_crew",
               "track_machine","crane","inspection_vehicle","tamping_machine","welding_equipment","rail_grinder"]
        rows=[]
        for i in range(1,n+1):
            typ=str(self.rng.choice(types))
            rows.append({
                "resource_id":uid("RES",i), "resource_type":typ,
                "resource_name":f"Synthetic {typ} {i:05d}",
                "home_station_id":stations.station_id.iloc[int(self.rng.integers(len(stations)))],
                "capability":typ.replace("_"," "),
                "capacity":int(self.rng.integers(1,5)) if "crew" in typ else 1,
                "skill_level":int(self.rng.integers(1,6)),
                "certification":self.rng.choice(["standard","advanced","specialist"]),
                "operating_status":self.rng.choice(["available","limited","maintenance"],p=[.90,.07,.03]),
            })
        self.register("resources",pd.DataFrame(rows),"resource_id")

    def generate_resource_availability(self):
        resources=self.tables["resources"]
        rows=[]
        for r in resources.itertuples(index=False):
            sample_days=self.rng.integers(20,self.cfg.train_days+1, size=8)
            for d in np.unique(sample_days):
                date=self.start+pd.Timedelta(days=int(d-1))
                shift=str(self.rng.choice(["day","night","swing"],p=[.55,.25,.20]))
                if shift=="day": s=6
                elif shift=="swing": s=14
                else: s=22
                start=date.normalize()+pd.Timedelta(hours=s)
                end=start+pd.Timedelta(hours=8 if shift!="night" else 7)
                rows.append({
                    "availability_id":uid("AVL",len(rows)+1),
                    "resource_id":r.resource_id,"date":date.date().isoformat(),
                    "available_start":start.isoformat(),"available_end":end.isoformat(),
                    "shift":shift,"maximum_work_hours":7.0 if shift!="night" else 6.5,
                    "break_requirement":30,"unavailable_reason":"" if self.rng.random()<.93 else "planned_leave",
                })
        self.register("resource_availability",pd.DataFrame(rows),"availability_id")

    def generate_task_resources(self):
        tasks=self.tables["maintenance_tasks"]
        res=self.tables["resources"]
        rows=[]
        for t in tasks.itertuples(index=False):
            count=int(self.rng.integers(1,4))
            choices=self.rng.choice(len(res),size=min(count,len(res)),replace=False)
            start=pd.Timestamp(t.earliest_start)
            end=start+pd.Timedelta(minutes=t.estimated_duration_minutes)
            for c in choices:
                rr=res.iloc[int(c)]
                rows.append({
                    "assignment_id":uid("ASSIGN",len(rows)+1),
                    "task_id":t.task_id,"resource_id":rr.resource_id,
                    "role":"lead" if len(rows)%count==0 else "support",
                    "planned_start":start.isoformat(),"planned_end":end.isoformat(),
                    "actual_start":"","actual_end":"",
                    "utilization_percent":round(float(self.rng.uniform(55,100)),2),
                })
        self.register("task_resources",pd.DataFrame(rows),"assignment_id")

    def generate_machines(self):
        stations=self.tables["stations"]; n=self.n(self.cfg.machines)
        rows=[]
        types=["track_machine","crane","inspection_vehicle","tamping_machine","welding_equipment","rail_grinder"]
        for i in range(1,n+1):
            last=self.start-pd.Timedelta(days=int(self.rng.integers(30,1800)))
            rows.append({
                "machine_id":uid("MCH",i),
                "machine_type":self.rng.choice(types),
                "capability":"railway maintenance",
                "current_station_id":stations.station_id.iloc[int(self.rng.integers(len(stations)))],
                "operating_status":self.rng.choice(["available","deployed","maintenance"],p=[.78,.16,.06]),
                "operating_hours":round(float(self.rng.uniform(100,30000)),1),
                "last_service_date":last.date().isoformat(),
                "next_service_date":(last+pd.Timedelta(days=int(self.rng.integers(180,600)))).date().isoformat(),
                "failure_rate":round(float(self.rng.beta(2,30)),5),
            })
        self.register("machines",pd.DataFrame(rows),"machine_id")

    def generate_weather(self):
        sec=self.tables["track_sections"]
        # 700 observations / selected section => >500k at full scale.
        rows=[]
        n_per=max(30,self.cfg.weather_obs_per_section)
        for r in sec.itertuples(index=False):
            base_temp=float(self.rng.normal(22,7))
            # Select a section-station-like pseudo climate seed; not true climate data.
            times=pd.date_range(self.start,self.end,periods=n_per,tz="UTC")
            phase=float(self.rng.uniform(0,2*np.pi))
            for t in times:
                season=math.sin(2*math.pi*(t.dayofyear/365.25)+phase)
                hour=math.sin(2*math.pi*(t.hour/24))
                temp=base_temp+5*season+2*hour+self.rng.normal(0,1.7)
                rain_prob=.12+.18*max(0,season*-0.5)+.05*(self.rng.random()<.05)
                rain=max(0,float(self.rng.gamma(1.4,2.0)-1.2)) if self.rng.random()<rain_prob else 0.0
                wind=max(0,float(self.rng.normal(17+4*rain_prob,5)))
                humidity=clamp(65+16*rain_prob+rain*1.8+self.rng.normal(0,7),10,100)
                visibility=clamp(15-rain*1.8-self.rng.normal(0,1.1),.2,20)
                extreme=bool((rain>35) or (wind>65) or (temp>45))
                condition="clear" if rain<.5 and visibility>10 else (
                    "rain" if rain>=.5 else "fog" if visibility<2 else "wind")
                rows.append({
                    "weather_id":uid("WTH",len(rows)+1),
                    "timestamp":t.isoformat(),"section_id":r.section_id,
                    "latitude":round(float(self.rng.normal(20,4)),6),
                    "longitude":round(float(self.rng.normal(80,5)),6),
                    "temperature_c":round(temp,2),"humidity_percent":round(humidity,2),
                    "rainfall_mm":round(rain,2),"wind_speed_kmh":round(wind,2),
                    "visibility_km":round(visibility,2),"weather_condition":condition,
                    "flooding_flag":bool(rain>60),"extreme_weather_flag":extreme,
                })
        self.register("weather",pd.DataFrame(rows),"weather_id")

    def generate_weather_forecast(self):
        sec=self.tables["track_sections"]
        rows=[]
        n_per=max(10,self.cfg.forecast_per_section)
        for r in sec.itertuples(index=False):
            times=pd.date_range(self.start,self.end,periods=n_per,tz="UTC")
            for t in times:
                rain_prob=float(np.clip(self.rng.normal(.25,.15),.01,.98))
                expected=float(max(0,self.rng.gamma(1.8,3)*rain_prob))
                rows.append({
                    "forecast_id":uid("FCST",len(rows)+1),
                    "forecast_created_at":(t-pd.Timedelta(hours=12)).isoformat(),
                    "forecast_for":t.isoformat(),"section_id":r.section_id,
                    "temperature_forecast_c":round(float(self.rng.normal(22,8)),2),
                    "rainfall_probability":round(rain_prob,4),
                    "expected_rainfall_mm":round(expected,2),
                    "wind_speed_forecast_kmh":round(float(max(0,self.rng.normal(20,7))),2),
                    "visibility_forecast_km":round(float(np.clip(self.rng.normal(10,3),.2,20)),2),
                    "extreme_weather_probability":round(float(np.clip(rain_prob*.12+self.rng.random()*.04,0,1)),4),
                })
        self.register("weather_forecast",pd.DataFrame(rows),"forecast_id")

    def generate_speed_restrictions(self):
        defects=self.tables["defects"]
        rows=[]
        for d in defects.itertuples(index=False):
            if not d.speed_restriction_applied: continue
            start=pd.Timestamp(d.detected_timestamp)
            end=start+pd.Timedelta(hours=int(self.rng.integers(6,72)))
            asset=self.tables["assets"].loc[self.tables["assets"].asset_id.eq(d.asset_id)].iloc[0]
            track=self.tables["tracks"].loc[self.tables["tracks"].track_id.eq(asset.track_id)].iloc[0]
            rows.append({
                "restriction_id":uid("SR",len(rows)+1),
                "section_id":d.section_id,"track_id":asset.track_id,
                "start_chainage_m":d.location_chainage_m,
                "end_chainage_m":min(d.location_chainage_m+100, asset.chainage_end_m),
                "start_timestamp":start.isoformat(),"end_timestamp":end.isoformat(),
                "normal_speed_kmh":track.maximum_speed_kmh,
                "restricted_speed_kmh":int(d.speed_restriction_kmh),
                "reason":"defect",
                "related_asset_id":d.asset_id,"related_defect_id":d.defect_id,
            })
        self.register("speed_restrictions",pd.DataFrame(rows),"restriction_id")

    def generate_incidents_emergency(self):
        defects=self.tables["defects"]
        incidents=[]; emergency=[]
        failed=defects[defects.failure_occurred]
        for d in failed.itertuples(index=False):
            ts=pd.Timestamp(d.detected_timestamp)+pd.Timedelta(hours=int(self.rng.integers(1,240)))
            incident_id=uid("INC",len(incidents)+1)
            severe=d.severity in ("high","critical")
            incidents.append({
                "incident_id":incident_id,"timestamp":ts.isoformat(),"section_id":d.section_id,
                "track_id":self.tables["assets"].loc[self.tables["assets"].asset_id.eq(d.asset_id),"track_id"].iloc[0],
                "asset_id":d.asset_id,"incident_type":"infrastructure_failure",
                "severity":d.severity,"cause":d.root_cause,"train_affected":bool(severe or self.rng.random()<.6),
                "delay_minutes":int(self.rng.integers(10,180) if severe else self.rng.integers(0,60)),
                "emergency_block_required":bool(severe),"passengers_affected":int(self.rng.integers(0,3000)),
                "service_cancelled":bool(severe and self.rng.random()<.35),
                "resolution_time_minutes":int(self.rng.integers(30,600)),
            })
            if severe and self.rng.random()<.8:
                failure=ts
                start=failure+pd.Timedelta(minutes=int(self.rng.integers(5,45)))
                end=start+pd.Timedelta(minutes=int(self.rng.integers(60,900)))
                emergency.append({
                    "emergency_id":uid("EMG",len(emergency)+1),
                    "incident_id":incident_id,"asset_id":d.asset_id,"section_id":d.section_id,
                    "detection_time":pd.Timestamp(d.detected_timestamp).isoformat(),
                    "failure_time":failure.isoformat(),
                    "emergency_response_time_minutes":int((start-failure).total_seconds()/60),
                    "emergency_block_start":start.isoformat(),"emergency_block_end":end.isoformat(),
                    "repair_duration_minutes":int((end-start).total_seconds()/60),
                    "cause":d.root_cause,"severity":d.severity,
                    "train_delay_minutes":incidents[-1]["delay_minutes"],
                    "estimated_cost":round(float(self.rng.lognormal(10.8,.8)),2),
                })
        self.register("incidents",pd.DataFrame(incidents),"incident_id")
        self.register("emergency_maintenance",pd.DataFrame(emergency),"emergency_id")

    def generate_costs_materials(self):
        tasks=self.tables["maintenance_tasks"]
        rows=[]
        for t in tasks.itertuples(index=False):
            labor=50*t.estimated_duration_minutes*(1.0+float(t.criticality))
            machine=100*self.rng.lognormal(0,0.4) if t.block_required else 0
            material=150*self.rng.lognormal(0,0.8)
            possession=250*self.rng.lognormal(0,0.5) if t.block_required else 0
            disruption=100*t.estimated_duration_minutes*(.4 if t.priority in ("P1","P2") else .15)
            emergency=0 if t.task_category=="corrective" else 0
            total=labor+machine+material+possession+disruption+emergency
            rows.append({
                "cost_id":uid("COST",len(rows)+1),"task_id":t.task_id,
                "labor_cost":round(labor,2),"machine_cost":round(machine,2),
                "material_cost":round(material,2),"possession_cost":round(possession,2),
                "disruption_cost":round(disruption,2),"emergency_cost":round(emergency,2),
                "total_cost":round(total,2),"currency":"INR",
            })
        self.register("maintenance_cost",pd.DataFrame(rows),"cost_id")

        st=self.tables["stations"]
        materials=["rail_fastener","rail_piece","sleeper","ballast","signal_module",
                   "cable","contact_wire","point_machine_component","drainage_pipe","welding_wire"]
        mr=[]
        for i in range(1,self.n(self.cfg.materials)+1):
            mr.append({
                "material_id":uid("MAT",i),"material_type":self.rng.choice(materials),
                "quantity_available":round(float(self.rng.uniform(50,5000)),1),
                "storage_station_id":st.station_id.iloc[int(self.rng.integers(len(st)))],
                "unit":self.rng.choice(["unit","m","kg","tonne"]),
                "unit_cost":round(float(self.rng.lognormal(5.6,1.0)),2),
                "lead_time_days":int(self.rng.integers(1,45)),
                "reserved_quantity":round(float(self.rng.uniform(0,500)),1),
                "reorder_level":round(float(self.rng.uniform(20,800)),1),
            })
        self.register("materials",pd.DataFrame(mr),"material_id")

        mats=self.tables["materials"]
        tmat=[]
        for t in tasks.itertuples(index=False):
            m=mats.iloc[int(self.rng.integers(len(mats)))]
            qty=round(float(self.rng.uniform(.5,30)),2)
            used=round(qty*self.rng.uniform(.8,1),2)
            tmat.append({
                "task_material_id":uid("TMAT",len(tmat)+1),"task_id":t.task_id,
                "material_id":m.material_id,"quantity_required":qty,"quantity_used":used,
                "availability_status":"available" if m.quantity_available>qty else "backordered",
            })
        self.register("task_materials",pd.DataFrame(tmat),"task_material_id")

    def generate_safety_signalling_planning_versions(self):
        safety_rows=[]
        for country in self.cfg.country_mix:
            c=country_config(country)
            for i, cat in enumerate(["possession","electrical_isolation","signalling_isolation","personnel","weather"],1):
                safety_rows.append({
                    "constraint_id":f"CON-{country[:2].upper()}-{i:03d}",
                    "jurisdiction":country,"ruleset_id":c["safety_ruleset_id"],
                    "rule_category":cat,"rule_code":f"{c['safety_ruleset_id']}-{i:03d}",
                    "description":f"Synthetic {cat} safety constraint",
                    "asset_type":self.rng.choice(ASSET_TYPES),
                    "track_type":self.rng.choice(["running","yard"]),
                    "minimum_block_duration_minutes":int(self.rng.integers(15,60)),
                    "minimum_clearance_minutes":int(self.rng.integers(5,30)),
                    "required_isolation":"electrical" if cat=="electrical_isolation" else "none",
                    "required_protection":"lookout" if cat in ("possession","personnel") else "signalling",
                    "required_personnel":int(self.rng.integers(1,6)),
                    "weather_restriction":"no_extreme_weather" if cat=="weather" else "none",
                    "severity":"critical" if cat in ("possession","electrical_isolation") else "high",
                    "hard_constraint":True,
                })
        self.register("safety_constraints",pd.DataFrame(safety_rows),"constraint_id")

        sec=self.tables["track_sections"]; st=self.tables["stations"]
        sig=[]
        for i in range(1,self.n(self.cfg.sections)*2+1):
            section=sec.iloc[(i-1)%len(sec)]
            station=st.iloc[int(self.rng.integers(len(st)))]
            sig.append({
                "signal_id":uid("SIG",i),"section_id":section.section_id,"station_id":station.station_id,
                "signal_type":self.rng.choice(["home","starter","distant","shunt"]),
                "location_chainage_m":round(float(self.rng.uniform(0,section.length_km*1000)),2),
                "direction":self.rng.choice(["up","down"]),"interlocking_type":self.rng.choice(["electronic","relay"]),
                "control_system":self.rng.choice(["centralized","local","remote"]),"track_circuit":bool(self.rng.random()<.62),
                "axle_counter":bool(self.rng.random()<.35),"route_dependency":f"ROUTE-{int(self.rng.integers(1,max(3,self.n(self.cfg.trains)//3))):05d}",
            })
        self.register("signalling",pd.DataFrame(sig),"signal_id")

        tasks=self.tables["maintenance_tasks"]; req=self.tables["block_requests"]
        rows=[]
        for i,t in enumerate(tasks.itertuples(index=False),1):
            request_id=req.loc[req.task_id.eq(t.task_id),"request_id"].iloc[0] if t.task_id in set(req.task_id) else ""
            system = "approve" if t.priority in ("P1","P2") else self.rng.choice(["approve","modify","postpone"])
            planner = system if self.rng.random()<.7 else self.rng.choice(["approve","modify","postpone","reject"])
            rows.append({
                "decision_id":uid("DEC",i),"task_id":t.task_id,"request_id":request_id,
                "scenario_id":f"SCEN-{int(self.rng.integers(1,5000)):06d}",
                "planner_id":f"PLANNER-{int(self.rng.integers(1,250)):04d}",
                "system_recommendation":system,"planner_decision":planner,
                "decision_reason":"safety priority" if t.priority=="P1" else "operational trade-off",
                "approval_status":"approved" if planner in ("approve","modify") else "rejected",
                "timestamp":(pd.Timestamp(t.earliest_start)-pd.Timedelta(hours=int(self.rng.integers(1,48)))).isoformat(),
                "final_schedule":pd.Timestamp(t.earliest_start).isoformat(),
                "actual_outcome":"completed" if t.task_status=="approved" else t.task_status,
            })
        self.register("planning_decisions",pd.DataFrame(rows),"decision_id")

        versions = pd.DataFrame([{
            "timetable_version_id":"TT-0001","created_at":self.start.isoformat(),
            "valid_from":self.start.date().isoformat(),"valid_until":self.end.date().isoformat(),
            "reason_changed":"synthetic baseline timetable","affected_train_count":len(self.tables["trains"]),
        }])
        self.register("timetable_versions",versions,"timetable_version_id")

        versions2=pd.DataFrame([{
            "plan_version_id":"BP-0001","created_at":self.start.isoformat(),
            "valid_from":self.start.date().isoformat(),"valid_until":self.end.date().isoformat(),
            "reason_changed":"synthetic baseline maintenance block plan",
            "modified_by":"planner_system","affected_block_count":len(self.tables["blocks"]),
        }])
        self.register("block_plan_versions",versions2,"plan_version_id")

    def generate_traffic_demand(self):
        sec=self.tables["track_sections"]; rows=[]
        days=max(365,self.cfg.train_days)
        # Sample ~monthly demand cells per section, then derive train counts/volume.
        sample_per_section=max(6, min(36, days//30))
        for r in sec.itertuples(index=False):
            for d in range(sample_per_section):
                date=self.start+pd.Timedelta(days=int(d*(days/max(1,sample_per_section-1))))
                weekday=date.dayofweek
                season=1+0.12*math.sin(2*math.pi*date.dayofyear/365.25)
                base=max(5,int(r.capacity_trains_per_day*self.rng.uniform(.35,.85)*season))
                passenger=max(0,int(base*self.rng.uniform(.5,.85)*(1.12 if weekday<5 else .88)))
                freight=max(0,base-passenger+int(self.rng.integers(-2,3)))
                rows.append({
                    "demand_id":uid("DEM",len(rows)+1),"date":date.date().isoformat(),
                    "section_id":r.section_id,
                    "passenger_volume":int(passenger*self.rng.integers(20,120)),
                    "freight_volume":int(freight*self.rng.integers(10,90)),
                    "train_count":base,"passenger_train_count":passenger,
                    "freight_train_count":freight,
                    "peak_hour":int(self.rng.choice([7,8,9,17,18,19],p=[.1,.2,.15,.18,.22,.15])),
                    "capacity_utilization_percent":round(float(np.clip(self.rng.normal(68,16),20,100)),2),
                })
        self.register("traffic_demand",pd.DataFrame(rows),"demand_id")

    def generate_provenance(self):
        rows=[]
        for table, df in self.tables.items():
            pk=self.pk.get(table)
            if pk and pk in df.columns:
                ids=df[pk].astype(str)
            else:
                ids=pd.Series(np.arange(1,len(df)+1).astype(str))
            for rid in ids:
                rows.append({
                    "provenance_id":uid("PROV",len(rows)+1),
                    "table_name":table,"record_id":rid,
                    "source_type":"synthetic_generator","source_name":"Rail-Yojna Generator",
                    "generation_method":"causal_relational_simulation",
                    "generation_timestamp":datetime.now(timezone.utc).isoformat(),
                    "data_quality_score":round(float(self.rng.uniform(.96,1.0)),4),
                    "synthetic_flag":True,"derived_flag":False,
                })
        self.register("data_provenance",pd.DataFrame(rows),"provenance_id")

    # ------------------------------------------------------------------
    # ML target definitions
    # ------------------------------------------------------------------

    def generate_target_definition(self):
        rows=[
            {
                "target_name":"failure_within_7_days","table":"asset_condition_history",
                "definition":"1 if an incident/emergency failure for the same asset occurs in the next 7 days; otherwise 0.",
                "label_source":"incidents + emergency_maintenance",
                "prediction_timestamp_required":True,"leakage_warning":"Do not use any event after prediction timestamp.",
            },
            {
                "target_name":"failure_within_30_days","table":"asset_condition_history",
                "definition":"1 if failure occurs in the next 30 days for the same asset.",
                "label_source":"incidents + emergency_maintenance",
                "prediction_timestamp_required":True,"leakage_warning":"Future events must not be features.",
            },
            {
                "target_name":"failure_within_90_days","table":"asset_condition_history",
                "definition":"1 if failure occurs in the next 90 days for the same asset.",
                "label_source":"incidents + emergency_maintenance",
                "prediction_timestamp_required":True,"leakage_warning":"Future events must not be features.",
            },
            {
                "target_name":"maintenance_required_within_30_days","table":"asset_condition_history",
                "definition":"1 if a maintenance task for the same asset is planned/approved within 30 days after observation.",
                "label_source":"maintenance_tasks",
                "prediction_timestamp_required":True,"leakage_warning":"Do not use task status/outcomes observed after prediction time.",
            },
            {
                "target_name":"expected_maintenance_duration","table":"maintenance_tasks",
                "definition":"Continuous target derived from actual execution duration for completed tasks.",
                "label_source":"maintenance_execution",
                "prediction_timestamp_required":True,"leakage_warning":"Actual duration cannot be an input.",
            },
            {
                "target_name":"block_overrun","table":"maintenance_execution",
                "definition":"1 when actual block duration exceeds planned block duration.",
                "label_source":"maintenance_execution / blocks",
                "prediction_timestamp_required":True,"leakage_warning":"Actual end times cannot be features.",
            },
            {
                "target_name":"train_delay_minutes","table":"train_movements",
                "definition":"Observed entry/exit delay in minutes for a movement.",
                "label_source":"train_movements",
                "prediction_timestamp_required":True,"leakage_warning":"No future movement delay values as features.",
            },
            {
                "target_name":"emergency_maintenance_required","table":"incidents",
                "definition":"1 when an incident creates a corresponding emergency maintenance record.",
                "label_source":"emergency_maintenance",
                "prediction_timestamp_required":True,"leakage_warning":"Do not join future emergency records into pre-failure features.",
            },
        ]
        self.register("target_definition",pd.DataFrame(rows))

    # ------------------------------------------------------------------
    # Schema/provenance metadata
    # ------------------------------------------------------------------

    def build_relationships(self) -> pd.DataFrame:
        rows = []
        def fk(table, column, ref_table, ref_column):
            self.fks.append((table,column,ref_table,ref_column))
            rows.append({
                "table_name":table,"column_name":column,
                "referenced_table":ref_table,"referenced_column":ref_column,
                "relationship_type":"foreign_key"
            })
        fk("stations","network_id","networks","network_id")
        fk("track_sections","network_id","networks","network_id")
        fk("track_sections","from_station_id","stations","station_id")
        fk("track_sections","to_station_id","stations","station_id")
        fk("tracks","section_id","track_sections","section_id")
        fk("assets","track_id","tracks","track_id")
        fk("assets","section_id","track_sections","section_id")
        fk("assets","station_id","stations","station_id")
        fk("asset_condition_history","asset_id","assets","asset_id")
        fk("inspections","asset_id","assets","asset_id")
        fk("defects","asset_id","assets","asset_id")
        fk("defects","section_id","track_sections","section_id")
        fk("maintenance_tasks","asset_id","assets","asset_id")
        fk("maintenance_tasks","section_id","track_sections","section_id")
        fk("maintenance_tasks","track_id","tracks","track_id")
        fk("maintenance_execution","task_id","maintenance_tasks","task_id")
        fk("block_requests","task_id","maintenance_tasks","task_id")
        fk("block_requests","section_id","track_sections","section_id")
        fk("block_requests","track_id","tracks","track_id")
        fk("blocks","request_id","block_requests","request_id")
        fk("blocks","section_id","track_sections","section_id")
        fk("blocks","track_id","tracks","track_id")
        fk("trains","origin_station_id","stations","station_id")
        fk("trains","destination_station_id","stations","station_id")
        fk("train_movements","train_id","trains","train_id")
        fk("train_movements","section_id","track_sections","section_id")
        fk("train_movements","track_id","tracks","track_id")
        fk("train_delays","train_id","trains","train_id")
        fk("train_delays","station_id","stations","station_id")
        fk("train_delays","section_id","track_sections","section_id")
        fk("routes","origin_station_id","stations","station_id")
        fk("routes","destination_station_id","stations","station_id")
        fk("resources","home_station_id","stations","station_id")
        fk("resource_availability","resource_id","resources","resource_id")
        fk("task_resources","task_id","maintenance_tasks","task_id")
        fk("task_resources","resource_id","resources","resource_id")
        fk("machines","current_station_id","stations","station_id")
        fk("weather","section_id","track_sections","section_id")
        fk("weather_forecast","section_id","track_sections","section_id")
        fk("speed_restrictions","section_id","track_sections","section_id")
        fk("speed_restrictions","track_id","tracks","track_id")
        fk("speed_restrictions","related_asset_id","assets","asset_id")
        fk("speed_restrictions","related_defect_id","defects","defect_id")
        fk("incidents","section_id","track_sections","section_id")
        fk("incidents","track_id","tracks","track_id")
        fk("incidents","asset_id","assets","asset_id")
        fk("emergency_maintenance","incident_id","incidents","incident_id")
        fk("emergency_maintenance","asset_id","assets","asset_id")
        fk("emergency_maintenance","section_id","track_sections","section_id")
        fk("maintenance_cost","task_id","maintenance_tasks","task_id")
        fk("task_materials","task_id","maintenance_tasks","task_id")
        fk("task_materials","material_id","materials","material_id")
        fk("materials","storage_station_id","stations","station_id")
        fk("signalling","section_id","track_sections","section_id")
        fk("signalling","station_id","stations","station_id")
        fk("planning_decisions","task_id","maintenance_tasks","task_id")
        fk("planning_decisions","request_id","block_requests","request_id")
        fk("traffic_demand","section_id","track_sections","section_id")
        return pd.DataFrame(rows)

    def build_data_dictionary(self) -> pd.DataFrame:
        rel = self.build_relationships()
        fk_map={(r.table_name,r.column_name):(r.referenced_table,r.referenced_column)
                for r in rel.itertuples(index=False)}
        rows=[]
        for table, cols in self.schemas.items():
            df=self.tables[table]
            for c in cols:
                fkref=fk_map.get((table,c),("",""))
                dtype=str(df[c].dtype)
                unit=""
                if any(x in c.lower() for x in ("minutes","duration")): unit="minutes"
                if "kmh" in c.lower() or "speed" in c.lower(): unit="km/h"
                if "percent" in c.lower() or "probability" in c.lower() or "rate" in c.lower(): unit="%/ratio"
                if c.endswith("_m") or "chainage" in c: unit="m"
                if c.endswith("_km"): unit="km"
                if "cost" in c: unit="currency"
                example="" if len(df)==0 else str(df[c].iloc[0])
                rows.append({
                    "table_name":table,"column_name":c,
                    "description":f"Synthetic {c.replace('_',' ')} field for {table}.",
                    "data_type":dtype,"unit":unit,"example_value":example,
                    "nullable":bool(df[c].isna().any() or (df[c].astype(str)=="").any()),
                    "primary_key":c==self.pk.get(table),
                    "foreign_key":bool(fkref[0]),
                    "referenced_table":fkref[0],
                    "referenced_column":fkref[1],
                    "derived":table in {"train_delays","maintenance_cost","target_definition"},
                    "synthetic":True,
                    "allowed_values":"",
                    "generation_logic":"Generated by causal/temporal synthetic simulation; see README.md.",
                })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        issues=[]
        def record(metric, value, status="PASS", details=""):
            issues.append({"metric":metric,"value":value,"status":status,"details":details})

        total=sum(len(x) for x in self.tables.values())
        record("total_records",total,"PASS" if total>=1_000_000*self.cfg.scale*.75 else "WARN")

        # Primary keys
        for table, pk in self.pk.items():
            df=self.tables[table]
            dup=int(df[pk].duplicated().sum())
            record(f"{table}.duplicate_primary_keys",dup,"PASS" if dup==0 else "FAIL")

        # Foreign keys
        fk_viol=0
        for table,col,rt,rc in self.fks:
            if table not in self.tables or col not in self.tables[table].columns:
                continue
            valid=set(self.tables[rt][rc].astype(str))
            vals=self.tables[table][col].astype(str)
            bad=int((~vals.isin(valid) & (vals!="") & (vals!="nan")).sum())
            fk_viol += bad
            if bad:
                record(f"{table}.{col}-> {rt}.{rc}",bad,"FAIL")
        record("FOREIGN_KEY_VIOLATIONS",fk_viol,"PASS" if fk_viol==0 else "FAIL")

        # Timestamp order checks.
        timestamp_viol=0
        for table,pairs in {
            "maintenance_execution":[("actual_start","actual_end"),("approved_start","approved_end")],
            "block_requests":[("requested_start","requested_end"),("approved_start","approved_end")],
            "blocks":[("actual_start","actual_end"),("planned_start","planned_end")],
        }.items():
            df=self.tables.get(table)
            if df is None: continue
            for a,b in pairs:
                x=pd.to_datetime(df[a],utc=True,errors="coerce")
                y=pd.to_datetime(df[b],utc=True,errors="coerce")
                mask=x.notna() & y.notna() & (y<x)
                bad=int(mask.sum()); timestamp_viol+=bad
        record("INVALID_TIMESTAMP_RELATIONSHIPS",timestamp_viol,"PASS" if timestamp_viol==0 else "FAIL")

        impossible=0
        # Universal numerical sanity checks.
        for table, df in self.tables.items():
            numeric=df.select_dtypes(include=[np.number])
            impossible += int(np.isinf(numeric.to_numpy()).sum()) if not numeric.empty else 0
            if "condition_score" in df:
                impossible += int(((df.condition_score<0)|(df.condition_score>100)).sum())
            for c in ("capacity_utilization_percent","humidity_percent"):
                if c in df:
                    impossible += int(((df[c]<0)|(df[c]>100)).sum())
            for c in ("actual_duration_minutes","planned_duration_minutes","duration_minutes"):
                if c in df:
                    impossible += int((df[c]<0).sum())
        record("IMPOSSIBLE_VALUE_COUNT",impossible,"PASS" if impossible==0 else "FAIL")

        miss_total=sum(int(df.isna().sum().sum()) for df in self.tables.values())
        cells_total=sum(int(df.shape[0]*df.shape[1]) for df in self.tables.values())
        miss_pct=100*miss_total/max(1,cells_total)
        record("missing_value_percentage",round(miss_pct,4),"PASS" if miss_pct<=3.0 else "WARN")

        # Class balances for available event/target proxies.
        class_rows=[]
        defs=self.tables.get("defects",pd.DataFrame())
        if len(defs):
            class_rows.append({"target":"failure_occurred","positive_rate":float(defs.failure_occurred.mean())})
        exe=self.tables.get("maintenance_execution",pd.DataFrame())
        if len(exe):
            class_rows.append({"target":"block_overrun","positive_rate":float((exe.overrun_minutes>0).mean())})
        inc=self.tables.get("incidents",pd.DataFrame())
        if len(inc):
            class_rows.append({"target":"emergency_maintenance_required","positive_rate":float(inc.incident_id.isin(set(self.tables["emergency_maintenance"].incident_id)).mean())})

        # Corruption audit: records intentionally touched can be kept in a separate report.
        if self.cfg.introduce_corruption:
            record("intentional_corruption_records",len(self.corruption_records),"INFO",
                   "These records are tagged in corruption_manifest.csv and excluded from clean validation semantics.")

        return pd.DataFrame(issues), pd.DataFrame(class_rows)

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def apply_optional_corruption(self):
        if not self.cfg.introduce_corruption:
            return
        # Keep corruption small and explicit. Clean source tables remain logically
        # recoverable because every changed field is recorded in the manifest.
        for table in ["asset_condition_history","inspections","train_movements"]:
            df=self.tables[table]
            n=max(1,int(len(df)*self.cfg.corruption_rate))
            idx=self.rng.choice(len(df),size=min(n,len(df)),replace=False)
            for i in idx[:max(1,n//3)]:
                row=int(i)
                if table=="asset_condition_history":
                    old=df.at[row,"measurement_value"]
                    df.at[row,"measurement_value"]=np.nan
                    self.corruption_records.append({"table":table,"row_index":row,"column":"measurement_value","old_value":old,"new_value":None,"reason":"missing_sensor_value"})
                elif table=="inspections":
                    old=df.at[row,"inspection_quality"]
                    df.at[row,"inspection_quality"]=np.nan
                    self.corruption_records.append({"table":table,"row_index":row,"column":"inspection_quality","old_value":old,"new_value":None,"reason":"missing_inspection_field"})
                else:
                    old=df.at[row,"speed_kmh"]
                    df.at[row,"speed_kmh"]=np.nan
                    self.corruption_records.append({"table":table,"row_index":row,"column":"speed_kmh","old_value":old,"new_value":None,"reason":"telemetry_gap"})

    def write_outputs(self, output: Path):
        output.mkdir(parents=True,exist_ok=True)
        for table, df in self.tables.items():
            path=output/f"{table}.csv"
            df.to_csv(path,index=False)
            if self.cfg.write_parquet:
                try: df.to_parquet(output/f"{table}.parquet",index=False)
                except Exception as e:
                    print(f"[WARN] parquet skipped for {table}: {e}", file=sys.stderr)

        relationships=self.build_relationships()
        relationships.to_csv(output/"schema_relationships.csv",index=False)
        self.build_data_dictionary().to_csv(output/"data_dictionary.csv",index=False)

        config=asdict(self.cfg)
        config.update({
            "dataset_name":DATASET_NAME,
            "generator_version":GENERATOR_VERSION,
            "run_id":self.run_id,
            "actual_seed":self.cfg.seed,
            "generated_at_utc":datetime.now(timezone.utc).isoformat(),
            "scale":self.cfg.scale,
        })
        (output/"generation_config.json").write_text(json.dumps(config,indent=2),encoding="utf-8")

        validation,class_balance=self.validate()
        validation.to_csv(output/"data_quality_report.csv",index=False)
        class_balance.to_csv(output/"target_class_balance.csv",index=False)

        if self.corruption_records:
            pd.DataFrame(self.corruption_records).to_csv(output/"corruption_manifest.csv",index=False)

        # README
        counts="\n".join(f"- `{k}.csv`: {len(v):,} records" for k,v in self.tables.items())
        fk_text="\n".join(f"- `{a}.{b}` → `{c}.{d}`" for a,b,c,d in self.fks)
        readme=f"""# Rail-Yojna Synthetic Research Dataset

## Purpose

This directory is generated by `rail_yojna_dataset_generator.py` for the Rail-Yojna
academic/research prototype: AI-assisted railway maintenance and block-planning
decision support.

**All records are synthetic.** They are not copied from railway infrastructure or
operational systems and must not be used for live signalling, dispatching,
automatic route setting, train control, or safety-critical decisions.

## Generation methodology

The generator builds the network first, then assets and longitudinal condition
trajectories, and then derives inspections, defects, maintenance requests,
possession/block decisions, executions, traffic interactions, delays, incidents,
emergency maintenance, cost, resource, material, weather, and planning records.

The intended causal chain is:

`asset age → condition → degradation → defect → priority → maintenance request → block conflict → planner decision → execution → outcome`

and, where maintenance is deferred:

`deterioration → postponement → worsening defect → failure → emergency block → train delay → operational cost`

Time is generated continuously across the configured historical window. Weather uses
seasonal, diurnal, geographic-seed, and event-clustering patterns. Train movement
records are constrained to real generated trains, sections, and tracks.

## Tables

{counts}

## Key relationships

{fk_text}

## ML target guidance

See `target_definition.csv`. Targets should be constructed relative to a prediction
timestamp. Do not use future events, actual outcomes, actual block end times, or
future delay values as features.

Recommended temporal split is approximately:
- Training: 2022–2024
- Validation: 2025
- Testing: 2026 (or the final chronological holdout configured for a run)

## Data quality

`data_quality_report.csv` is generated after construction. A clean run is expected to
report:

`FOREIGN_KEY_VIOLATIONS = 0`

`INVALID_TIMESTAMP_RELATIONSHIPS = 0`

Optional corruption is disabled by default. When enabled, affected cells are listed
in `corruption_manifest.csv` so research on noisy data remains auditable.

## Reproducibility

The seed and complete generation configuration are stored in `generation_config.json`.
Running the same generator/version/configuration/seed produces the same values apart
from run identifiers and generation timestamps.

## Safety limitation

The dataset can support research on optimization and decision support, but safety
rules represented in `safety_constraints.csv` are synthetic abstractions. They are
not a substitute for local railway rules, engineering standards, signalling
interlocking logic, possession authorities, or human safety validation.
"""
        (output/"README.md").write_text(readme,encoding="utf-8")

        # Table-level statistics summary.
        stats=[]
        for table,df in self.tables.items():
            stats.append({
                "table_name":table,"record_count":len(df),
                "column_count":df.shape[1],
                "null_cells":int(df.isna().sum().sum()),
                "duplicate_rows":int(df.duplicated().sum()),
                "memory_mb":round(df.memory_usage(deep=True).sum()/1024/1024,2),
            })
        pd.DataFrame(stats).to_csv(output/"statistics_summary.csv",index=False)

        if self.cfg.write_sqlite:
            self.write_sqlite(output/"rail_yojna.sqlite")

        return validation

    def write_sqlite(self, path: Path):
        import sqlite3
        with sqlite3.connect(path) as conn:
            for table, df in self.tables.items():
                df.to_sql(table, conn, if_exists="replace", index=False)
            self.build_relationships().to_sql("schema_relationships",conn,if_exists="replace",index=False)

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run(self, output: Path):
        start=time.time()
        print("[1/8] network...")
        self.generate_networks()
        self.generate_stations()
        self.generate_track_sections()
        self.generate_tracks()

        print("[2/8] assets and condition...")
        self.generate_assets()
        self.generate_condition_history()
        self.generate_inspections()
        self.generate_defects()

        print("[3/8] maintenance and blocks...")
        self.generate_maintenance_tasks()
        self.generate_executions_and_blocks()

        print("[4/8] trains and operations...")
        self.generate_trains()
        self.generate_routes()
        self.generate_movements_delays()

        print("[5/8] resources and machines...")
        self.generate_resources()
        self.generate_resource_availability()
        self.generate_task_resources()
        self.generate_machines()

        print("[6/8] weather and incidents...")
        self.generate_weather()
        self.generate_weather_forecast()
        self.generate_speed_restrictions()
        self.generate_incidents_emergency()

        print("[7/8] cost/material/safety/planning...")
        self.generate_costs_materials()
        self.generate_safety_signalling_planning_versions()
        self.generate_traffic_demand()
        self.generate_target_definition()

        if self.cfg.introduce_corruption:
            print("[8/8] optional data-quality corruption...")
            self.apply_optional_corruption()
        else:
            print("[8/8] provenance + validation + output...")
        self.generate_provenance()

        validation = self.write_outputs(output)
        elapsed=time.time()-start
        print(f"[DONE] Output: {output.resolve()}")
        print(f"[DONE] Tables: {len(self.tables)}")
        print(f"[DONE] Total rows: {sum(len(v) for v in self.tables.values()):,}")
        print(f"[DONE] Seconds: {elapsed:.1f}")
        failed=validation[validation.status.eq("FAIL")]
        if len(failed):
            print("[ERROR] Validation failures:")
            print(failed.to_string(index=False))
            return 2
        return 0


def parse_args():
    p=argparse.ArgumentParser(description="Generate the complete Rail-Yojna synthetic relational dataset.")
    p.add_argument("--output",default="./rail_yojna_data",help="Output directory.")
    p.add_argument("--scale",type=float,default=1.0,
                   help="Multiplier for entity/time-series sizes. 0.05 is a useful smoke test.")
    p.add_argument("--seed",type=int,default=42)
    p.add_argument("--no-sqlite",action="store_true")
    p.add_argument("--parquet",action="store_true")
    p.add_argument("--corrupt",action="store_true",
                   help="Introduce small, explicitly tracked data-quality defects.")
    p.add_argument("--corruption-rate",type=float,default=0.005)
    return p.parse_args()


def main():
    args=parse_args()
    if args.scale <= 0:
        raise SystemExit("--scale must be > 0")
    cfg=Config(
        seed=args.seed, scale=args.scale,
        write_sqlite=not args.no_sqlite, write_parquet=args.parquet,
        introduce_corruption=args.corrupt, corruption_rate=args.corruption_rate
    )
    return RailYojnaGenerator(cfg).run(Path(args.output))


if __name__=="__main__":
    raise SystemExit(main())
