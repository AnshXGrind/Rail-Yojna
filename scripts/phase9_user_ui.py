from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
FRONTEND = ROOT / "frontend/src"
APP = FRONTEND / "App.jsx"
LIVE = FRONTEND / "components/LivePrediction.jsx"
CSS = FRONTEND / "App.css"

BACKUP = (
    ROOT
    / "data/backups"
    / f"phase9_user_ui_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)

BACKUP.mkdir(parents=True, exist_ok=True)


def backup(path: Path):
    if path.exists():
        dst = BACKUP / path.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)


def write(path: Path, content: str):
    backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run(cmd, check=True):
    print("\n$", " ".join(cmd))
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        check=check,
    )


# ============================================================
# BACKEND — allow browsing all selected planner tasks
# ============================================================

planning_service = ROOT / "backend/app/services/planning_service.py"
routes = ROOT / "backend/app/api/routes.py"

for path in [planning_service, routes]:
    backup(path)


service_text = planning_service.read_text(encoding="utf-8")
service_text = service_text.replace(
    'limit = max(1, min(int(limit), 500))',
    'limit = max(1, min(int(limit), 1500))',
)

planning_service.write_text(
    service_text,
    encoding="utf-8",
)

routes_text = routes.read_text(encoding="utf-8")

routes_text = routes_text.replace(
'''    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),''',
'''    limit: int = Query(
        default=50,
        ge=1,
        le=1500,
    ),''',
1,
)

routes.write_text(routes_text, encoding="utf-8")

print("[PASS] Planner API limit increased to 1500")


# ============================================================
# FRONTEND APP
# ============================================================

