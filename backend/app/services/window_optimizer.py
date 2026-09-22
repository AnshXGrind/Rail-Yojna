
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / "rail_yojna_data"


def _clean(v: Any) -> Any:
    if pd.isna(v):
        return None
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            pass
    return v


def _iso(v: Any) -> str | None:
    if v is None or pd.isna(v):
        return None
    ts = pd.to_datetime(v, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.isoformat()


def _minutes(a, b) -> float:
    return max(0.0, (b - a).total_seconds() / 60.0)


def _pick(df: pd.DataFrame, names: Iterable[str]) -> str | None:
    lower = {str(c).lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def _csv(name: str) -> Path:
    p = RAW / name
    if not p.exists():
        raise FileNotFoundError(p)
    return p


@lru_cache(maxsize=1)
def _movements() -> pd.DataFrame:
    p = _csv("train_movements.csv")
    df = pd.read_csv(p)

    for c in (
        "date",
        "scheduled_entry",
        "scheduled_exit",
        "actual_entry",
        "actual_exit",
    ):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], utc=True, errors="coerce")

    return df


@lru_cache(maxsize=1)
def _maintenance_tasks() -> pd.DataFrame:
    p = _csv("maintenance_tasks.csv")
    df = pd.read_csv(p)

    for c in (
        "planned_date",
        "earliest_start",
        "latest_finish",
    ):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], utc=True, errors="coerce")

    return df


@lru_cache(maxsize=1)
def _task_resources() -> pd.DataFrame:
    p = _csv("task_resources.csv")
    return pd.read_csv(p)


@lru_cache(maxsize=1)
def _availability() -> pd.DataFrame:
    p = _csv("resource_availability.csv")
    df = pd.read_csv(p)

    for c in df.columns:
        lc = str(c).lower()
        if any(k in lc for k in ("start", "end", "from", "to", "available")):
            parsed = pd.to_datetime(df[c], utc=True, errors="coerce")
            if parsed.notna().any():
                df[c] = parsed

    return df


@lru_cache(maxsize=1)
def _resources() -> pd.DataFrame:
    p = _csv("resources.csv")
    return pd.read_csv(p)


@lru_cache(maxsize=1)
def _machines() -> pd.DataFrame:
    p = RAW / "machines.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


@lru_cache(maxsize=1)
def _materials() -> pd.DataFrame:
    p = RAW / "materials.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


@lru_cache(maxsize=1)
def _safety_constraints() -> pd.DataFrame:
    p = _csv("safety_constraints.csv")
    return pd.read_csv(p)


def _asset_rule(asset_type: str | None) -> dict[str, Any]:
    sc = _safety_constraints()
    if sc.empty or not asset_type:
        return {
            "status": "DATA_GAP",
            "minimum_clearance_minutes": None,
            "minimum_block_duration_minutes": None,
            "required_personnel": None,
            "matched_rows": 0,
        }

    a = str(asset_type).lower()
    aliases = {
        "ohe_maintenance": "ohe",
        "ohe_inspection": "ohe",
        "rail_maintenance": "rail",
        "rail_inspection": "rail",
        "ballast_renewal": "rail",
        "point_machine": "point_machine",
        "signal_maintenance": "signal",
        "signal_inspection": "signal",
    }
    needle = aliases.get(a, a)

    if "asset_type" not in sc.columns:
        return {
            "status": "DATA_GAP",
            "minimum_clearance_minutes": None,
            "minimum_block_duration_minutes": None,
            "required_personnel": None,
            "matched_rows": 0,
        }

    mask = sc["asset_type"].astype(str).str.lower().eq(needle)
    rows = sc.loc[mask]

    if rows.empty:
        return {
            "status": "DATA_GAP",
            "minimum_clearance_minutes": None,
            "minimum_block_duration_minutes": None,
            "required_personnel": None,
            "matched_rows": 0,
        }

    def num(col):
        if col not in rows.columns:
            return None
        s = pd.to_numeric(rows[col], errors="coerce").dropna()
        return float(s.max()) if not s.empty else None

    return {
        "status": "PASS",
        "minimum_clearance_minutes": num("minimum_clearance_minutes"),
        "minimum_block_duration_minutes": num("minimum_block_duration_minutes"),
        "required_personnel": num("required_personnel"),
        "matched_rows": int(len(rows)),
    }


