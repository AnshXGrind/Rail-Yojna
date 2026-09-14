from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "data" / "backups" / f"phase4_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def backup(path: Path) -> None:
    if path.exists():
        dest = BACKUP / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup(path)
    path.write_text(content, encoding="utf-8")


def patch_text(path: Path, transform, description: str) -> None:
    if not path.exists():
        raise FileNotFoundError(path)

    original = path.read_text(encoding="utf-8")
    updated = transform(original)

    if updated == original:
        raise RuntimeError(f"Patch made no changes: {description}")

    backup(path)
    path.write_text(updated, encoding="utf-8")


def run(cmd: list[str], *, cwd: Path = ROOT, check=True) -> subprocess.CompletedProcess:
    print("\n$", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, check=check, text=True)


print("=" * 80)
print("RAIL-YOJNA PHASE 4 — PRODUCT INTEGRATION")
print("=" * 80)

BACKUP.mkdir(parents=True, exist_ok=True)
print(f"[BACKUP] {BACKUP}")


# ---------------------------------------------------------------------------
# 1. PLANNING SERVICE — V2 + explanations
# ---------------------------------------------------------------------------

write(
    ROOT / "backend/app/services/planning_service.py",
    r'''from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]

PLAN_PATH = ROOT / "optimization/results/maintenance_plan_v2.parquet"


def _read_plan() -> pd.DataFrame:
    parquet = PLAN_PATH

    if parquet.exists():
        return pd.read_parquet(parquet)

    csv_path = parquet.with_suffix(".csv")
    if csv_path.exists():
        return pd.read_csv(csv_path)

    raise FileNotFoundError(
        f"Maintenance plan not found: {parquet} or {csv_path}"
    )


@lru_cache(maxsize=1)
def load_plan() -> pd.DataFrame:
    df = _read_plan().copy()

    required = {
        "task_id",
        "asset_id",
        "calibrated_risk",
        "condition_score",
        "degradation_rate",
        "task_type",
        "priority",
        "criticality",
        "estimated_duration_minutes",
        "planned_date",
        "block_required",
        "value",
        "selected",
    }

    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(
            f"Maintenance plan missing required columns: {missing}"
        )

    return df


def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def explain_task(row: pd.Series) -> dict[str, Any]:
    risk = float(row["calibrated_risk"])
    condition = float(row["condition_score"])
    degradation = float(row["degradation_rate"])
    criticality = float(row["criticality"])
    priority = str(row["priority"])
    block_required = bool(row["block_required"])

    reasons: list[str] = []

    if risk >= 0.50:
        reasons.append("critical predicted failure risk")
    elif risk >= 0.20:
        reasons.append("high predicted failure risk")
    elif risk >= 0.05:
        reasons.append("moderate predicted failure risk")
    else:
        reasons.append("low predicted failure risk")

    if condition < 40:
        reasons.append("poor current condition")
    elif condition < 60:
        reasons.append("degraded current condition")

    if degradation > 0:
        reasons.append("positive degradation trend")

    if criticality >= 0.80:
        reasons.append("high asset criticality")

    if priority == "P1":
        reasons.append("highest maintenance priority")

    if block_required:
        reasons.append("requires a planned block")

    return {
        "primary_reason": reasons[0],
        "reasons": reasons,
        "risk_probability": risk,
        "condition_score": condition,
        "degradation_rate": degradation,
        "criticality": criticality,
        "priority": priority,
        "block_required": block_required,
        "explanation_mode": "deterministic_rule_summary",
    }


def _row_to_dict(row: pd.Series) -> dict[str, Any]:
    item = {
        "task_id": row["task_id"],
        "asset_id": row["asset_id"],
        "section_id": row.get("section_id"),
        "track_id": row.get("track_id"),
        "calibrated_risk": row["calibrated_risk"],
        "condition_score": row["condition_score"],
        "degradation_rate": row["degradation_rate"],
        "task_type": row["task_type"],
        "priority": row["priority"],
        "criticality": row["criticality"],
        "estimated_duration_minutes": row["estimated_duration_minutes"],
        "planned_date": row["planned_date"],
        "block_required": row["block_required"],
        "value": row["value"],
        "selected": row["selected"],
        "explanation": explain_task(row),
        "data_mode": "synthetic",
    }

    return {k: _clean_value(v) for k, v in item.items()}


def get_plan(limit: int = 50) -> list[dict]:
    df = load_plan()
    limit = max(1, min(int(limit), 500))

    selected = (
        df[df["selected"] == 1]
        .sort_values("value", ascending=False)
        .head(limit)
    )

    return [_row_to_dict(row) for _, row in selected.iterrows()]


def get_plan_task(task_id: str) -> dict:
    df = load_plan()

    matches = df[df["task_id"].astype(str) == str(task_id)]
    if matches.empty:
        raise KeyError(task_id)

    return _row_to_dict(matches.iloc[0])


def get_plan_summary() -> dict:
    df = load_plan()

    selected = df[df["selected"] == 1]

    minutes = int(selected["estimated_duration_minutes"].sum())

    return {
        "candidate_tasks": int(len(df)),
        "selected_tasks": int(len(selected)),
        "deferred_tasks": int(len(df) - len(selected)),
        "selected_minutes": minutes,
        "selected_hours": float(minutes / 60),
        "risk_mass": float(selected["calibrated_risk"].sum()),
        "data_mode": "synthetic",
        "planner_version": "maintenance_plan_v2",
    }


def get_plan_metrics() -> dict:
    df = load_plan()

    selected = df[df["selected"] == 1]

    risk = selected["calibrated_risk"].astype(float)

    return {
        "selected_tasks": int(len(selected)),
        "selected_hours": float(
            selected["estimated_duration_minutes"].sum() / 60
        ),
        "risk_mass": float(risk.sum()),
        "mean_selected_risk": float(risk.mean()) if len(risk) else 0.0,
        "high_risk_tasks": int((risk >= 0.20).sum()),
        "critical_risk_tasks": int((risk >= 0.50).sum()),
        "block_required_tasks": int(selected["block_required"].astype(bool).sum()),
        "p1_tasks": int((selected["priority"].astype(str) == "P1").sum()),
        "planner_version": "maintenance_plan_v2",
    }


def clear_plan_cache() -> None:
    load_plan.cache_clear()
''',
)


