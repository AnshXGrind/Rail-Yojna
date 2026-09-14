import { useEffect, useMemo, useState } from "react";
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
        axios.get(`${API}/planning/plan?limit=100`),
        axios.get(`${API}/audit/events?limit=12`),
      ]);

      if (healthResponse.data.status !== "ok") {
        throw new Error("Backend health check failed");
      }

      setSystem(systemResponse.data);
      const nextAssets = assetResponse.data.items || [];
      const nextPlan = planResponse.data.items || [];

      setSummary(summaryResponse.data);
      setMetrics(metricsResponse.data);
      setAssets(nextAssets);
      setPlan(nextPlan);
      setAudit(auditResponse.data.items || []);

      setSelectedTask((current) => {
        if (current) return current;
        return nextPlan[0] || null;
      });

      setSelectedAsset((current) => {
        if (!current) return null;

        return (
          nextAssets.find(
            (item) => item.asset_id === current.asset_id
          ) || current
        );
      });

      if (!selectedAsset && nextAssets[0]?.asset_id) {
        try {
          const detail = await axios.get(
            `${API}/assets/${encodeURIComponent(nextAssets[0].asset_id)}/risk`
          );
          setSelectedAsset(detail.data);
        } catch {
          // The watchlist remains usable even when detail loading fails.
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
        .filter((task) => task.asset_id === assetId)
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
          actor: decisionActor.trim(),
          note: decisionNote.trim(),
        }
      );

      setDecisionMessage(
        `${decision.toUpperCase()} recorded for ${task.task_id}`
      );

      setDecisionNote("");
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

                <div className="decision-form">
                  <label>
                    <span>Reviewer</span>
                    <input
                      value={decisionActor}
                      onChange={(event) =>
                        setDecisionActor(event.target.value)
                      }
                      placeholder="Planner name"
                    />
                  </label>

                  <label>
                    <span>Decision note</span>
                    <textarea
                      value={decisionNote}
                      onChange={(event) =>
                        setDecisionNote(event.target.value)
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
