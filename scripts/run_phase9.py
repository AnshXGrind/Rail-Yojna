from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend/src"
BACKUP = ROOT / "data/backups" / f"phase9_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
REPORT = ROOT / "data/validation/phase9_report.json"


def backup(path: Path):
    if path.exists():
        target = BACKUP / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    backup(path)
    path.write_text(content, encoding="utf-8")


def run(cmd, check=True):
    print("\n$", " ".join(cmd))
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        check=check,
    )


def fail(message: str):
    print(f"\n[FAIL] {message}")
    print(f"[BACKUP] {BACKUP}")
    raise SystemExit(1)


print("=" * 80)
print("RAIL-YOJNA PHASE 9 — OPERATIONAL DASHBOARD")
print("=" * 80)

BACKUP.mkdir(parents=True, exist_ok=True)
(FRONTEND / "components").mkdir(parents=True, exist_ok=True)


APP = r'''import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import LivePrediction from "./components/LivePrediction";
import "./App.css";

const API = "http://127.0.0.1:8000/api/v1";

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

function Metric({ label, value, meta }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      <div className="metric-meta">{meta}</div>
    </div>
  );
}

function Empty({ children }) {
  return <div className="empty">{children}</div>;
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

  const [predictionOpen, setPredictionOpen] = useState(false);
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [decisionMessage, setDecisionMessage] = useState("");

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
        axios.get(`${API}/planning/plan?limit=100`),
        axios.get(`${API}/audit/events?limit=12`),
      ]);

      if (healthResponse.data.status !== "ok") {
        throw new Error("Backend health check failed");
      }

      setSystem(systemResponse.data);
      setSummary(summaryResponse.data);
      setMetrics(metricsResponse.data);
      setAssets(assetResponse.data.items || []);
      setPlan(planResponse.data.items || []);
      setAudit(auditResponse.data.items || []);

      setSelectedAsset((current) => {
        if (!current) return null;

        return (
          (assetResponse.data.items || []).find(
            (item) => item.asset_id === current.asset_id
          ) || current
        );
      });
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
    } catch (err) {
      console.error(err);
      setError(`Unable to load ${assetId}.`);
    }
  }

  async function decide(task, decision) {
    if (!task) return;

    const actor = window.prompt(
      "Planner / reviewer name:",
      "planner"
    );

    if (!actor) return;

    const note =
      window.prompt("Decision note:", "") ?? "";

    try {
      setDecisionBusy(true);
      setDecisionMessage("");

      const response = await axios.post(
        `${API}/planning/tasks/${encodeURIComponent(task.task_id)}/decision`,
        {
          decision,
          actor,
          note,
        }
      );

      setDecisionMessage(
        `${decision.toUpperCase()} recorded for ${task.task_id}`
      );

      await loadDashboard(false);

      if (response.data) {
        setSelectedTask((current) =>
          current ? { ...current } : current
        );
      }
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

        return String(asset.asset_id)
          .toLowerCase()
          .includes(term);
      })
      .filter((asset) => {
        if (riskFilter === "ALL") return true;

        const risk = Number(asset.risk || 0);

        if (riskFilter === "CRITICAL") return risk >= 0.5;
        if (riskFilter === "HIGH") return risk >= 0.2 && risk < 0.5;
        if (riskFilter === "MEDIUM") return risk >= 0.05 && risk < 0.2;
        if (riskFilter === "LOW") return risk < 0.05;

        return true;
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
        ]
          .filter(Boolean)
          .some((value) =>
            String(value).toLowerCase().includes(term)
          );
      })
      .slice(0, 25);
  }, [plan, search]);

  const criticalCount = assets.filter(
    (asset) => Number(asset.risk || 0) >= 0.5
  ).length;

  const highCount = assets.filter(
    (asset) => {
      const risk = Number(asset.risk || 0);
      return risk >= 0.2 && risk < 0.5;
    }
  ).length;

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

  if (loading) {
    return (
      <div className="boot-screen">
        <div className="boot-card">
          <div className="brand-mark">RY</div>
          <h1>Rail-Yojna</h1>
          <p>Loading live maintenance intelligence…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <div className="brand-mark">RY</div>

          <div>
            <div className="brand-title">
              Rail-Yojna
            </div>
            <div className="brand-subtitle">
              Maintenance decision support
            </div>
          </div>
        </div>

        <div className="header-center">
          <strong>Operational Dashboard</strong>
          <span>
            V3 failure risk · 30-day horizon · maintenance_plan_v2
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
            {system ? "Backend online" : "Backend unavailable"}
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
            onClick={() => setPredictionOpen(true)}
          >
            Live prediction
          </button>
        </div>
      </header>

      {error && (
        <div className="error-banner">
          <strong>Backend error</strong>
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
            meta="Current planning dataset"
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
          />

          <Metric
            label="Selected hours"
            value={
              summary
                ? summary.selected_hours.toFixed(1)
                : "—"
            }
            meta="Estimated maintenance workload"
          />

          <Metric
            label="Risk mass"
            value={
              summary
                ? summary.risk_mass.toFixed(2)
                : "—"
            }
            meta="Selected maintenance risk"
          />

          <Metric
            label="High risk tasks"
            value={
              metrics
                ? metrics.high_risk_tasks
                : highCount
            }
            meta={`${criticalCount} critical assets`}
          />

          <Metric
            label="Block-required"
            value={
              metrics
                ? metrics.block_required_tasks
                : "—"
            }
            meta="Selected tasks"
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
                  Highest-risk assets returned by the live API.
                </p>
              </div>

              <span className="panel-count">
                {filteredAssets.length}
              </span>
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
                      <th>Priority</th>
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
                          <strong>{asset.asset_id}</strong>
                        </td>
                        <td>
                          <RiskChip value={asset.risk} />
                        </td>
                        <td>
                          {asset.condition_score != null
                            ? Number(
                                asset.condition_score
                              ).toFixed(1)
                            : "—"}
                        </td>
                        <td>
                          {asset.priority || "—"}
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
                  Selected tasks from maintenance_plan_v2.
                </p>
              </div>

              <span className="panel-count">
                {filteredPlan.length}
              </span>
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
                          selectedTask?.task_id === task.task_id
                            ? "selected"
                            : ""
                        }
                        onClick={() =>
                          setSelectedTask(task)
                        }
                      >
                        <td>
                          <strong>{task.task_id}</strong>
                        </td>
                        <td>{task.asset_id}</td>
                        <td>
                          <RiskChip
                            value={task.calibrated_risk}
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
                  Live asset risk and the maintenance context
                  available from the backend.
                </p>
              </div>
            </div>

            {!selectedAsset ? (
              <Empty>
                Select an asset from the risk watchlist.
              </Empty>
            ) : (
              <div className="asset-detail">
                <div className="asset-detail-top">
                  <div>
                    <div className="asset-id">
                      {selectedAsset.asset_id}
                    </div>
                    <div className="asset-meta">
                      {selectedAsset.asset_type || "Railway asset"}
                    </div>
                  </div>

                  <RiskChip value={selectedAsset.risk} />
                </div>

                <div className="detail-grid">
                  <div>
                    <span>Condition</span>
                    <strong>
                      {selectedAsset.condition_score != null
                        ? Number(
                            selectedAsset.condition_score
                          ).toFixed(1)
                        : "—"}
                    </strong>
                  </div>

                  <div>
                    <span>Criticality</span>
                    <strong>
                      {selectedAsset.criticality != null
                        ? Number(
                            selectedAsset.criticality
                          ).toFixed(2)
                        : "—"}
                    </strong>
                  </div>

                  <div>
                    <span>Risk probability</span>
                    <strong>
                      {riskPercent(selectedAsset.risk)}
                    </strong>
                  </div>

                  <div>
                    <span>Data mode</span>
                    <strong>
                      {selectedAsset.data_mode || "synthetic"}
                    </strong>
                  </div>
                </div>

                <div className="asset-tasks">
                  <div className="mini-title">
                    Related maintenance tasks
                  </div>

                  {selectedAssetTasks.length === 0 ? (
                    <span className="muted">
                      No selected task found for this asset.
                    </span>
                  ) : (
                    <div className="task-pills">
                      {selectedAssetTasks.map((task) => (
                        <button
                          key={task.task_id}
                          onClick={() =>
                            setSelectedTask(task)
                          }
                        >
                          {task.task_id}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </article>

          <article className="panel decision-panel">
            <div className="panel-header">
              <div>
                <h3>Planner decision</h3>
                <p>
                  Human approval is mandatory.
                </p>
              </div>
            </div>

            {!selectedTask ? (
              <Empty>
                Select a maintenance task to review.
              </Empty>
            ) : (
              <div className="decision-detail">
                <div className="decision-title">
                  <div>
                    <strong>{selectedTask.task_id}</strong>
                    <span>
                      {selectedTask.task_type}
                    </span>
                  </div>

                  <RiskChip
                    value={selectedTask.calibrated_risk}
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
                      {selectedTask.estimated_duration_minutes} min
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
                    {selectedTask.explanation?.primary_reason ||
                      "Deterministic planner explanation"}
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

                <div className="decision-actions">
                  <button
                    className="approve"
                    disabled={decisionBusy}
                    onClick={() =>
                      decide(selectedTask, "approve")
                    }
                  >
                    Approve
                  </button>

                  <button
                    disabled={decisionBusy}
                    onClick={() =>
                      decide(selectedTask, "modify")
                    }
                  >
                    Modify
                  </button>

                  <button
                    className="reject"
                    disabled={decisionBusy}
                    onClick={() =>
                      decide(selectedTask, "reject")
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
                  Decision support only. No signalling, routing,
                  dispatch, or train-movement authority is issued.
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
            <strong>Recent planner decisions</strong>
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
                    {event.recommendation_id || "system"}
                  </span>
                  <small>
                    {event.actor || "system"}
                  </small>
                </div>
              ))
            )}
          </div>

          <div className="footer-status">
            <span>
              Model{" "}
              {system?.model_version ||
                "failure_30d_v3_logistic"}
            </span>

            <span>
              Planner{" "}
              {system?.planner_version ||
                "maintenance_plan_v2"}
            </span>

            <span>
              Human review required
            </span>
          </div>
        </section>
      </main>

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


CSS = r''':root {
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
select {
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
  height: 64px;
  display: grid;
  grid-template-columns: 245px 1fr auto;
  align-items: center;
  gap: 20px;
  padding: 0 22px;
  background: #ffffff;
  border-bottom: 1px solid #dfe5e9;
}

.brand {
  display: flex;
  align-items: center;
  gap: 11px;
}

.brand-mark {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  background: #17365d;
  color: white;
  font-size: 12px;
  font-weight: 800;
}

.brand-title {
  font-size: 15px;
  font-weight: 800;
}

.brand-subtitle {
  margin-top: 2px;
  color: #7a8791;
  font-size: 10px;
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
  color: #7b8792;
  font-size: 10px;
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
  margin-right: 5px;
  color: #687681;
  font-size: 10px;
  white-space: nowrap;
}

.connection i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #c95757;
}