# ---------------------------------------------------------------------------
# 2. PLANNING SCHEMAS
# ---------------------------------------------------------------------------

write(
    ROOT / "backend/app/schemas/planning.py",
    r'''from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlanningSummary(BaseModel):
    candidate_tasks: int
    selected_tasks: int
    deferred_tasks: int
    selected_minutes: int
    selected_hours: float
    risk_mass: float
    data_mode: str
    planner_version: str = "maintenance_plan_v2"


class PlanningDecisionRequest(BaseModel):
    decision: str = Field(
        pattern="^(approve|modify|reject)$"
    )
    actor: str = Field(default="planner", min_length=1, max_length=100)
    note: str = Field(default="", max_length=2000)


class PlanningDecisionResponse(BaseModel):
    decision_id: str
    task_id: str
    decision: str
    actor: str
    note: str
    human_approval_required: bool = True
    decision_mode: str = "decision_support"


class PlanningTaskResponse(BaseModel):
    task_id: str
    asset_id: str
    section_id: Any | None = None
    track_id: Any | None = None
    calibrated_risk: float
    condition_score: float
    degradation_rate: float
    task_type: str
    priority: str
    criticality: float
    estimated_duration_minutes: int
    planned_date: Any | None = None
    block_required: bool
    value: float
    selected: int
    explanation: dict[str, Any]
    data_mode: str


class AuditEventResponse(BaseModel):
    event_id: str
    event_type: str
    timestamp: str
    actor: str
    asset_id: str | None = None
    recommendation_id: str | None = None
    model_version: str | None = None
    payload: dict[str, Any]
''',
)