APP_JSX = r'''import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import LivePrediction from "./components/LivePrediction";
import "./App.css";

const API = "http://127.0.0.1:8000/api/v1";

const TASK_PAGE_OPTIONS = [25, 50, 100, 250, 500, 1000, 1500];
const ASSET_PAGE_OPTIONS = [25, 50, 100];

function riskBand(value) {
  const risk = Number(value || 0);

  if (risk >= 0.5) return { label: "Critical", cls: "critical" };
  if (risk >= 0.2) return { label: "High", cls: "high" };
  if (risk >= 0.05) return { label: "Medium", cls: "medium" };

  return { label: "Low", cls: "low" };
}

function riskPercent(value) {
  const risk = Number(value || 0);
  const percent = risk * 100;

  if (percent === 0) return "0%";
  if (percent < 0.01) return `${percent.toFixed(6)}%`;
  if (percent < 1) return `${percent.toFixed(4)}%`;
  if (percent < 10) return `${percent.toFixed(3)}%`;

  return `${percent.toFixed(2)}%`;
}

function RiskChip({ value }) {
  const band = riskBand(value);

  return (
    <span className={`risk-chip ${band.cls}`}>
      {riskPercent(value)} · {band.label}
    </span>
  );
}

function IndiaMapIcon() {
  return (
    <svg
      className="india-map"
      viewBox="0 0 90 110"
      aria-hidden="true"
    >
      <path
        d="M37 3
           L47 9
           L54 18
           L65 21
           L62 29
           L74 35
           L69 44
           L78 50
           L70 58
           L64 69
           L58 72
           L55 83
           L47 78
           L42 91
           L34 82
           L27 78
           L23 68
           L14 65
           L17 55
           L10 48
           L19 40
           L13 33
           L23 27
           L21 18
           L30 16
           Z"
      />
    </svg>
  );
}

function Metric({ label, value, meta, tone }) {
  return (
    <div className={`metric metric-${tone || "blue"}`}>
      <div className="metric-accent" />
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      <div className="metric-meta">{meta}</div>
    </div>
  );
}

function Empty({ children }) {
  return <div className="empty">{children}</div>;
}

function ListModal({
  title,
  subtitle,
  items,
  total,
  kind,
  onClose,
  onSelect,
}) {
  const isTasks = kind === "tasks";
  const options = isTasks
    ? TASK_PAGE_OPTIONS
    : ASSET_PAGE_OPTIONS;

  const [visible, setVisible] = useState(
    isTasks ? 100 : 50
  );

  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();

    if (!term) return items;

    return items.filter((item) => {
      if (isTasks) {
        return [
          item.task_id,
          item.asset_id,
          item.task_type,
          item.section_id,
          item.track_id,
          item.priority,
        ]
          .filter(Boolean)
          .some((value) =>
            String(value).toLowerCase().includes(term)
          );
      }

      return String(item.asset_id || "")
        .toLowerCase()
        .includes(term);
    });
  }, [items, search, isTasks]);

  const shown = filtered.slice(0, visible);

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="browse-modal">
        <div className="browse-header">
          <div>
            <div className="section-kicker">
              {isTasks ? "MAINTENANCE QUEUE" : "RISK WATCHLIST"}
            </div>

            <h2>{title}</h2>
            <p>{subtitle}</p>
          </div>

          <button
            className="modal-close"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <div className="browse-toolbar">
          <input
            value={search}
            onChange={(event) =>
              setSearch(event.target.value)
            }
            placeholder={
              isTasks
                ? "Search task, asset, priority…"
                : "Search asset…"
            }
          />

          <label className="count-select">
            <span>Show</span>

            <select
              value={visible}
              onChange={(event) =>
                setVisible(Number(event.target.value))
              }
            >
              {options.map((option) => (
                <option
                  key={option}
                  value={option}
                >
                  {option}
                </option>
              ))}
            </select>
          </label>

          <span className="result-count">
            {filtered.length.toLocaleString()} available
            {total != null && ` / ${total.toLocaleString()}`}
          </span>
        </div>

        <div className="browse-table-wrap">
          {shown.length === 0 ? (
            <Empty>No matching records.</Empty>
          ) : (
            <table>
              <thead>
                {isTasks ? (
                  <tr>
                    <th>Task</th>
                    <th>Asset</th>
                    <th>Risk</th>
                    <th>Priority</th>
                    <th>Duration</th>
                    <th>Block</th>
                  </tr>
                ) : (
                  <tr>
                    <th>Asset</th>
                    <th>Risk</th>
                    <th>Condition</th>
                    <th>Criticality</th>
                  </tr>
                )}
              </thead>

              <tbody>
                {shown.map((item) => (
                  <tr
                    key={
                      isTasks
                        ? item.task_id
                        : item.asset_id
                    }
                    onClick={() => {
                      onSelect(item);
                      onClose();
                    }}
                  >
                    {isTasks ? (
                      <>
                        <td>
                          <strong>{item.task_id}</strong>
                        </td>
                        <td>{item.asset_id}</td>
                        <td>
                          <RiskChip
                            value={item.calibrated_risk}
                          />
                        </td>
                        <td>{item.priority}</td>
                        <td>
                          {item.estimated_duration_minutes} min
                        </td>
                        <td>
                          {item.block_required
                            ? "Required"
                            : "No"}
                        </td>
                      </>
                    ) : (
                      <>
                        <td>
                          <strong>{item.asset_id}</strong>
                        </td>
                        <td>
                          <RiskChip value={item.risk} />
                        </td>
                        <td>
                          {item.condition_score != null
                            ? Number(
                                item.condition_score
                              ).toFixed(1)
                            : "—"}
                        </td>
                        <td>
                          {item.criticality != null
                            ? Number(
                                item.criticality
                              ).toFixed(2)
                            : "—"}
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="browse-footer">
          Showing {shown.length.toLocaleString()} of{" "}
          {filtered.length.toLocaleString()} filtered records
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [summary, setSummary] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [assets, setAssets] = useState([]);
  const [plan, setPlan] = useState([]);
  const [audit, setAudit] = useState([]);
  const [system, setSystem] = useState(null);

  const [selectedAsset, setSelectedAsset] = useState(null);
  const [selectedTask, setSelectedTask] = useState(null);

  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState("ALL");

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const [browse, setBrowse] = useState(null);
  const [predictionOpen, setPredictionOpen] = useState(false);

  const [decisionBusy, setDecisionBusy] = useState(false);
  const [decisionMessage, setDecisionMessage] = useState("");
  const [decisionActor, setDecisionActor] = useState("planner");
  const [decisionNote, setDecisionNote] = useState("");

  async function loadDashboard(initial = false) {
    try {
      if (initial) setLoading(true);
      else setRefreshing(true);

      setError("");

      const [
        healthResponse,
        systemResponse,
        summaryResponse,
        metricsResponse,
        assetResponse,
        planResponse,
        auditResponse,
      ] = await Promise.all([
        axios.get(`${API}/health`),
        axios.get(`${API}/system/status`),
        axios.get(`${API}/planning/summary`),
        axios.get(`${API}/planning/metrics`),
        axios.get(`${API}/assets/risk/top?limit=100`),
        axios.get(`${API}/planning/plan?limit=1500`),
        axios.get(`${API}/audit/events?limit=12`),
      ]);

      if (healthResponse.data.status !== "ok") {
        throw new Error("Backend health check failed");
      }

      const nextAssets = assetResponse.data.items || [];
      const nextPlan = planResponse.data.items || [];

      setSystem(systemResponse.data);
      setSummary(summaryResponse.data);
      setMetrics(metricsResponse.data);
      setAssets(nextAssets);
      setPlan(nextPlan);
      setAudit(auditResponse.data.items || []);

      setSelectedTask((current) => {
        if (current) {
          return (
            nextPlan.find(
              (task) =>
                task.task_id === current.task_id
            ) || nextPlan[0] || null
          );
        }

        return nextPlan[0] || null;
      });

      setSelectedAsset((current) => {
        if (!current) return nextAssets[0] || null;

        return (
          nextAssets.find(
            (asset) =>
              asset.asset_id === current.asset_id
          ) || current
        );
      });

      if (!selectedAsset && nextAssets[0]?.asset_id) {
        try {
          const detail = await axios.get(
            `${API}/assets/${encodeURIComponent(
              nextAssets[0].asset_id
            )}/risk`
          );

          setSelectedAsset(detail.data);
        } catch {
          // Watchlist still works without the detail request.
        }
      }
    } catch (err) {
      console.error(err);

      setError(
        err?.response?.data?.detail ||
        "Rail-Yojna backend is unavailable. Start FastAPI on port 8000."
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    loadDashboard(true);
  }, []);

  async function openAsset(assetId) {
    try {
      setError("");

      const response = await axios.get(
        `${API}/assets/${encodeURIComponent(assetId)}/risk`
      );

      setSelectedAsset(response.data);

      const relatedTask = plan
        .filter(
          (task) =>
            task.asset_id === assetId
        )
        .sort(
          (a, b) =>
            Number(b.calibrated_risk || 0) -
            Number(a.calibrated_risk || 0)
        )[0];

      if (relatedTask) {
        setSelectedTask(relatedTask);
      }
    } catch (err) {
      console.error(err);

      setError(`Unable to load ${assetId}.`);
    }
  }

  function openTask(task) {
    setSelectedTask(task);

    if (task?.asset_id) {
      openAsset(task.asset_id);
    }
  }

  async function decide(task, decision) {
    if (!task) return;

    if (!decisionActor.trim()) {
      setDecisionMessage(
        "Reviewer name is required."
      );
      return;
    }

    try {
      setDecisionBusy(true);
      setDecisionMessage("");

      await axios.post(
        `${API}/planning/tasks/${encodeURIComponent(
          task.task_id
        )}/decision`,
        {
          decision,
          actor: decisionActor.trim(),
          note: decisionNote.trim(),
        }
      );

      setDecisionMessage(
        `${decision.toUpperCase()} recorded for ${task.task_id}`
      );

      setDecisionNote("");

      await loadDashboard(false);
    } catch (err) {
      setDecisionMessage(
        err?.response?.data?.detail ||
        "Decision could not be recorded."
      );
    } finally {
      setDecisionBusy(false);
    }
  }

  const filteredAssets = useMemo(() => {
    const term = search.trim().toLowerCase();

    return assets
      .filter((asset) => {
        if (!term) return true;

        return String(asset.asset_id || "")
          .toLowerCase()
          .includes(term);
      })
      .filter((asset) => {
        if (riskFilter === "ALL") return true;

        const risk = Number(asset.risk || 0);

        if (riskFilter === "CRITICAL") return risk >= 0.5;
        if (riskFilter === "HIGH")
          return risk >= 0.2 && risk < 0.5;
        if (riskFilter === "MEDIUM")
          return risk >= 0.05 && risk < 0.2;

        return risk < 0.05;
      })
      .slice(0, 30);
  }, [assets, search, riskFilter]);

  const filteredPlan = useMemo(() => {
    const term = search.trim().toLowerCase();

    return plan
      .filter((task) => {
        if (!term) return true;

        return [
          task.task_id,
          task.asset_id,
          task.task_type,
          task.section_id,
          task.track_id,
          task.priority,
        ]
          .filter(Boolean)
          .some((value) =>
            String(value)
              .toLowerCase()
              .includes(term)
          );
      })
      .slice(0, 25);
  }, [plan, search]);

  const selectedAssetTasks = selectedAsset
    ? plan
        .filter(
          (task) =>
            task.asset_id === selectedAsset.asset_id
        )
        .sort(
          (a, b) =>
            Number(b.calibrated_risk || 0) -
            Number(a.calibrated_risk || 0)
        )
        .slice(0, 5)
    : [];

  const assetCriticality =
    selectedAsset?.criticality ??
    selectedAssetTasks[0]?.criticality ??
    null;

  const assetCondition =
    selectedAsset?.condition_score ??
    selectedAssetTasks[0]?.condition_score ??
    null;

  const assetRisk =
    selectedAsset?.risk ??
    selectedAssetTasks[0]?.calibrated_risk ??
    0;

  const criticalCount = assets.filter(
    (asset) => Number(asset.risk || 0) >= 0.5
  ).length;

  const highCount = assets.filter(
    (asset) => {
      const risk = Number(asset.risk || 0);
      return risk >= 0.2 && risk < 0.5;
    }
  ).length;

  if (loading) {
    return (
      <div className="boot-screen">
        <div className="boot-card">
          <IndiaMapIcon />
          <h1>रेल-योजना</h1>
          <p>Maintenance decision support</p>
          <span>Connecting to live data…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <div className="brand-map">
            <IndiaMapIcon />
          </div>

          <div>
            <div className="brand-title">
              रेल-योजना
            </div>
            <div className="brand-subtitle">
              Rail-Yojna · Railway Maintenance Intelligence
            </div>
          </div>
        </div>

        <div className="header-center">
          <strong>Maintenance Operations</strong>
          <span>
            Risk, maintenance priority and human review
          </span>
        </div>

        <div className="header-actions">
          <span
            className={
              system
                ? "connection online"
                : "connection offline"
            }
          >
            <i />
            {system ? "Live" : "Offline"}
          </span>

          <button
            className="button secondary"
            onClick={() => loadDashboard(false)}
            disabled={refreshing}
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>

          <button
            className="button primary"
            onClick={() =>
              setPredictionOpen(true)
            }
          >
            New risk check
          </button>
        </div>
      </header>

      {error && (
        <div className="error-banner">
          <strong>Connection issue</strong>
          <span>{error}</span>
        </div>
      )}

      <main className="dashboard">
        <section className="metrics">
          <Metric
            label="Candidate tasks"
            value={
              summary
                ? summary.candidate_tasks.toLocaleString()
                : "—"
            }
            meta="Available for planning"
            tone="blue"
          />

          <Metric
            label="Selected tasks"
            value={
              summary
                ? summary.selected_tasks.toLocaleString()
                : "—"
            }
            meta={
              summary
                ? `${summary.deferred_tasks.toLocaleString()} deferred`
                : "—"
            }
            tone="green"
          />

          <Metric
            label="Selected hours"
            value={
              summary
                ? summary.selected_hours.toFixed(1)
                : "—"
            }
            meta="Estimated workload"
            tone="orange"
          />

          <Metric
            label="Risk mass"
            value={
              summary
                ? summary.risk_mass.toFixed(2)
                : "—"
            }
            meta="Selected maintenance risk"
            tone="red"
          />

          <Metric
            label="High risk tasks"
            value={
              metrics
                ? metrics.high_risk_tasks
                : highCount
            }
            meta={`${criticalCount} critical assets`}
            tone="orange"
          />

          <Metric
            label="Block required"
            value={
              metrics
                ? metrics.block_required_tasks
                : "—"
            }
            meta="Selected tasks"
            tone="green"
          />
        </section>

        <section className="toolbar">
          <div>
            <span className="section-kicker">
              LIVE DATA
            </span>
            <h2>Risk and maintenance overview</h2>
          </div>

          <div className="filters">
            <input
              value={search}
              onChange={(event) =>
                setSearch(event.target.value)
              }
              placeholder="Search asset or task…"
            />

            <select
              value={riskFilter}
              onChange={(event) =>
                setRiskFilter(event.target.value)
              }
            >
              <option value="ALL">All risk</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
          </div>
        </section>

        <section className="workspace">
          <article className="panel risk-panel">
            <div className="panel-header">
              <div>
                <h3>Risk watchlist</h3>
                <p>
                  Highest-risk assets from the live service.
                </p>
              </div>

              <button
                className="panel-count clickable"
                onClick={() =>
                  setBrowse({
                    type: "assets",
                  })
                }
                title="Browse risk assets"
              >
                {assets.length}
              </button>
            </div>

            <div className="table-wrap">
              {filteredAssets.length === 0 ? (
                <Empty>
                  No assets match the current filters.
                </Empty>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>Asset</th>
                      <th>Risk</th>
                      <th>Condition</th>
                      <th>Criticality</th>
                    </tr>
                  </thead>

                  <tbody>
                    {filteredAssets.map((asset) => (
                      <tr
                        key={asset.asset_id}
                        className={
                          selectedAsset?.asset_id ===
                          asset.asset_id
                            ? "selected"
                            : ""
                        }
                        onClick={() =>
                          openAsset(asset.asset_id)
                        }
                      >
                        <td>
                          <strong>
                            {asset.asset_id}
                          </strong>
                        </td>

                        <td>
                          <RiskChip
                            value={asset.risk}
                          />
                        </td>

                        <td>
                          {asset.condition_score != null
                            ? Number(
                                asset.condition_score
                              ).toFixed(1)
                            : "—"}
                        </td>

                        <td>
                          {asset.criticality != null
                            ? Number(
                                asset.criticality
                              ).toFixed(2)
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </article>

          <article className="panel plan-panel">
            <div className="panel-header">
              <div>
                <h3>Maintenance queue</h3>
                <p>
                  Browse selected maintenance recommendations.
                </p>
              </div>

              <button
                className="panel-count clickable"
                onClick={() =>
                  setBrowse({
                    type: "tasks",
                  })
                }
                title="Browse maintenance tasks"
              >
                {summary
                  ? summary.selected_tasks
                  : plan.length}
              </button>
            </div>

            <div className="table-wrap">
              {filteredPlan.length === 0 ? (
                <Empty>
                  No maintenance tasks match the search.
                </Empty>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>Task</th>
                      <th>Asset</th>
                      <th>Risk</th>
                      <th>Priority</th>
                      <th>Block</th>
                    </tr>
                  </thead>

                  <tbody>
                    {filteredPlan.map((task) => (
                      <tr
                        key={task.task_id}
                        className={
                          selectedTask?.task_id ===
                          task.task_id
                            ? "selected"
                            : ""
                        }
                        onClick={() =>
                          openTask(task)
                        }
                      >
                        <td>
                          <strong>
                            {task.task_id}
                          </strong>
                        </td>

                        <td>{task.asset_id}</td>

                        <td>
                          <RiskChip
                            value={
                              task.calibrated_risk
                            }
                          />
                        </td>

                        <td>{task.priority}</td>

                        <td>
                          {task.block_required
                            ? "Required"
                            : "No"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </article>
        </section>

        <section className="bottom-grid">
          <article className="panel detail-panel">
            <div className="panel-header">
              <div>
                <h3>Selected asset</h3>
                <p>
                  Live risk and maintenance context.
                </p>
              </div>
            </div>

            {!selectedAsset ? (
              <Empty>
                Select an asset from the watchlist.
              </Empty>
            ) : (
              <div className="asset-detail">
                <div className="asset-detail-top">
                  <div>
                    <div className="asset-id">
                      {selectedAsset.asset_id}
                    </div>

                    <div className="asset-meta">
                      {selectedAsset.asset_type ||
                        selectedAsset.asset_name ||
                        "Railway asset"}
                    </div>
                  </div>

                  <RiskChip value={assetRisk} />
                </div>

                <div className="detail-grid">
                  <div>
                    <span>Condition</span>
                    <strong>
                      {assetCondition != null
                        ? Number(
                            assetCondition
                          ).toFixed(1)
                        : "—"}
                    </strong>
                  </div>

                  <div>
                    <span>Criticality</span>
                    <strong>
                      {assetCriticality != null
                        ? Number(
                            assetCriticality
                          ).toFixed(2)
                        : "—"}
                    </strong>
                  </div>

                  <div>
                    <span>Risk probability</span>
                    <strong>
                      {riskPercent(assetRisk)}
                    </strong>
                  </div>

                  <div>
                    <span>Priority</span>
                    <strong>
                      {selectedAssetTasks[0]?.priority ||
                        "—"}
                    </strong>
                  </div>
                </div>

                <div className="asset-task-strip">
                  <div>
                    <span>Recommended task</span>
                    <strong>
                      {selectedAssetTasks[0]?.task_id ||
                        "No selected task"}
                    </strong>
                  </div>

                  <div>
                    <span>Work type</span>
                    <strong>
                      {selectedAssetTasks[0]?.task_type ||
                        "—"}
                    </strong>
                  </div>

                  <div>
                    <span>Block</span>
                    <strong>
                      {selectedAssetTasks[0]
                        ?.block_required
                        ? "Required"
                        : "No"}
                    </strong>
                  </div>
                </div>
              </div>
            )}
          </article>

          <article className="panel decision-panel">
            <div className="panel-header">
              <div>
                <h3>Planner decision</h3>
                <p>
                  Review the selected recommendation.
                </p>
              </div>
            </div>

            {!selectedTask ? (
              <Empty>
                Select a maintenance task.
              </Empty>
            ) : (
              <div className="decision-detail">
                <div className="decision-title">
                  <div>
                    <strong>
                      {selectedTask.task_id}
                    </strong>

                    <span>
                      {selectedTask.task_type ||
                        "Maintenance task"}
                    </span>
                  </div>

                  <RiskChip
                    value={
                      selectedTask.calibrated_risk
                    }
                  />
                </div>

                <div className="detail-grid compact">
                  <div>
                    <span>Asset</span>
                    <strong>
                      {selectedTask.asset_id}
                    </strong>
                  </div>

                  <div>
                    <span>Priority</span>
                    <strong>
                      {selectedTask.priority}
                    </strong>
                  </div>

                  <div>
                    <span>Duration</span>
                    <strong>
                      {
                        selectedTask.estimated_duration_minutes
                      }{" "}
                      min
                    </strong>
                  </div>

                  <div>
                    <span>Block</span>
                    <strong>
                      {selectedTask.block_required
                        ? "Required"
                        : "Not required"}
                    </strong>
                  </div>
                </div>

                <div className="explanation">
                  <span>Why this recommendation exists</span>

                  <strong>
                    {selectedTask.explanation
                      ?.primary_reason ||
                      "Based on current risk, asset condition and maintenance priority."}
                  </strong>

                  {Array.isArray(
                    selectedTask.explanation?.reasons
                  ) && (
                    <ul>
                      {selectedTask.explanation.reasons
                        .slice(0, 3)
                        .map((reason) => (
                          <li key={reason}>
                            {reason}
                          </li>
                        ))}
                    </ul>
                  )}
                </div>

                <div className="decision-form">
                  <label>
                    <span>Reviewer</span>

                    <input
                      value={decisionActor}
                      onChange={(event) =>
                        setDecisionActor(
                          event.target.value
                        )
                      }
                      placeholder="Planner name"
                    />
                  </label>

                  <label>
                    <span>Decision note</span>

                    <textarea
                      value={decisionNote}
                      onChange={(event) =>
                        setDecisionNote(
                          event.target.value
                        )
                      }
                      placeholder="Reason for this decision"
                      rows={2}
                    />
                  </label>
                </div>

                <div className="decision-actions">
                  <button
                    className="approve"
                    disabled={decisionBusy}
                    onClick={() =>
                      decide(
                        selectedTask,
                        "approve"
                      )
                    }
                  >
                    Approve
                  </button>

                  <button
                    disabled={decisionBusy}
                    onClick={() =>
                      decide(
                        selectedTask,
                        "modify"
                      )
                    }
                  >
                    Modify
                  </button>

                  <button
                    className="reject"
                    disabled={decisionBusy}
                    onClick={() =>
                      decide(
                        selectedTask,
                        "reject"
                      )
                    }
                  >
                    Reject
                  </button>
                </div>

                {decisionMessage && (
                  <div className="decision-message">
                    {decisionMessage}
                  </div>
                )}

                <div className="safety-note">
                  Human review is required before any
                  maintenance decision is treated as approved.
                </div>
              </div>
            )}
          </article>
        </section>

        <section className="audit-strip">
          <div>
            <span className="section-kicker">
              AUDIT
            </span>

            <strong>
              Recent planner decisions
            </strong>
          </div>

          <div className="audit-items">
            {audit.length === 0 ? (
              <span className="muted">
                No planner decisions recorded yet.
              </span>
            ) : (
              audit.slice(0, 4).map((event) => (
                <div
                  className="audit-item"
                  key={event.event_id}
                >
                  <strong>
                    {event.event_type
                      ?.replaceAll("_", " ")
                      .toLowerCase()}
                  </strong>

                  <span>
                    {event.recommendation_id ||
                      "system"}
                  </span>

                  <small>
                    {event.actor || "system"}
                  </small>
                </div>
              ))
            )}
          </div>

          <div className="footer-status">
            <span>30-day risk window</span>
            <span>Human review required</span>
            <span>Live backend</span>
          </div>
        </section>
      </main>

      {browse?.type === "tasks" && (
        <ListModal
          title="Maintenance recommendations"
          subtitle="Browse the complete selected maintenance queue."
          items={plan}
          total={
            summary?.selected_tasks ??
            plan.length
          }
          kind="tasks"
          onClose={() => setBrowse(null)}
          onSelect={openTask}
        />
      )}

      {browse?.type === "assets" && (
        <ListModal
          title="Risk watchlist"
          subtitle="Browse the available high-risk asset ranking."
          items={assets}
          total={assets.length}
          kind="assets"
          onClose={() => setBrowse(null)}
          onSelect={(asset) =>
            openAsset(asset.asset_id)
          }
        />
      )}

      {predictionOpen && (
        <div
          className="modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setPredictionOpen(false);
            }
          }}
        >
          <div className="prediction-modal">
            <button
              className="modal-close"
              onClick={() =>
                setPredictionOpen(false)
              }
            >
              ×
            </button>

            <LivePrediction
              onAssetOpen={(assetId) => {
                setPredictionOpen(false);
                openAsset(assetId);
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
'''