.connection.online i {
  background: #35a86b;
}

.button {
  height: 32px;
  padding: 0 12px;
  border-radius: 7px;
  border: 1px solid #d8e0e6;
  font-size: 11px;
  font-weight: 650;
}

.button.secondary {
  color: #43525e;
  background: #fff;
}

.button.primary {
  color: #fff;
  background: #17365d;
  border-color: #17365d;
}

.error-banner {
  height: 36px;
  margin: 8px 18px 0;
  padding: 0 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid #ecc7c7;
  border-radius: 7px;
  background: #fff5f5;
  color: #813c3c;
  font-size: 10px;
}

.dashboard {
  height: calc(100vh - 64px);
  padding: 12px 18px;
  display: grid;
  grid-template-rows: 70px 44px minmax(0, 1fr) 170px 58px;
  gap: 10px;
}

.metrics {
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.metric {
  min-width: 0;
  padding: 10px 13px;
  border: 1px solid #dde4e8;
  border-radius: 9px;
  background: #fff;
  overflow: hidden;
}

.metric-label {
  color: #74818c;
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.metric-value {
  margin-top: 4px;
  font-size: 22px;
  line-height: 1;
  font-weight: 800;
  letter-spacing: -0.5px;
}

.metric-meta {
  margin-top: 4px;
  color: #98a2aa;
  font-size: 9px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-width: 0;
}

.section-kicker {
  color: #81909b;
  font-size: 8px;
  font-weight: 800;
  letter-spacing: 0.11em;
}

.toolbar h2 {
  margin: 1px 0 0;
  font-size: 16px;
}

.filters {
  display: flex;
  gap: 7px;
}

.filters input,
.filters select {
  height: 31px;
  border: 1px solid #d7dfe5;
  border-radius: 7px;
  background: #fff;
  color: #35424d;
  font-size: 10px;
}

.filters input {
  width: 210px;
  padding: 0 10px;
}

.filters select {
  padding: 0 8px;
}

.workspace {
  min-height: 0;
  display: grid;
  grid-template-columns: 1.16fr 1fr;
  gap: 10px;
}

.panel {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid #dde4e8;
  border-radius: 10px;
  background: #fff;
}

.panel-header {
  height: 51px;
  padding: 10px 13px;
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
  color: #8b969f;
  font-size: 9px;
}

.panel-count {
  min-width: 25px;
  height: 23px;
  padding: 0 7px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: #f1f4f7;
  color: #586672;
  font-size: 9px;
  font-weight: 750;
}

.table-wrap {
  height: calc(100% - 51px);
  overflow: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 9px;
}

th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #f8fafb;
  color: #7c8994;
  font-weight: 700;
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
  transition: background 0.12s ease;
}

tbody tr:hover,
tbody tr.selected {
  background: #f3f7fb;
}

td strong {
  font-weight: 750;
}

.risk-chip {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 7px;
  border-radius: 999px;
  font-size: 8px;
  font-weight: 750;
}

.risk-chip.low {
  background: #e8f5ee;
  color: #26724c;
}

.risk-chip.medium {
  background: #fff5d9;
  color: #9a7415;
}

.risk-chip.high {
  background: #ffeadc;
  color: #a85620;
}

.risk-chip.critical {
  background: #fde4e4;
  color: #a63e3e;
}

.empty {
  height: 100%;
  min-height: 90px;
  display: grid;
  place-items: center;
  padding: 20px;
  color: #9aa3ab;
  font-size: 10px;
  text-align: center;
}

.bottom-grid {
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.asset-detail,
.decision-detail {
  height: calc(100% - 51px);
  min-height: 0;
  padding: 11px 13px;
  overflow: hidden;
}

.asset-detail-top,
.decision-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.asset-id {
  font-size: 15px;
  font-weight: 800;
}

.asset-meta {
  margin-top: 2px;
  color: #89949e;
  font-size: 9px;
}

.detail-grid {
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.detail-grid.compact {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.detail-grid div {
  min-width: 0;
  padding: 8px;
  border: 1px solid #e8edf0;
  border-radius: 7px;
}

.detail-grid span {
  display: block;
  color: #88949e;
  font-size: 8px;
}

.detail-grid strong {
  display: block;
  margin-top: 4px;
  font-size: 11px;
}

.asset-tasks {
  margin-top: 9px;
}

.mini-title {
  margin-bottom: 6px;
  color: #78858f;
  font-size: 8px;
  font-weight: 750;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.task-pills {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.task-pills button {
  height: 23px;
  padding: 0 7px;
  border: 1px solid #dce3e7;
  border-radius: 5px;
  background: #fff;
  color: #40505c;
  font-size: 8px;
}

.decision-title strong {
  display: block;
  font-size: 13px;
}

.decision-title span {
  display: block;
  margin-top: 3px;
  color: #8c979f;
  font-size: 8px;
}

.explanation {
  margin-top: 9px;
  padding: 8px 9px;
  border-left: 3px solid #54769b;
  background: #f6f9fb;
}

.explanation > span {
  display: block;
  color: #7e8a94;
  font-size: 8px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.explanation > strong {
  display: block;
  margin-top: 4px;
  font-size: 9px;
}

.explanation ul {
  margin: 5px 0 0;
  padding-left: 16px;
}

.explanation li {
  margin: 2px 0;
  color: #687681;
  font-size: 8px;
}

.decision-actions {
  display: flex;
  gap: 7px;
  margin-top: 10px;
}

.decision-actions button {
  height: 28px;
  min-width: 78px;
  padding: 0 10px;
  border: 1px solid #d8e0e5;
  border-radius: 6px;
  background: #fff;
  color: #43525e;
  font-size: 9px;
  font-weight: 700;
}

.decision-actions .approve {
  background: #eaf7ef;
  border-color: #bfdfca;
  color: #2b7750;
}

.decision-actions .reject {
  background: #fff0f0;
  border-color: #eccaca;
  color: #a24848;
}

.decision-message {
  margin-top: 7px;
  color: #49667f;
  font-size: 8px;
}

.safety-note {
  margin-top: 6px;
  color: #949da4;
  font-size: 7px;
}

.audit-strip {
  min-width: 0;
  display: grid;
  grid-template-columns: 185px 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border: 1px solid #dde4e8;
  border-radius: 9px;
  background: #fff;
}

.audit-strip > div:first-child strong {
  display: block;
  margin-top: 2px;
  font-size: 10px;
}

.audit-items {
  min-width: 0;
  display: flex;
  gap: 7px;
  overflow: hidden;
}

.audit-item {
  min-width: 140px;
  padding: 6px 8px;
  border: 1px solid #e7ebee;
  border-radius: 6px;
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
  color: #495862;
  font-size: 8px;
}

.audit-item span {
  margin-top: 2px;
  color: #77848e;
  font-size: 8px;
}

.audit-item small {
  margin-top: 2px;
  color: #9aa3aa;
  font-size: 7px;
}

.footer-status {
  display: flex;
  gap: 9px;
  align-items: center;
  white-space: nowrap;
}

.footer-status span {
  padding: 5px 7px;
  border-radius: 999px;
  background: #f1f4f7;
  color: #71808b;
  font-size: 7px;
}

.muted {
  color: #9aa4ac;
  font-size: 9px;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(16, 26, 36, 0.48);
}

.prediction-modal {
  position: relative;
  width: min(760px, 92vw);
  max-height: 90vh;
  overflow: auto;
  border-radius: 13px;
  background: #f3f5f7;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.25);
}

.prediction-modal > .modal-close {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 5;
  width: 29px;
  height: 29px;
  border: 1px solid #d7dfe5;
  border-radius: 7px;
  background: #fff;
  color: #5f6d78;
  font-size: 18px;
}

.prediction-modal .page-heading {
  padding: 16px 18px 0;
}

.boot-screen {
  width: 100vw;
  height: 100vh;
  display: grid;
  place-items: center;
  background: #eef2f5;
}

.boot-card {
  text-align: center;
}

.boot-card .brand-mark {
  margin: 0 auto 9px;
}

.boot-card h1 {
  margin: 0;
  font-size: 22px;
}

.boot-card p {
  margin-top: 5px;
  color: #83909b;
  font-size: 10px;
}

@media (max-width: 1280px) {
  .header {
    grid-template-columns: 205px 1fr auto;
  }

  .dashboard {
    padding-left: 12px;
    padding-right: 12px;
  }

  .metrics {
    gap: 7px;
  }

  .metric {
    padding: 9px 10px;
  }
}
'''

write(FRONTEND / "App.jsx", APP)
write(FRONTEND / "App.css", CSS)


# ---------------------------------------------------------------------------
# Fix LivePrediction stale V2 text and risk vocabulary
# ---------------------------------------------------------------------------

live = FRONTEND / "components/LivePrediction.jsx"

if live.exists():
    text = live.read_text(encoding="utf-8")
    backup(live)

    text = text.replace(
        "failure_30d_v2_logistic",
        "failure_30d_v3_logistic",
    )

    text = text.replace(
        'label: "Moderate"',
        'label: "Medium"',
    )

    live.write_text(text, encoding="utf-8")

    print("[PASS] LivePrediction aligned to V3 vocabulary")


# ---------------------------------------------------------------------------
# Compile / build
# ---------------------------------------------------------------------------

run([
    "python3",
    "-m",
    "py_compile",
    str(ROOT / "scripts/run_phase9.py"),
])

build = run(
    ["npm", "--prefix", "frontend", "run", "build"],
    check=False,
)

if build.returncode != 0:
    fail("Frontend production build failed")


# ---------------------------------------------------------------------------
# Backend regression tests
# ---------------------------------------------------------------------------

tests = run(
    ["python3", "-m", "pytest", "-q", "tests"],
    check=False,
)

if tests.returncode != 0:
    fail("Backend tests failed")


# ---------------------------------------------------------------------------
# Static checks
# ---------------------------------------------------------------------------

app_text = (FRONTEND / "App.jsx").read_text(encoding="utf-8")
live_text = (FRONTEND / "components/LivePrediction.jsx").read_text(
    encoding="utf-8"
)

frontend_text = app_text + "\n" + live_text

required_endpoints = [
    "/health",
    "/system/status",
    "/planning/summary",
    "/planning/metrics",
    "/planning/plan",
    "/assets/risk/top",
    "/audit/events",
    "/planning/tasks/",
    "/risk/predict",
]

for required in required_endpoints:
    if required not in frontend_text:
        fail(f"Dashboard missing API integration: {required}")

if "const API = " not in frontend_text:
    fail("Dashboard API base URL is missing")

if "/api/v1" not in frontend_text:
    fail("Dashboard API base path is missing")

if "96.4%" in app_text or "98%" in app_text:
    fail("Detected hard-coded dashboard KPI values")

if "18.5 hrs" in app_text or "32" in app_text and "Optimized Blocks" in app_text:
    fail("Detected screenshot-style dummy KPI content")

print("[PASS] Dashboard API wiring")
print("[PASS] No screenshot KPI dummy data detected")

# Ensure sidebar has actually been removed.
if "sidebar" in app_text.lower():
    fail("Legacy sidebar remains in App.jsx")

print("[PASS] Unnecessary sidebar removed")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

report = {
    "phase": "9",
    "status": "PASS",
    "timestamp": datetime.now().astimezone().isoformat(),
    "purpose": "single-screen operational dashboard",
    "real_backend_data": True,
    "dummy_kpis": False,
    "sidebar_removed": True,
    "desktop_vertical_scroll": False,
    "risk_api": True,
    "planning_api": True,
    "asset_detail_api": True,
    "decision_api": True,
    "audit_api": True,
    "live_prediction_modal": True,
    "model_version": "failure_30d_v3_logistic",
    "planner_version": "maintenance_plan_v2",
    "human_review_required": True,
    "autonomous_railway_control": False,
    "backup": str(BACKUP.relative_to(ROOT)),
    "frontend_build": "PASS",
    "pytest": "PASS",
}

REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8",
)

print("\n" + "=" * 80)
print("PHASE 9 COMPLETE")
print("=" * 80)
print(json.dumps(report, indent=2))
print("=" * 80)