# ---------------------------------------------------------------------------
# 3. AUDIT SERVICE — persistent, queryable audit history
# ---------------------------------------------------------------------------

write(
    ROOT / "backend/app/audit/audit_service.py",
    r'''from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
AUDIT_DIR = ROOT / "data" / "audit"
AUDIT_FILE = AUDIT_DIR / "decision_events.jsonl"


def record_event(
    event_type: str,
    *,
    actor: str = "system",
    asset_id: str | None = None,
    recommendation_id: str | None = None,
    model_version: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "asset_id": asset_id,
        "recommendation_id": recommendation_id,
        "model_version": model_version,
        "payload": payload or {},
    }

    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")

    return event


def list_events(
    *,
    limit: int = 100,
    event_type: str | None = None,
    asset_id: str | None = None,
) -> list[dict[str, Any]]:

    if not AUDIT_FILE.exists():
        return []

    limit = max(1, min(int(limit), 500))
    events: list[dict[str, Any]] = []

    with AUDIT_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event_type and event.get("event_type") != event_type:
                continue

            if asset_id and event.get("asset_id") != asset_id:
                continue

            events.append(event)

    events.sort(
        key=lambda x: x.get("timestamp", ""),
        reverse=True,
    )

    return events[:limit]
''',
)


# ---------------------------------------------------------------------------
# 4. ROUTES — planner decisions + audit history
# ---------------------------------------------------------------------------

routes_path = ROOT / "backend/app/api/routes.py"

patch_text(
    routes_path,
    lambda text: text.replace(
        "from fastapi import APIRouter, HTTPException, Query",
        "from fastapi import APIRouter, HTTPException, Query\n"
        "from backend.app.audit.audit_service import list_events, record_event\n"
        "from backend.app.schemas.planning import PlanningDecisionRequest",
    )
    .replace(
        "from backend.app.services.planning_service import (\n"
        "    get_plan,\n"
        "    get_plan_summary,\n"
        ")",
        "from backend.app.services.planning_service import (\n"
        "    get_plan,\n"
        "    get_plan_summary,\n"
        "    get_plan_metrics,\n"
        "    get_plan_task,\n"
        ")",
    ),
    "planning imports",
)

# Add routes immediately after /planning/plan.
def add_phase4_routes(text: str) -> str:
    anchor = '''@router.get("/planning/plan")
def planning_plan(
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),
):
    return {
        "items": get_plan(limit),
        "data_mode": "synthetic",
    }
'''

    if anchor not in text:
        raise RuntimeError("Could not locate planning_plan route")

    addition = anchor + r'''

@router.get("/planning/metrics")
def planning_metrics():
    return get_plan_metrics()


@router.get("/planning/tasks/{task_id}")
def planning_task(task_id: str):
    try:
        return get_plan_task(task_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Planning task not found: {task_id}",
        )


@router.post("/planning/tasks/{task_id}/decision")
def planning_decision(
    task_id: str,
    request: PlanningDecisionRequest,
):
    try:
        task = get_plan_task(task_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Planning task not found: {task_id}",
        )

    event_type = {
        "approve": "PLANNING_APPROVED",
        "modify": "PLANNING_MODIFIED",
        "reject": "PLANNING_REJECTED",
    }[request.decision]

    event = record_event(
        event_type,
        actor=request.actor,
        asset_id=str(task["asset_id"]),
        recommendation_id=str(task_id),
        model_version="maintenance_plan_v2",
        payload={
            "task": task_id,
            "decision": request.decision,
            "note": request.note,
            "human_reviewed": True,
            "decision_mode": "decision_support",
        },
    )

    return {
        "decision_id": event["event_id"],
        "task_id": task_id,
        "decision": request.decision,
        "actor": request.actor,
        "note": request.note,
        "human_approval_required": True,
        "decision_mode": "decision_support",
    }


@router.get("/audit/events")
def audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    event_type: str | None = Query(default=None),
    asset_id: str | None = Query(default=None),
):
    return {
        "items": list_events(
            limit=limit,
            event_type=event_type,
            asset_id=asset_id,
        ),
        "data_mode": "synthetic",
    }
'''

    return text.replace(anchor, addition)