def _candidate_tasks(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    return list(candidate.get("tasks") or [])


def _task_window(task: dict[str, Any]):
    start = pd.to_datetime(task.get("earliest_start"), utc=True, errors="coerce")
    finish = pd.to_datetime(task.get("latest_finish"), utc=True, errors="coerce")

    if pd.isna(start) or pd.isna(finish):
        return None, None

    return start, finish


def _block_requirements(candidate: dict[str, Any]) -> dict[str, Any]:
    tasks = _candidate_tasks(candidate)

    duration = sum(
        float(t.get("duration_minutes") or 0)
        for t in tasks
    )

    clearance = 0.0
    minimum_block = 0.0
    personnel = 0.0
    safety_mapped = 0
    safety_missing = 0

    for t in tasks:
        rule = _asset_rule(t.get("task_type"))

        if rule["status"] == "PASS":
            safety_mapped += 1
            clearance = max(
                clearance,
                float(rule["minimum_clearance_minutes"] or 0),
            )
            minimum_block = max(
                minimum_block,
                float(rule["minimum_block_duration_minutes"] or 0),
            )
            personnel = max(
                personnel,
                float(rule["required_personnel"] or 0),
            )
        else:
            safety_missing += 1

    return {
        "duration_minutes": duration,
        "clearance_minutes": clearance,
        "minimum_block_duration_minutes": minimum_block,
        "required_personnel": personnel,
        "safety_mapped_tasks": safety_mapped,
        "safety_missing_tasks": safety_missing,
    }


def _occupied_intervals(movements, section_id, track_id, start, finish):
    if movements.empty:
        return [], True

    df = movements.copy()

    mask = pd.Series(True, index=df.index)
    if "section_id" in df.columns:
        mask &= df["section_id"].astype(str).eq(str(section_id))
    if "track_id" in df.columns:
        mask &= df["track_id"].astype(str).eq(str(track_id))

    df = df.loc[mask]

    if "actual_entry" not in df.columns or "actual_exit" not in df.columns:
        return [], True

    df = df.loc[
        df["actual_entry"].notna()
        & df["actual_exit"].notna()
    ]

    if df.empty:
        return [], False

    intervals = []

    for _, row in df.iterrows():
        a = pd.Timestamp(row["actual_entry"])
        b = pd.Timestamp(row["actual_exit"])

        if b <= start or a >= finish:
            continue

        intervals.append(
            (
                max(a, start),
                min(b, finish),
                str(row.get("movement_id", "")),
                str(row.get("train_id", "")),
            )
        )

    intervals.sort(key=lambda x: x[0])
    return intervals, False


def _free_windows(start, finish, occupied, duration, clearance):
    expanded = []

    for a, b, movement_id, train_id in occupied:
        ca = a - pd.Timedelta(minutes=clearance)
        cb = b + pd.Timedelta(minutes=clearance)
        expanded.append((ca, cb, movement_id, train_id))

    merged = []
    for item in expanded:
        if not merged or item[0] > merged[-1][1]:
            merged.append([item[0], item[1], [item[2]], [item[3]]])
        else:
            merged[-1][1] = max(merged[-1][1], item[1])
            merged[-1][2].append(item[2])
            merged[-1][3].append(item[3])

    out = []
    cursor = start

    for a, b, _, _ in merged:
        if a > cursor and _minutes(cursor, a) >= duration:
            out.append(
                {
                    "start": _iso(cursor),
                    "finish": _iso(cursor + pd.Timedelta(minutes=duration)),
                    "available_minutes": _minutes(cursor, a),
                    "required_minutes": duration,
                    "train_free": True,
                    "resource_feasible": None,
                    "status": "TRAIN_FREE",
                }
            )

        cursor = max(cursor, b)

    if cursor < finish and _minutes(cursor, finish) >= duration:
        out.append(
            {
                "start": _iso(cursor),
                "finish": _iso(cursor + pd.Timedelta(minutes=duration)),
                "available_minutes": _minutes(cursor, finish),
                "required_minutes": duration,
                "train_free": True,
                "resource_feasible": None,
                "status": "TRAIN_FREE",
            }
        )

    return out


def _resource_ids_for_tasks(task_ids):
    tr = _task_resources()
    if tr.empty or "task_id" not in tr.columns:
        return [], False

    rows = tr.loc[
        tr["task_id"].astype(str).isin(
            {str(x) for x in task_ids}
        )
    ]

    if rows.empty:
        return [], False

    id_col = _pick(
        rows,
        (
            "resource_id",
            "machine_id",
            "crew_id",
            "personnel_id",
            "resource",
        ),
    )

    if not id_col:
        # Still mapped task resources, but schema doesn't expose
        # a joinable resource identifier.
        return [], True

    ids = [
        x for x in rows[id_col].dropna().astype(str).unique().tolist()
        if x and x.lower() != "nan"
    ]

    return ids, True


def _availability_for_resource(resource_id, start, finish):
    av = _availability()
    if av.empty:
        return False, "NO_AVAILABILITY_DATA"

    id_col = _pick(
        av,
        (
            "resource_id",
            "machine_id",
            "crew_id",
            "personnel_id",
            "resource",
        ),
    )

    if not id_col:
        return False, "RESOURCE_ID_COLUMN_MISSING"

    rows = av.loc[
        av[id_col].astype(str).eq(str(resource_id))
    ]

    if rows.empty:
        return False, "RESOURCE_NOT_FOUND"

    start_col = _pick(
        rows,
        (
            "available_from",
            "availability_start",
            "start_time",
            "start",
            "from",
            "window_start",
        ),
    )

    finish_col = _pick(
        rows,
        (
            "available_to",
            "availability_end",
            "end_time",
            "end",
            "to",
            "window_finish",
        ),
    )

    if not start_col or not finish_col:
        return False, "AVAILABILITY_WINDOW_COLUMNS_MISSING"

    for _, row in rows.iterrows():
        a = pd.to_datetime(row[start_col], utc=True, errors="coerce")
        b = pd.to_datetime(row[finish_col], utc=True, errors="coerce")

        if pd.isna(a) or pd.isna(b):
            continue

        if a <= start and b >= finish:
            status_col = _pick(
                rows,
                ("status", "availability_status", "state"),
            )

            if status_col:
                status = str(row[status_col]).lower()
                if any(x in status for x in ("inactive", "unavailable", "offline")):
                    continue

            return True, "AVAILABLE"

    return False, "INTERVAL_NOT_COVERED"


def _resource_check(candidate, start, finish):
    task_ids = [
        t.get("task_id")
        for t in _candidate_tasks(candidate)
        if t.get("task_id")
    ]

    resource_ids, mapped = _resource_ids_for_tasks(task_ids)

    if not mapped:
        return {
            "status": "DATA_GAP",
            "resource_ids": [],
            "mapped_resource_data": False,
            "conflicts": [],
        }

    if not resource_ids:
        return {
            "status": "DATA_GAP",
            "resource_ids": [],
            "mapped_resource_data": True,
            "conflicts": ["resource identifier cannot be joined to availability"],
        }

    conflicts = []

    for resource_id in resource_ids:
        ok, reason = _availability_for_resource(
            resource_id,
            start,
            finish,
        )

        if not ok:
            conflicts.append(
                {
                    "resource_id": resource_id,
                    "reason": reason,
                }
            )

    return {
        "status": "PASS" if not conflicts else "CONFLICT",
        "resource_ids": resource_ids,
        "mapped_resource_data": True,
        "conflicts": conflicts,
    }


def optimize_windows(
    candidate: dict[str, Any],
    *,
    include_resource_check: bool = True,
    limit: int = 10,
) -> dict[str, Any]:

    section_id = candidate.get("section_id")
    track_id = candidate.get("track_id")

    task_windows = [
        _task_window(t)
        for t in _candidate_tasks(candidate)
    ]

    task_windows = [
        (a, b)
        for a, b in task_windows
        if a is not None and b is not None
    ]

    if not task_windows:
        return {
            "status": "MAINTENANCE_DATA_GAP",
            "alternative_windows": [],
            "resource_summary": {
                "status": "DATA_GAP"
            },
            "requirements": {},
        }

    start = min(x[0] for x in task_windows)
    finish = max(x[1] for x in task_windows)

    req = _block_requirements(candidate)
    duration = max(
        float(candidate.get("total_duration_minutes") or 0),
        req["duration_minutes"],
        req["minimum_block_duration_minutes"],
    )

    movements = _movements()
    occupied, train_data_gap = _occupied_intervals(
        movements,
        section_id,
        track_id,
        start,
        finish,
    )

    if train_data_gap:
        return {
            "status": "TRAIN_DATA_GAP",
            "alternative_windows": [],
            "resource_summary": {
                "status": "DATA_GAP"
            },
            "requirements": req,
            "train_coverage": {
                "status": "DATA_GAP",
                "section_id": section_id,
                "track_id": track_id,
                "window_start": _iso(start),
                "window_finish": _iso(finish),
            },
        }

    free = _free_windows(
        start,
        finish,
        occupied,
        duration,
        req["clearance_minutes"],
    )

    enriched = []

    for w in free[: max(limit * 3, limit)]:
        ws = pd.to_datetime(w["start"], utc=True)
        wf = pd.to_datetime(w["finish"], utc=True)

        resource_summary = (
            _resource_check(candidate, ws, wf)
            if include_resource_check
            else {"status": "NOT_EVALUATED"}
        )

        item = dict(w)
        item["resource_feasible"] = (
            resource_summary["status"] == "PASS"
        )
        item["resource_status"] = resource_summary["status"]
        item["resource_conflicts"] = resource_summary.get(
            "conflicts", []
        )

        if resource_summary["status"] == "PASS":
            item["status"] = "FEASIBLE"
        elif resource_summary["status"] == "CONFLICT":
            item["status"] = "RESOURCE_CONFLICT"
        else:
            item["status"] = "RESOURCE_DATA_GAP"

        enriched.append(item)

    feasible = [
        x for x in enriched
        if x["status"] == "FEASIBLE"
    ]

    if feasible:
        status = "FEASIBLE"
    elif enriched:
        if all(x["status"] == "RESOURCE_CONFLICT" for x in enriched):
            status = "RESOURCE_CONFLICT"
        elif all(x["status"] == "RESOURCE_DATA_GAP" for x in enriched):
            status = "RESOURCE_DATA_GAP"
        else:
            status = "REVIEW"
    else:
        status = "TRAIN_CONFLICT"

    return {
        "status": status,
        "alternative_windows": enriched[:limit],
        "resource_summary": {
            "status": (
                "PASS"
                if feasible
                else (
                    "CONFLICT"
                    if enriched
                    else "DATA_GAP"
                )
            ),
            "feasible_windows": len(feasible),
            "evaluated_windows": len(enriched),
        },
        "requirements": req,
        "train_coverage": {
            "status": "EVALUATED",
            "occupied_intervals": len(occupied),
            "section_id": section_id,
            "track_id": track_id,
        },
    }


def optimize_task_windows(
    task_id: str,
    *,
    include_resource_check: bool = False,
    limit: int = 10,
) -> dict[str, Any]:

    df = _maintenance_tasks()

    if "task_id" not in df.columns:
        return {
            "status": "MAINTENANCE_DATA_GAP",
            "alternative_windows": [],
        }

    rows = df.loc[
        df["task_id"].astype(str).eq(str(task_id))
    ]

    if rows.empty:
        return {
            "status": "NOT_FOUND",
            "alternative_windows": [],
        }

    row = rows.iloc[0]

    task = {
        k: _clean(row[k])
        for k in row.index
    }

    candidate = {
        "block_id": f"HIST-{task_id}",
        "planned_date": _iso(task.get("planned_date")),
        "section_id": task.get("section_id"),
        "track_id": task.get("track_id"),
        "task_ids": [task_id],
        "tasks": [task],
        "total_duration_minutes": float(
            task.get("estimated_duration_minutes") or 0
        ),
    }

    return optimize_windows(
        candidate,
        include_resource_check=include_resource_check,
        limit=limit,
    )