write(APP, APP_JSX)


# ============================================================
# LIVE PREDICTION — remove model naming from user UI
# ============================================================

backup(LIVE)
live_text = LIVE.read_text(encoding="utf-8")

live_text = live_text.replace(
    'Model: failure_30d_v2_logistic',
    'Prediction service connected',
)

live_text = live_text.replace(
    'Model: failure_30d_v3_logistic',
    'Prediction service connected',
)

live_text = live_text.replace(
    'validated V2 failure-risk inference pipeline',
    'validated failure-risk inference pipeline',
)

live_text = live_text.replace(
    'validated V3 failure-risk inference pipeline',
    'validated failure-risk inference pipeline',
)

live_text = live_text.replace(
    'label: "Moderate"',
    'label: "Medium"',
)

LIVE.write_text(
    live_text,
    encoding="utf-8",
)

print("[PASS] Removed model/version labels from user UI")


# ============================================================
# CSS
# ============================================================

write(
    CSS,
    r''':root {
  font-family:
    Inter,
    ui-sans-serif,
    system-ui,
    -apple-system,
    BlinkMacSystemFont,
    "Segoe UI",
    sans-serif;

  color: #17212b;
  background: #eef2f5;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
}

* {
  box-sizing: border-box;
}

html,
body,
#root {
  width: 100%;
  height: 100%;
  margin: 0;
}

body {
  min-width: 1180px;
  overflow: hidden;
  background: #eef2f5;
}

button,
input,
select,
textarea {
  font: inherit;
}

button {
  cursor: pointer;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.app {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: #eef2f5;
}

.header {
  height: 66px;
  display: grid;
  grid-template-columns: 285px 1fr auto;
  align-items: center;
  gap: 22px;
  padding: 0 22px;
  background: #fff;
  border-bottom: 1px solid #dce3e8;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-map {
  width: 38px;
  height: 44px;
  display: grid;
  place-items: center;
}

.india-map {
  width: 31px;
  height: 39px;
  fill: #0d477d;
  filter: drop-shadow(0 2px 2px rgba(13, 71, 125, 0.2));
}

.boot-card .india-map {
  width: 52px;
  height: 62px;
  margin: 0 auto 8px;
  fill: #0d477d;
}

.brand-title {
  font-size: 18px;
  line-height: 1;
  font-weight: 800;
  color: #17365d;
}

.brand-subtitle {
  margin-top: 4px;
  color: #7b8892;
  font-size: 9px;
}

.header-center {
  min-width: 0;
}

.header-center strong {
  display: block;
  font-size: 14px;
}

.header-center span {
  display: block;
  margin-top: 2px;
  color: #87939d;
  font-size: 9px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.connection {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-right: 4px;
  color: #71808b;
  font-size: 9px;
  white-space: nowrap;
}

.connection i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #d45c5c;
}

.connection.online i {
  background: #25a56b;
}

.button {
  height: 31px;
  padding: 0 11px;
  border-radius: 7px;
  font-size: 9px;
  font-weight: 700;
}

.button.secondary {
  border: 1px solid #d7e0e6;
  background: #fff;
  color: #445560;
}

.button.primary {
  border: 1px solid #17365d;
  background: #17365d;
  color: #fff;
}

.error-banner {
  position: absolute;
  top: 74px;
  left: 18px;
  right: 18px;
  z-index: 20;
  height: 34px;
  padding: 0 11px;
  display: flex;
  align-items: center;
  gap: 7px;
  border: 1px solid #ebc5c5;
  border-radius: 7px;
  background: #fff5f5;
  color: #813c3c;
  font-size: 9px;
}

.dashboard {
  height: calc(100vh - 66px);
  padding: 10px 18px;
  display: grid;
  grid-template-rows:
    71px
    43px
    minmax(0, 1fr)
    174px
    55px;
  gap: 9px;
  overflow: hidden;
}

.metrics {
  min-width: 0;
  display: grid;
  grid-template-columns:
    repeat(6, minmax(0, 1fr));
  gap: 8px;
}

.metric {
  position: relative;
  min-width: 0;
  padding: 10px 12px;
  overflow: hidden;
  border: 1px solid #dce4e8;
  border-radius: 9px;
  background: #fff;
}

.metric-accent {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
}

.metric-blue .metric-accent {
  background: #2f7dc5;
}

.metric-green .metric-accent {
  background: #23a66b;
}

.metric-orange .metric-accent {
  background: #e8922f;
}

.metric-red .metric-accent {
  background: #dc5a54;
}

.metric-label {
  margin-top: 2px;
  color: #778590;
  font-size: 8px;
  font-weight: 750;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.metric-value {
  margin-top: 5px;
  font-size: 22px;
  line-height: 1;
  font-weight: 800;
  letter-spacing: -0.5px;
}

.metric-meta {
  margin-top: 5px;
  color: #9aa4ac;
  font-size: 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.toolbar {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-kicker {
  color: #7f8e99;
  font-size: 7px;
  font-weight: 800;
  letter-spacing: 0.11em;
}

.toolbar h2 {
  margin: 1px 0 0;
  font-size: 15px;
}

.filters {
  display: flex;
  gap: 7px;
}

.filters input,
.filters select {
  height: 30px;
  border: 1px solid #d6dfe5;
  border-radius: 7px;
  background: #fff;
  color: #35434d;
  font-size: 9px;
}

.filters input {
  width: 220px;
  padding: 0 9px;
}

.filters select {
  padding: 0 8px;
}

.workspace {
  min-height: 0;
  display: grid;
  grid-template-columns: 1.16fr 1fr;
  gap: 9px;
}

.panel {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid #dce4e8;
  border-radius: 9px;
  background: #fff;
}

.panel-header {
  height: 49px;
  padding: 9px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #edf0f2;
}

.panel-header h3 {
  margin: 0;
  font-size: 12px;
}

.panel-header p {
  margin: 3px 0 0;
  color: #8a969f;
  font-size: 8px;
}

.panel-count {
  min-width: 27px;
  height: 25px;
  padding: 0 7px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  border: 0;
  background: #edf3f8;
  color: #325a7f;
  font-size: 8px;
  font-weight: 800;
}

.panel-count.clickable {
  cursor: pointer;
}

.panel-count.clickable:hover {
  background: #dfeaf3;
  transform: translateY(-1px);
}

.table-wrap {
  height: calc(100% - 49px);
  overflow: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 8px;
}

th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #f7fafb;
  color: #7d8993;
  font-size: 8px;
  font-weight: 750;
}

th,
td {
  padding: 7px 9px;
  border-bottom: 1px solid #edf0f2;
  text-align: left;
  white-space: nowrap;
}

tbody tr {
  cursor: pointer;
  transition:
    background 0.12s ease,
    box-shadow 0.12s ease;
}

tbody tr:hover {
  background: #f6fafc;
}

tbody tr.selected {
  background: #edf5fb;
  box-shadow: inset 3px 0 0 #3a78ad;
}

td strong {
  font-weight: 750;
}

.risk-chip {
  display: inline-flex;
  min-height: 19px;
  padding: 0 6px;
  align-items: center;
  border-radius: 999px;
  font-size: 7px;
  font-weight: 800;
}

.risk-chip.low {
  background: #e7f5ec;
  color: #24764c;
}

.risk-chip.medium {
  background: #fff4d5;
  color: #977118;
}

.risk-chip.high {
  background: #ffead9;
  color: #aa5923;
}

.risk-chip.critical {
  background: #fde3e3;
  color: #a83f3f;
}

.empty {
  min-height: 85px;
  height: 100%;
  display: grid;
  place-items: center;
  color: #9aa4ab;
  font-size: 9px;
  text-align: center;
  padding: 16px;
}

.bottom-grid {
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px;
}

.asset-detail,
.decision-detail {
  height: calc(100% - 49px);
  min-height: 0;
  overflow: hidden;
  padding: 10px 12px;
}

.asset-detail-top,
.decision-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.asset-id {
  font-size: 14px;
  font-weight: 800;
}

.asset-meta {
  margin-top: 2px;
  color: #8b969f;
  font-size: 8px;
}

.detail-grid {
  margin-top: 8px;
  display: grid;
  grid-template-columns:
    repeat(4, minmax(0, 1fr));
  gap: 7px;
}

.detail-grid div {
  min-width: 0;
  padding: 7px;
  border: 1px solid #e6ecef;
  border-radius: 6px;
  background: #fbfcfd;
}

.detail-grid span,
.asset-task-strip span {
  display: block;
  color: #85919a;
  font-size: 7px;
}

.detail-grid strong,
.asset-task-strip strong {
  display: block;
  margin-top: 3px;
  color: #263946;
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.asset-task-strip {
  margin-top: 7px;
  display: grid;
  grid-template-columns:
    1.2fr 1fr 0.7fr;
  gap: 7px;
}

.asset-task-strip > div {
  padding: 7px;
  border-radius: 6px;
  background: #f2f8f5;
  border: 1px solid #d8ece0;
}

.asset-task-strip > div:nth-child(2) {
  background: #fff7e9;
  border-color: #f0dfbc;
}

.asset-task-strip > div:nth-child(3) {
  background: #eef5fb;
  border-color: #d7e5f2;
}

.decision-title strong {
  display: block;
  color: #203849;
  font-size: 12px;
}

.decision-title span {
  display: block;
  margin-top: 2px;
  color: #8d99a2;
  font-size: 7px;
}

.explanation {
  margin-top: 7px;
  padding: 7px 8px;
  border-left: 3px solid #e58c2e;
  background: #fff9f1;
}

.explanation > span {
  display: block;
  color: #7d8992;
  font-size: 7px;
  font-weight: 750;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.explanation > strong {
  display: block;
  margin-top: 3px;
  color: #4c4a46;
  font-size: 8px;
}

.explanation ul {
  margin: 4px 0 0;
  padding-left: 15px;
}

.explanation li {
  margin: 2px 0;
  color: #77746f;
  font-size: 7px;
}

.decision-form {
  margin-top: 7px;
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  gap: 7px;
}

.decision-form label > span {
  display: block;
  margin-bottom: 3px;
  color: #7f8b94;
  font-size: 7px;
  font-weight: 750;
  text-transform: uppercase;
}

.decision-form input,
.decision-form textarea {
  width: 100%;
  border: 1px solid #d7e0e5;
  border-radius: 6px;
  background: #fff;
  color: #2f414d;
  font-size: 8px;
  outline: none;
}

.decision-form input {
  height: 28px;
  padding: 0 7px;
}

.decision-form textarea {
  min-height: 28px;
  padding: 6px 7px;
  resize: none;
}

.decision-form input:focus,
.decision-form textarea:focus {
  border-color: #5c82a7;
  box-shadow:
    0 0 0 2px rgba(92, 130, 167, 0.1);
}

.decision-actions {
  display: flex;
  gap: 6px;
  margin-top: 7px;
}

.decision-actions button {
  height: 27px;
  min-width: 75px;
  padding: 0 9px;
  border: 1px solid #d6dfe5;
  border-radius: 6px;
  background: #fff;
  color: #43535f;
  font-size: 8px;
  font-weight: 800;
}

.decision-actions .approve {
  border-color: #b9dcc5;
  background: #e9f7ee;
  color: #2a7a4f;
}

.decision-actions .reject {
  border-color: #eac4c4;
  background: #fff0f0;
  color: #a24646;
}

.decision-message {
  margin-top: 5px;
  color: #4c6e8b;
  font-size: 8px;
}

.safety-note {
  margin-top: 4px;
  color: #9aa2a8;
  font-size: 7px;
}

.audit-strip {
  min-width: 0;
  display: grid;
  grid-template-columns: 180px 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 7px 11px;
  border: 1px solid #dce4e8;
  border-radius: 9px;
  background: #fff;
}

.audit-strip > div:first-child strong {
  display: block;
  margin-top: 2px;
  font-size: 9px;
}

.audit-items {
  min-width: 0;
  display: flex;
  gap: 6px;
  overflow: hidden;
}

.audit-item {
  min-width: 130px;
  padding: 5px 7px;
  border-radius: 6px;
  border: 1px solid #e6ecef;
  background: #fafbfc;
}

.audit-item strong,
.audit-item span,
.audit-item small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.audit-item strong {
  color: #52636e;
  font-size: 7px;
}

.audit-item span {
  margin-top: 2px;
  color: #7e8a93;
  font-size: 7px;
}

.audit-item small {
  margin-top: 1px;
  color: #9ca5ab;
  font-size: 6px;
}

.footer-status {
  display: flex;
  gap: 5px;
}

.footer-status span {
  padding: 4px 6px;
  border-radius: 999px;
  background: #f0f5f8;
  color: #6f7f8b;
  font-size: 6px;
  white-space: nowrap;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: grid;
  place-items: center;
  padding: 18px;
  background: rgba(18, 31, 42, 0.47);
}

.browse-modal {
  width: min(1040px, 94vw);
  height: min(760px, 88vh);
  display: grid;
  grid-template-rows:
    78px
    47px
    minmax(0, 1fr)
    32px;
  overflow: hidden;
  border: 1px solid #d4dfe6;
  border-radius: 12px;
  background: #f7fafb;
  box-shadow:
    0 25px 80px rgba(0, 0, 0, 0.24);
}

.browse-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 13px 17px;
  background: #fff;
  border-bottom: 1px solid #e3eaee;
}

.browse-header h2 {
  margin: 2px 0 0;
  color: #17365d;
  font-size: 18px;
}

.browse-header p {
  margin: 3px 0 0;
  color: #84919a;
  font-size: 8px;
}

.modal-close {
  width: 29px;
  height: 29px;
  border: 1px solid #d7e0e5;
  border-radius: 6px;
  background: #fff;
  color: #66757f;
  font-size: 17px;
}

.browse-toolbar {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 12px;
  border-bottom: 1px solid #e2e9ed;
  background: #fbfcfd;
}

.browse-toolbar input {
  flex: 1;
  height: 31px;
  padding: 0 9px;
  border: 1px solid #d5dfe5;
  border-radius: 6px;
  background: #fff;
  font-size: 8px;
  outline: none;
}

.count-select {
  display: flex;
  align-items: center;
  gap: 5px;
  color: #788691;
  font-size: 8px;
}

.count-select select {
  height: 31px;
  border: 1px solid #d5dfe5;
  border-radius: 6px;
  background: #fff;
  color: #31434f;
  font-size: 8px;
}

.result-count {
  color: #80909c;
  font-size: 8px;
  white-space: nowrap;
}

.browse-table-wrap {
  min-height: 0;
  overflow: auto;
  background: #fff;
}

.browse-table-wrap table {
  font-size: 8px;
}

.browse-table-wrap tbody tr:hover {
  background: #edf6fa;
}

.browse-footer {
  display: flex;
  align-items: center;
  padding: 0 11px;
  border-top: 1px solid #e2e9ed;
  background: #f8fafb;
  color: #89969f;
  font-size: 7px;
}

.prediction-modal {
  position: relative;
  width: min(760px, 92vw);
  max-height: 90vh;
  overflow: auto;
  border: 1px solid #d4dfe6;
  border-radius: 12px;
  background: #f7fafb;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.24);
}

.prediction-modal > .modal-close {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 4;
}

.prediction-layout {
  padding: 0 13px 13px;
}

.prediction-modal .page-heading {
  padding: 15px 17px 8px;
}

.prediction-modal .page-heading h2 {
  color: #17365d;
  font-size: 21px;
}

.prediction-modal .page-heading p {
  color: #7e8b95;
  font-size: 9px;
}

.prediction-form {
  overflow: hidden;
  border: 1px solid #dce4e8;
  background: #fff;
  border-radius: 9px;
}

.prediction-form .form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 9px 11px;
  padding: 13px;
}

.prediction-form label > span {
  display: block;
  margin-bottom: 4px;
  color: #72808b;
  font-size: 8px;
  font-weight: 750;
}

.prediction-form input,
.prediction-form textarea {
  width: 100%;
  min-height: 32px;
  padding: 0 8px;
  border: 1px solid #d6e0e6;
  border-radius: 6px;
  background: #fff;
  color: #293c49;
  font-size: 9px;
  outline: none;
}

.prediction-form input:focus,
.prediction-form textarea:focus {
  border-color: #6285a7;
  box-shadow:
    0 0 0 2px rgba(98, 133, 167, 0.1);
}

.prediction-form .form-footer {
  min-height: 48px;
  padding: 8px 13px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid #edf1f3;
  background: #fbfcfd;
}

.prediction-form .form-footer span {
  color: #7c8b96;
  font-size: 8px;
}

.prediction-form .primary-button {
  min-height: 31px;
  padding: 0 12px;
  border: 0;
  border-radius: 6px;
  background: #17365d;
  color: #fff;
  font-size: 9px;
  font-weight: 750;
}

.live-risk-meter {
  margin-top: 9px;
  padding: 0 13px 12px;
}

.live-risk-meter-track {
  position: relative;
  height: 9px;
  border-radius: 999px;
  background:
    linear-gradient(
      90deg,
      #2aa876 0%,
      #83bf61 25%,
      #e2c246 45%,
      #ef9840 63%,
      #df5d56 100%
    );
}

.live-risk-meter-marker {
  position: absolute;
  top: 50%;
  width: 13px;
  height: 13px;
  transform: translate(-50%, -50%);
  border: 2px solid #fff;
  border-radius: 50%;
  background: #17365d;
  box-shadow:
    0 1px 6px rgba(0, 0, 0, 0.25);
}

.live-risk-meter-marker[data-risk="low"] {
  background: #239d67;
}

.live-risk-meter-marker[data-risk="medium"] {
  background: #c5a329;
}

.live-risk-meter-marker[data-risk="high"] {
  background: #d87d2d;
}

.live-risk-meter-marker[data-risk="critical"] {
  background: #cb4e4e;
}

.live-risk-meter-scale {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  color: #89959e;
  font-size: 7px;
}

.boot-screen {
  width: 100vw;
  height: 100vh;
  display: grid;
  place-items: center;
  background:
    radial-gradient(
      circle at 50% 40%,
      #ffffff 0,
      #edf3f7 52%,
      #e6edf2 100%
    );
}

.boot-card {
  text-align: center;
}

.boot-card h1 {
  margin: 0;
  color: #17365d;
  font-size: 23px;
}

.boot-card p {
  margin: 4px 0;
  color: #657681;
  font-size: 10px;
}

.boot-card span {
  color: #98a3ab;
  font-size: 8px;
}

.muted {
  color: #9ba4ab;
  font-size: 8px;
}

@media (max-width: 1250px) {
  .header {
    grid-template-columns: 240px 1fr auto;
  }

  .dashboard {
    padding-left: 10px;
    padding-right: 10px;
  }

  .metrics {
    gap: 6px;
  }

  .metric {
    padding-left: 9px;
    padding-right: 9px;
  }
}
''',
)