patch_text(
    routes_path,
    add_phase4_routes,
    "Phase 4 planning decision and audit routes",
)


# ---------------------------------------------------------------------------
# 5. FRONTEND COMPONENT
# ---------------------------------------------------------------------------

planning_component = r'''import { useEffect, useState } from "react";

const API = "http://127.0.0.1:8000/api/v1";

function pct(value) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}

function riskClass(value) {
  const v = Number(value || 0);
  if (v >= 0.50) return "critical";
  if (v >= 0.20) return "high";
  if (v >= 0.05) return "medium";
  return "low";
}

export default function PlanningDashboard() {
  const [summary, setSummary] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [selected, setSelected] = useState(null);
  const [audit, setAudit] = useState([]);
  const [message, setMessage] = useState("");

  async function load() {
    const [s, m, p, a] = await Promise.all([
      fetch(`${API}/planning/summary`).then(r => r.json()),
      fetch(`${API}/planning/metrics`).then(r => r.json()),
      fetch(`${API}/planning/plan?limit=50`).then(r => r.json()),
      fetch(`${API}/audit/events?limit=20`).then(r => r.json()),
    ]);

    setSummary(s);
    setMetrics(m);
    setTasks(p.items || []);
    setAudit(a.items || []);
  }

  useEffect(() => {
    load().catch(err => setMessage(err.message));
  }, []);

  async function decide(taskId, decision) {
    const actor = window.prompt("Planner / reviewer name:", "planner");
    if (!actor) return;

    const note = window.prompt("Decision note:", "") ?? "";

    const response = await fetch(
      `${API}/planning/tasks/${encodeURIComponent(taskId)}/decision`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          decision,
          actor,
          note,
        }),
      }
    );

    const data = await response.json();

    if (!response.ok) {
      setMessage(data.detail || "Decision failed");
      return;
    }

    setMessage(
      `${decision.toUpperCase()} recorded for ${taskId}`
    );

    await load();
  }

  return (
    <section className="planning-dashboard">
      <div className="planning-header">
        <div>
          <h2>Maintenance Planning</h2>
          <p>Human-reviewed decision support · maintenance_plan_v2</p>
        </div>

        <button onClick={() => load()}>
          Refresh
        </button>
      </div>

      {summary && (
        <div className="planning-metrics">
          <div>
            <span>Selected Tasks</span>
            <strong>{summary.selected_tasks}</strong>
          </div>
          <div>
            <span>Deferred</span>
            <strong>{summary.deferred_tasks}</strong>
          </div>
          <div>
            <span>Hours</span>
            <strong>{summary.selected_hours.toFixed(1)}</strong>
          </div>
          <div>
            <span>Risk Mass</span>
            <strong>{summary.risk_mass.toFixed(2)}</strong>
          </div>
          <div>
            <span>High Risk</span>
            <strong>{metrics?.high_risk_tasks ?? 0}</strong>
          </div>
          <div>
            <span>Blocks</span>
            <strong>{metrics?.block_required_tasks ?? 0}</strong>
          </div>
        </div>
      )}

      {message && (
        <div className="planning-message">
          {message}
        </div>
      )}

      <div className="planning-layout">
        <div className="planning-table-wrap">
          <table className="planning-table">
            <thead>
              <tr>
                <th>Task</th>
                <th>Asset</th>
                <th>Risk</th>
                <th>Condition</th>
                <th>Priority</th>
                <th>Duration</th>
                <th>Block</th>
              </tr>
            </thead>

            <tbody>
              {tasks.map(task => (
                <tr
                  key={task.task_id}
                  className={
                    selected?.task_id === task.task_id
                      ? "selected-row"
                      : ""
                  }
                  onClick={() => setSelected(task)}
                >
                  <td>{task.task_id}</td>
                  <td>{task.asset_id}</td>
                  <td>
                    <span className={`risk-chip ${riskClass(task.calibrated_risk)}`}>
                      {pct(task.calibrated_risk)}
                    </span>
                  </td>
                  <td>{Number(task.condition_score).toFixed(1)}</td>
                  <td>{task.priority}</td>
                  <td>{task.estimated_duration_minutes} min</td>
                  <td>{task.block_required ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <aside className="planning-detail">
          {!selected ? (
            <div className="empty-detail">
              Select a maintenance recommendation.
            </div>
          ) : (
            <>
              <h3>{selected.task_id}</h3>

              <div className="detail-grid">
                <span>Asset</span>
                <strong>{selected.asset_id}</strong>

                <span>Risk</span>
                <strong>{pct(selected.calibrated_risk)}</strong>

                <span>Condition</span>
                <strong>{Number(selected.condition_score).toFixed(1)}</strong>

                <span>Degradation</span>
                <strong>{Number(selected.degradation_rate).toFixed(4)}</strong>

                <span>Criticality</span>
                <strong>{Number(selected.criticality).toFixed(2)}</strong>

                <span>Priority</span>
                <strong>{selected.priority}</strong>

                <span>Task</span>
                <strong>{selected.task_type}</strong>

                <span>Block</span>
                <strong>{selected.block_required ? "Required" : "Not required"}</strong>
              </div>

              <div className="planning-explanation">
                <h4>Why this task is recommended</h4>
                <p>{selected.explanation.primary_reason}</p>

                <ul>
                  {selected.explanation.reasons.map(reason => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>

              <div className="decision-buttons">
                <button
                  className="approve"
                  onClick={() => decide(selected.task_id, "approve")}
                >
                  Approve
                </button>

                <button
                  onClick={() => decide(selected.task_id, "modify")}
                >
                  Modify
                </button>

                <button
                  className="reject"
                  onClick={() => decide(selected.task_id, "reject")}
                >
                  Reject
                </button>
              </div>

              <small>
                Human review is mandatory. This interface does not issue
                railway movement or signalling authority.
              </small>
            </>
          )}
        </aside>
      </div>

      <div className="audit-panel">
        <h3>Recent Decision Audit</h3>
        {audit.length === 0 ? (
          <p>No planner decisions recorded yet.</p>
        ) : (
          <div className="audit-list">
            {audit.map(event => (
              <div key={event.event_id}>
                <strong>{event.event_type}</strong>
                <span>
                  {event.recommendation_id} · {event.actor}
                </span>
                <small>{event.timestamp}</small>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
'''

