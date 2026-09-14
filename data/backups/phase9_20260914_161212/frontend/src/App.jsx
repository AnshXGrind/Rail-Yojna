import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import "./App.css";
import LivePrediction from "./components/LivePrediction";
import PlanningDashboard from "./components/PlanningDashboard";

const API = "http://127.0.0.1:8000/api/v1";

function RiskBadge({ risk }) {
  const percent = risk * 100;

  let label = "Low";
  let className = "low";

  if (percent >= 50) {
    label = "Critical";
    className = "critical";
  } else if (percent >= 20) {
    label = "High";
    className = "high";
  } else if (percent >= 5) {
    label = "Moderate";
    className = "moderate";
  }

  return (
    <span className={`risk-badge ${className}`}>
      {percent.toFixed(2)}% · {label}
    </span>
  );
}

function PriorityBadge({ priority }) {
  return (
    <span className={`priority-badge ${priority}`}>
      {priority}
    </span>
  );
}

function StatCard({ label, value, meta }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {meta && <div className="stat-meta">{meta}</div>}
    </div>
  );
}

function App() {
  const [view, setView] = useState("overview");
  const [summary, setSummary] = useState(null);
  const [assets, setAssets] = useState([]);
  const [plan, setPlan] = useState([]);

  const [selectedAssetId, setSelectedAssetId] = useState(null);
  const [selectedAsset, setSelectedAsset] = useState(null);
  const [assetLoading, setAssetLoading] = useState(false);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");

  const [search, setSearch] = useState("");
  const [priority, setPriority] = useState("ALL");
  const [riskFilter, setRiskFilter] = useState("ALL");
  const [sortField, setSortField] = useState("risk");
  const [sortDirection, setSortDirection] = useState("desc");

  async function loadDashboard(showSpinner = true) {
    try {
      if (showSpinner) {
        setLoading(true);
      } else {
        setRefreshing(true);
      }

      setError("");

      const [health, summaryResponse, assetsResponse, planResponse] =
        await Promise.all([
          axios.get(`${API}/health`),
          axios.get(`${API}/planning/summary`),
          axios.get(`${API}/assets/risk/top?limit=100`),
          axios.get(`${API}/planning/plan?limit=500`),
        ]);

      setConnected(health.data.status === "ok");
      setSummary(summaryResponse.data);
      setAssets(assetsResponse.data.items);
      setPlan(planResponse.data.items);
    } catch (err) {
      console.error(err);
      setConnected(false);
      setError(
        "Rail-Yojna backend is unavailable. Start FastAPI on port 8000."
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    loadDashboard();
  }, []);

  async function openAsset(assetId) {
    try {
      setSelectedAssetId(assetId);
      setAssetLoading(true);
      setSelectedAsset(null);
      setView("asset");
      setError("");

      const response = await axios.get(
        `${API}/assets/${assetId}/risk`
      );

      setSelectedAsset(response.data);
    } catch (err) {
      console.error(err);
      setError(`Unable to load asset ${assetId}.`);
    } finally {
      setAssetLoading(false);
    }
  }

  function changeSort(field) {
    if (sortField === field) {
      setSortDirection((current) =>
        current === "asc" ? "desc" : "asc"
      );
      return;
    }

    setSortField(field);
    setSortDirection("desc");
  }

  const filteredPlan = useMemo(() => {
    let result = [...plan];

    if (priority !== "ALL") {
      result = result.filter(
        (task) => task.priority === priority
      );
    }

    if (riskFilter !== "ALL") {
      result = result.filter((task) => {
        const risk = task.calibrated_risk;

        if (riskFilter === "CRITICAL") return risk >= 0.5;
        if (riskFilter === "HIGH") return risk >= 0.2 && risk < 0.5;
        if (riskFilter === "MODERATE") return risk >= 0.05 && risk < 0.2;
        if (riskFilter === "LOW") return risk < 0.05;

        return true;
      });
    }

    if (search.trim()) {
      const term = search.toLowerCase().trim();

      result = result.filter((task) =>
        [
          task.task_id,
          task.asset_id,
          task.task_type,
          task.section_id,
          task.track_id,
        ]
          .filter(Boolean)
          .some((value) =>
            String(value).toLowerCase().includes(term)
          )
      );
    }

    result.sort((a, b) => {
      let av;
      let bv;

      if (sortField === "risk") {
        av = a.calibrated_risk;
        bv = b.calibrated_risk;
      } else if (sortField === "criticality") {
        av = a.criticality;
        bv = b.criticality;
      } else if (sortField === "duration") {
        av = a.estimated_duration_minutes;
        bv = b.estimated_duration_minutes;
      } else {
        av = a.task_id;
        bv = b.task_id;
      }

      if (av < bv) return sortDirection === "asc" ? -1 : 1;
      if (av > bv) return sortDirection === "asc" ? 1 : -1;
      return 0;
    });

    return result;
  }, [
    plan,
    priority,
    riskFilter,
    search,
    sortField,
    sortDirection,
  ]);

  const filteredAssets = useMemo(() => {
    const result = [...assets];

    if (!search.trim()) {
      return result;
    }

    const term = search.toLowerCase().trim();

    return result.filter((asset) =>
      asset.asset_id.toLowerCase().includes(term)
    );
  }, [assets, search]);

  const assetTasks = useMemo(() => {
    if (!selectedAssetId) return [];

    return plan
      .filter((task) => task.asset_id === selectedAssetId)
      .sort(
        (a, b) => b.calibrated_risk - a.calibrated_risk
      );
  }, [plan, selectedAssetId]);

  const criticalCount = useMemo(
    () => assets.filter((asset) => asset.risk >= 0.5).length,
    [assets]
  );

  const highCount = useMemo(
    () =>
      assets.filter(
        (asset) => asset.risk >= 0.2 && asset.risk < 0.5
      ).length,
    [assets]
  );

  const selectedPercentage = summary
    ? (
        (summary.selected_tasks / summary.candidate_tasks) *
        100
      ).toFixed(1)
    : "0";

  function renderOverview() {
    return (
      <>
        <div className="page-heading">
          <div>
            <div className="eyebrow">Operations overview</div>
            <h2>Maintenance intelligence</h2>
            <p>
              Risk-ranked assets and the current maintenance
              selection produced by Rail-Yojna V1.
            </p>
          </div>

          <button
            className="secondary-button"
            onClick={() => loadDashboard(false)}
            disabled={refreshing}
          >
            {refreshing ? "Refreshing…" : "Refresh data"}
          </button>
        </div>

        <section className="stats-grid">
          <StatCard
            label="Candidate tasks"
            value={summary?.candidate_tasks.toLocaleString() ?? "—"}
            meta="2026 planning horizon"
          />

          <StatCard
            label="Selected tasks"
            value={summary?.selected_tasks.toLocaleString() ?? "—"}
            meta={`${selectedPercentage}% of candidate tasks`}
          />

          <StatCard
            label="Maintenance hours"
            value={summary?.selected_hours.toFixed(1) ?? "—"}
            meta="Estimated selected workload"
          />

          <StatCard
            label="Aggregate risk mass"
            value={summary?.risk_mass.toFixed(2) ?? "—"}
            meta="Selected maintenance risk"
          />
        </section>

        <section className="content-grid">
          <div className="panel">
            <div className="panel-title-row">
              <div>
                <h3>Priority risk assets</h3>
                <p>Highest calibrated 30-day failure probabilities.</p>
              </div>

              <button
                className="ghost-button"
                onClick={() => setView("assets")}
              >
                View all
              </button>
            </div>

            <div className="risk-summary">
              <div className="risk-summary-card critical">
                <span>Critical</span>
                <strong>{criticalCount}</strong>
                <small>≥ 50%</small>
              </div>

              <div className="risk-summary-card high">
                <span>High</span>
                <strong>{highCount}</strong>
                <small>20–49.99%</small>
              </div>

              <div className="risk-summary-card total">
                <span>Ranked assets</span>
                <strong>{assets.length}</strong>
                <small>Top risk list</small>
              </div>
            </div>

            <div className="asset-list">
              {assets.slice(0, 10).map((asset) => (
                <button
                  className="asset-row"
                  key={asset.asset_id}
                  onClick={() => openAsset(asset.asset_id)}
                >
                  <div className="asset-row-main">
                    <div className="asset-code">
                      {asset.asset_id}
                    </div>
                    <div className="asset-condition">
                      Condition {asset.condition_score.toFixed(2)}
                    </div>
                  </div>

                  <div className="asset-risk-bar">
                    <div
                      className="asset-risk-fill"
                      style={{
                        width: `${Math.min(
                          asset.risk * 100,
                          100
                        )}%`,
                      }}
                    />
                  </div>

                  <div className="asset-row-risk">
                    {(asset.risk * 100).toFixed(2)}%
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-title-row">
              <div>
                <h3>Planning decision</h3>
                <p>Current V1 selection state.</p>
              </div>
            </div>

            <div className="decision-card">
              <div className="decision-number">
                {summary?.selected_tasks.toLocaleString() ?? "—"}
              </div>
              <div className="decision-label">
                maintenance tasks selected
              </div>

              <div className="decision-progress">
                <div
                  style={{
                    width: `${Math.min(
                      Number(selectedPercentage),
                      100
                    )}%`,
                  }}
                />
              </div>

              <div className="decision-row">
                <span>Selected</span>
                <strong>{selectedPercentage}%</strong>
              </div>

              <div className="decision-row">
                <span>Deferred</span>
                <strong>
                  {summary?.deferred_tasks.toLocaleString() ?? "—"}
                </strong>
              </div>

              <div className="decision-row">
                <span>Workload</span>
                <strong>
                  {summary
                    ? `${summary.selected_hours.toFixed(1)} h`
                    : "—"}
                </strong>
              </div>
            </div>

            <div className="methodology-note">
              <div className="note-title">
                Decision model
              </div>
              <p>
                V1 combines calibrated failure risk, maintenance
                criticality and assigned maintenance priority under
                an explicit planning-capacity constraint.
              </p>
            </div>
          </div>
        </section>
      </>
    );
  }

  function renderAssets() {
    return (
      <>
        <div className="page-heading">
          <div>
            <div className="eyebrow">Risk intelligence</div>
            <h2>High-risk assets</h2>
            <p>
              Ranked asset condition and predicted 30-day failure
              probability.
            </p>
          </div>
        </div>

        <div className="toolbar">
          <div className="search-wrap">
            <span>⌕</span>
            <input
              value={search}
              onChange={(event) =>
                setSearch(event.target.value)
              }
              placeholder="Search asset ID"
            />
          </div>

          <button
            className="secondary-button"
            onClick={() => setSearch("")}
          >
            Clear
          </button>
        </div>

        <div className="panel table-panel">
          <table>
            <thead>
              <tr>
                <th>Asset</th>
                <th>Risk</th>
                <th>Risk level</th>
                <th>Condition</th>
                <th>Degradation</th>
                <th />
              </tr>
            </thead>

            <tbody>
              {filteredAssets.map((asset) => (
                <tr key={asset.asset_id}>
                  <td>
                    <button
                      className="link-button"
                      onClick={() => openAsset(asset.asset_id)}
                    >
                      {asset.asset_id}
                    </button>
                  </td>

                  <td className="number-cell">
                    {(asset.risk * 100).toFixed(2)}%
                  </td>

                  <td>
                    <RiskBadge risk={asset.risk} />
                  </td>

                  <td className="number-cell">
                    {asset.condition_score.toFixed(2)}
                  </td>

                  <td className="number-cell">
                    {asset.degradation_rate.toFixed(4)}
                  </td>

                  <td>
                    <button
                      className="row-action"
                      onClick={() =>
                        openAsset(asset.asset_id)
                      }
                    >
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {filteredAssets.length === 0 && (
            <div className="empty-state">
              No assets match the current search.
            </div>
          )}
        </div>
      </>
    );
  }

  function renderPlan() {
    return (
      <>
        <div className="page-heading">
          <div>
            <div className="eyebrow">Planning engine</div>
            <h2>Maintenance plan</h2>
            <p>
              Recommended maintenance tasks selected by Rail-Yojna
              V1.
            </p>
          </div>
        </div>

        <div className="toolbar plan-toolbar">
          <div className="search-wrap">
            <span>⌕</span>
            <input
              value={search}
              onChange={(event) =>
                setSearch(event.target.value)
              }
              placeholder="Search task, asset, section or type"
            />
          </div>

          <select
            value={priority}
            onChange={(event) =>
              setPriority(event.target.value)
            }
          >
            <option value="ALL">All priorities</option>
            <option value="P1">P1</option>
            <option value="P2">P2</option>
            <option value="P3">P3</option>
            <option value="P4">P4</option>
          </select>

          <select
            value={riskFilter}
            onChange={(event) =>
              setRiskFilter(event.target.value)
            }
          >
            <option value="ALL">All risk levels</option>
            <option value="CRITICAL">Critical</option>
            <option value="HIGH">High</option>
            <option value="MODERATE">Moderate</option>
            <option value="LOW">Low</option>
          </select>

          <button
            className="secondary-button"
            onClick={() => {
              setSearch("");
              setPriority("ALL");
              setRiskFilter("ALL");
            }}
          >
            Reset
          </button>
        </div>

        <div className="plan-summary-strip">
          <div>
            <span>Visible tasks</span>
            <strong>{filteredPlan.length}</strong>
          </div>

          <div>
            <span>P1 tasks</span>
            <strong>
              {
                filteredPlan.filter(
                  (task) => task.priority === "P1"
                ).length
              }
            </strong>
          </div>

          <div>
            <span>Critical risk</span>
            <strong>
              {
                filteredPlan.filter(
                  (task) => task.calibrated_risk >= 0.5
                ).length
              }
            </strong>
          </div>

          <div>
            <span>Maintenance hours</span>
            <strong>
              {(
                filteredPlan.reduce(
                  (sum, task) =>
                    sum + task.estimated_duration_minutes,
                  0
                ) / 60
              ).toFixed(1)}
            </strong>
          </div>
        </div>

        <div className="panel table-panel">
          <table>
            <thead>
              <tr>
                <th>Task</th>
                <th>Asset</th>

                <th
                  className="sortable"
                  onClick={() => changeSort("risk")}
                >
                  Risk
                  {sortField === "risk" &&
                    (sortDirection === "desc" ? " ↓" : " ↑")}
                </th>

                <th>Priority</th>

                <th
                  className="sortable"
                  onClick={() =>
                    changeSort("criticality")
                  }
                >
                  Criticality
                  {sortField === "criticality" &&
                    (sortDirection === "desc" ? " ↓" : " ↑")}
                </th>

                <th
                  className="sortable"
                  onClick={() =>
                    changeSort("duration")
                  }
                >
                  Duration
                  {sortField === "duration" &&
                    (sortDirection === "desc" ? " ↓" : " ↑")}
                </th>

                <th>Planned date</th>
              </tr>
            </thead>

            <tbody>
              {filteredPlan.map((task) => (
                <tr key={task.task_id}>
                  <td>
                    <div className="task-main">
                      <strong>{task.task_id}</strong>
                      <span>{task.task_type}</span>
                    </div>
                  </td>

                  <td>
                    <button
                      className="link-button"
                      onClick={() =>
                        openAsset(task.asset_id)
                      }
                    >
                      {task.asset_id}
                    </button>
                  </td>

                  <td>
                    <RiskBadge
                      risk={task.calibrated_risk}
                    />
                  </td>

                  <td>
                    <PriorityBadge
                      priority={task.priority}
                    />
                  </td>

                  <td className="number-cell">
                    {task.criticality.toFixed(3)}
                  </td>

                  <td className="number-cell">
                    {task.estimated_duration_minutes} min
                  </td>

                  <td>
                    {new Date(
                      task.planned_date
                    ).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {filteredPlan.length === 0 && (
            <div className="empty-state">
              No maintenance tasks match the current filters.
            </div>
          )}
        </div>
      </>
    );
  }

  function renderAsset() {
    return (
      <>
        <div className="page-heading">
          <div>
            <button
              className="back-link"
              onClick={() => setView("assets")}
            >
              ← Back to risk assets
            </button>

            <div className="eyebrow">
              Asset assessment
            </div>

            <h2>{selectedAssetId}</h2>

            <p>
              Current calibrated risk state and associated
              maintenance recommendations.
            </p>
          </div>
        </div>

        {assetLoading || !selectedAsset ? (
          <div className="panel">
            <div className="empty-state">
              Loading asset assessment…
            </div>
          </div>
        ) : (
          <>
            <section className="asset-hero-grid">
              <div className="asset-risk-hero">
                <div className="hero-label">
                  30-day predicted failure risk
                </div>

                <div className="hero-risk">
                  {(selectedAsset.risk * 100).toFixed(2)}%
                </div>

                <RiskBadge risk={selectedAsset.risk} />

                <div className="hero-footnote">
                  Calibrated model output · synthetic dataset
                </div>
              </div>

              <div className="panel metrics-panel">
                <div className="metric-item">
                  <span>Condition score</span>
                  <strong>
                    {selectedAsset.condition_score.toFixed(
                      2
                    )}
                  </strong>
                </div>

                <div className="metric-item">
                  <span>Degradation rate</span>
                  <strong>
                    {selectedAsset.degradation_rate.toFixed(
                      4
                    )}
                  </strong>
                </div>

                <div className="metric-item">
                  <span>Prediction horizon</span>
                  <strong>30 days</strong>
                </div>

                <div className="metric-item">
                  <span>Data mode</span>
                  <strong>synthetic</strong>
                </div>
              </div>
            </section>

            <section className="panel table-panel">
              <div className="panel-title-row">
                <div>
                  <h3>Associated maintenance</h3>
                  <p>
                    Selected V1 tasks connected to this asset.
                  </p>
                </div>
              </div>

              {assetTasks.length === 0 ? (
                <div className="empty-state">
                  No selected maintenance task is currently
                  associated with this asset in the loaded plan.
                </div>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>Task</th>
                      <th>Type</th>
                      <th>Risk</th>
                      <th>Priority</th>
                      <th>Criticality</th>
                      <th>Duration</th>
                      <th>Block</th>
                    </tr>
                  </thead>

                  <tbody>
                    {assetTasks.map((task) => (
                      <tr key={task.task_id}>
                        <td>{task.task_id}</td>
                        <td>{task.task_type}</td>
                        <td>
                          <RiskBadge
                            risk={task.calibrated_risk}
                          />
                        </td>
                        <td>
                          <PriorityBadge
                            priority={task.priority}
                          />
                        </td>
                        <td>
                          {task.criticality.toFixed(3)}
                        </td>
                        <td>
                          {task.estimated_duration_minutes} min
                        </td>
                        <td>
                          {task.block_required
                            ? "Required"
                            : "Not required"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </>
        )}
      </>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">RY</div>
          <div>
            <div className="brand-name">Rail-Yojna</div>
            <div className="brand-subtitle">
              Maintenance intelligence
            </div>
          </div>
        </div>

        <div className="sidebar-section">
          <div className="sidebar-label">Workspace</div>

          <button
            className={`nav-item ${
              view === "overview" ? "active" : ""
            }`}
            onClick={() => setView("overview")}
          >
            <span>▦</span>
            Overview
          </button>

          <button
            className={`nav-item ${
              view === "assets" || view === "asset"
                ? "active"
                : ""
            }`}
            onClick={() => setView("assets")}
          >
            <span>◉</span>
            Risk assets
          </button>

          <button
            className={`nav-item ${
              view === "plan" ? "active" : ""
            }`}
            onClick={() => setView("plan")}
          >
            <span>≡</span>
            Maintenance plan
          </button>

          <button
            className={`nav-item ${
              view === "predict" ? "active" : ""
            }`}
            onClick={() => setView("predict")}
          >
            <span>+</span>
            Live prediction
          </button>
        </div>

        <div className="sidebar-bottom">
          <div className="connection-card">
            <div
              className={`connection-dot ${
                connected ? "connected" : ""
              }`}
            />
            <div>
              <strong>
                {connected ? "Backend connected" : "Backend offline"}
              </strong>
              <span>
                {connected
                  ? "FastAPI · localhost:8000"
                  : "Start FastAPI to continue"}
              </span>
            </div>
          </div>

          <div className="synthetic-badge">
            Synthetic planning environment
          </div>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <div>
            <span className="topbar-title">
              India-focused railway maintenance
            </span>
          </div>

          <div className="topbar-right">
            <span className="status-pill">
              Decision support
            </span>

            <button
              className="icon-button"
              title="Refresh"
              onClick={() => loadDashboard(false)}
            >
              ↻
            </button>
          </div>
        </header>

        {error && (
          <div className="error-banner">
            <strong>Connection issue</strong>
            <span>{error}</span>
          </div>
        )}

        <main className="content">
          {loading ? (
            <div className="loading-screen">
              <div className="loading-spinner" />
              <h3>Loading Rail-Yojna</h3>
              <p>
                Reading the risk state and maintenance plan.
              </p>
            </div>
          ) : (
            <>
              {view === "overview" && renderOverview()}
              {view === "assets" && renderAssets()}
              {view === "plan" && renderPlan()}
              {view === "asset" && renderAsset()}
              {view === "predict" && <LivePrediction onAssetOpen={openAsset} />}
            </>
          )}
          <PlanningDashboard />
      </main>
      </div>
    </div>
  );
}

export default App;