# ============================================================
# VALIDATION
# ============================================================

run(
    [
        "python3",
        "-m",
        "py_compile",
        str(planning_service),
        str(routes),
    ]
)

run(
    [
        "python3",
        "-m",
        "pytest",
        "-q",
        "tests",
    ],
    check=True,
)

run(
    [
        "npm",
        "--prefix",
        "frontend",
        "run",
        "build",
    ],
    check=True,
)

report = {
    "phase": "9-user-ui-v2",
    "status": "PASS",
    "planner_browse_limit": 1500,
    "task_page_options": [25, 50, 100, 250, 500, 1000, 1500],
    "asset_page_options": [25, 50, 100],
    "single_screen_dashboard": True,
    "internal_list_scrolling": True,
    "expandable_task_browse": True,
    "expandable_asset_browse": True,
    "india_map_brand": True,
    "hindi_brand": "रेल-योजना",
    "color_accents": [
        "blue",
        "green",
        "orange",
        "red",
    ],
    "model_labels_removed_from_user_ui": True,
    "selected_asset_auto_populated": True,
    "planner_decision_auto_populated": True,
    "real_api_data": True,
    "dummy_dashboard_values": False,
    "backup": str(BACKUP.relative_to(ROOT)),
    "pytest": "PASS",
    "frontend_build": "PASS",
}

report_path = ROOT / "data/validation/phase9_user_ui_v2_report.json"
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("\n" + "=" * 80)
print("PHASE 9 USER UI V2 COMPLETE")
print("=" * 80)
print(json.dumps(report, indent=2, ensure_ascii=False))
print("=" * 80)