write(
    ROOT / "frontend/src/components/PlanningDashboard.jsx",
    planning_component,
)


# ---------------------------------------------------------------------------
# 6. FRONTEND CSS
# ---------------------------------------------------------------------------

planning_css = r'''
.planning-dashboard {
  margin-top: 24px;
  padding: 24px;
  border: 1px solid rgba(127, 127, 127, 0.25);
  border-radius: 16px;
}

.planning-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.planning-header h2 {
  margin: 0;
}

.planning-header p {
  margin: 6px 0 0;
  opacity: 0.7;
}

.planning-metrics {
  display: grid;
  grid-template-columns: repeat(6, minmax(110px, 1fr));
  gap: 12px;
  margin: 20px 0;
}

.planning-metrics > div {
  padding: 14px;
  border-radius: 10px;
  background: rgba(127, 127, 127, 0.08);
}

.planning-metrics span {
  display: block;
  font-size: 12px;
  opacity: 0.65;
}

.planning-metrics strong {
  display: block;
  margin-top: 5px;
  font-size: 20px;
}

.planning-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(300px, 0.8fr);
  gap: 18px;
}

.planning-table-wrap {
  overflow-x: auto;
}

.planning-table {
  width: 100%;
  border-collapse: collapse;
}

.planning-table th,
.planning-table td {
  padding: 11px 9px;
  border-bottom: 1px solid rgba(127,127,127,0.18);
  text-align: left;
  white-space: nowrap;
}

.planning-table tbody tr {
  cursor: pointer;
}

.planning-table tbody tr:hover,
.planning-table tbody tr.selected-row {
  background: rgba(127,127,127,0.09);
}

.risk-chip {
  display: inline-block;
  padding: 3px 7px;
  border-radius: 999px;
  font-size: 12px;
}

.risk-chip.low {
  background: rgba(40, 180, 100, 0.15);
}

.risk-chip.medium {
  background: rgba(220, 190, 50, 0.18);
}

.risk-chip.high {
  background: rgba(230, 120, 40, 0.18);
}

.risk-chip.critical {
  background: rgba(220, 60, 60, 0.18);
}

.planning-detail {
  padding: 18px;
  border-radius: 12px;
  background: rgba(127,127,127,0.07);
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px;
}

.detail-grid span {
  opacity: 0.65;
}

.planning-explanation {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid rgba(127,127,127,0.2);
}

.planning-explanation ul {
  padding-left: 18px;
}

.decision-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 18px 0 10px;
}

.decision-buttons button {
  flex: 1;
  min-width: 90px;
}

.decision-buttons .approve {
  border: 1px solid rgba(30, 160, 90, 0.5);
}

.decision-buttons .reject {
  border: 1px solid rgba(210, 70, 70, 0.5);
}

.planning-message {
  margin: 12px 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(100, 150, 220, 0.12);
}

.audit-panel {
  margin-top: 22px;
}

.audit-list {
  display: grid;
  gap: 8px;
}

.audit-list > div {
  display: grid;
  grid-template-columns: 1fr 2fr 1.4fr;
  gap: 10px;
  padding: 10px;
  border-radius: 8px;
  background: rgba(127,127,127,0.07);
}

.audit-list small {
  opacity: 0.65;
}

.empty-detail {
  opacity: 0.65;
}

@media (max-width: 1000px) {
  .planning-metrics {
    grid-template-columns: repeat(3, 1fr);
  }

  .planning-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 650px) {
  .planning-metrics {
    grid-template-columns: repeat(2, 1fr);
  }

  .audit-list > div {
    grid-template-columns: 1fr;
  }
}
'''

css_path = ROOT / "frontend/src/App.css"
with css_path.open("a", encoding="utf-8") as f:
    backup(css_path)
    f.write("\n\n/* PHASE 4 PLANNING UI */\n")
    f.write(planning_css)


# ---------------------------------------------------------------------------
# 7. PATCH APP.JSX — import + component mount
# ---------------------------------------------------------------------------

app_path = ROOT / "frontend/src/App.jsx"

def patch_app(text: str) -> str:
    if "PlanningDashboard" not in text:
        # Put import after the existing import block.
        lines = text.splitlines()
        last_import = max(
            (i for i, line in enumerate(lines) if line.startswith("import ")),
            default=-1,
        )

        lines.insert(
            last_import + 1,
            'import PlanningDashboard from "./components/PlanningDashboard";',
        )
        text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")

    if "<PlanningDashboard />" not in text:
        # Prefer a main closing tag.
        if "</main>" in text:
            text = text.replace(
                "</main>",
                "  <PlanningDashboard />\n      </main>",
                1,
            )
        else:
            # Otherwise put it immediately before the final root/container close.
            candidates = ["</div>\n  )", "</div>\n)", "</section>\n  )"]
            done = False
            for anchor in candidates:
                if anchor in text:
                    text = text.replace(
                        anchor,
                        "  <PlanningDashboard />\n" + anchor,
                        1,
                    )
                    done = True
                    break

            if not done:
                raise RuntimeError(
                    "Could not find a safe mount point in App.jsx"
                )

    return text


patch_text(
    app_path,
    patch_app,
    "mount Phase 4 PlanningDashboard",
)


# ---------------------------------------------------------------------------
# 8. VERIFY V2 PLAN EXISTS
# ---------------------------------------------------------------------------

plan_v2 = ROOT / "optimization/results/maintenance_plan_v2.parquet"

if not plan_v2.exists():
    raise FileNotFoundError(
        f"Phase 4 requires Phase 3 output: {plan_v2}"
    )

print(f"[OK] V2 planning artifact: {plan_v2}")


# ---------------------------------------------------------------------------
# 9. STATIC PYTHON VALIDATION
# ---------------------------------------------------------------------------

python_files = [
    ROOT / "backend/app/services/planning_service.py",
    ROOT / "backend/app/schemas/planning.py",
    ROOT / "backend/app/audit/audit_service.py",
    ROOT / "backend/app/api/routes.py",
]

for file in python_files:
    run(["python3", "-m", "py_compile", str(file)])

print("[OK] Backend Python syntax")


# ---------------------------------------------------------------------------
# 10. BACKEND TESTS
# ---------------------------------------------------------------------------

test_result = run(
    ["python3", "-m", "pytest", "-q", "tests"],
    check=False,
)

if test_result.returncode != 0:
    print("\n[ERROR] Backend test suite failed.")
    print(f"[RESTORE] Backup available at: {BACKUP}")
    raise SystemExit(test_result.returncode)

print("[OK] Backend tests")


# ---------------------------------------------------------------------------
# 11. FRONTEND BUILD
# ---------------------------------------------------------------------------

if not (ROOT / "frontend/package.json").exists():
    raise FileNotFoundError("frontend/package.json not found")

build = run(
    ["npm", "--prefix", "frontend", "run", "build"],
    check=False,
)

if build.returncode != 0:
    print("\n[ERROR] Frontend build failed.")
    print(f"[RESTORE] Backup available at: {BACKUP}")
    raise SystemExit(build.returncode)

print("[OK] Frontend production build")


# ---------------------------------------------------------------------------
# 12. IMPORT / API CONTRACT SMOKE TEST
# ---------------------------------------------------------------------------

smoke = r'''
from backend.app.services.planning_service import (
    get_plan,
    get_plan_summary,
    get_plan_metrics,
)

s = get_plan_summary()
m = get_plan_metrics()
p = get_plan(3)

assert s["planner_version"] == "maintenance_plan_v2"
assert m["planner_version"] == "maintenance_plan_v2"
assert isinstance(p, list)

if p:
    assert "explanation" in p[0]
    assert "task_id" in p[0]
    assert "calibrated_risk" in p[0]

print("planning smoke: PASS")
print("summary:", s)
print("metrics:", m)
print("sample_tasks:", len(p))
'''

run(
    [
        "python3",
        "-c",
        smoke,
    ]
)

# ---------------------------------------------------------------------------
# 13. FINAL REPORT
# ---------------------------------------------------------------------------

report = {
    "phase": "4",
    "status": "PASS",
    "planner_artifact": str(plan_v2.relative_to(ROOT)),
    "planner_version": "maintenance_plan_v2",
    "backend_tests": "PASS",
    "frontend_build": "PASS",
    "planning_smoke": "PASS",
    "human_review_required": True,
    "decision_mode": "decision_support",
    "autonomous_railway_control": False,
    "backup": str(BACKUP.relative_to(ROOT)),
}

report_path = ROOT / "data/validation/phase4_report.json"
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8",
)

print("\n" + "=" * 80)
print("PHASE 4 COMPLETE")
print("=" * 80)
print(json.dumps(report, indent=2))
print("\nNext runtime:")
print("  PYTHONPATH=\"$PWD\" python3 -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000")
print("  npm --prefix frontend run dev")
print("=" * 80)
