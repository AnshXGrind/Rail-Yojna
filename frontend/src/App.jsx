import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import LivePrediction from "./components/LivePrediction";
import BlockPlanningModal from "./components/BlockPlanningModal";
import Reports from "./pages/Reports";
import Service from "./pages/Service";
import "./App.css";

const API = "http://127.0.0.1:8000/api/v1";

const TASK_PAGE_OPTIONS = [25, 50, 100, 250, 500, 1000, 1500];
const ASSET_PAGE_OPTIONS = [25, 50, 100];

function getRoute() {
  const hash = window.location.hash || "#/control";
  const match = hash.match(/^#\/([^\/]+)(?:\/(.*))?$/);
  return {
    page: match?.[1] || "control",
    id: match?.[2] || "",
  };
}

function navigate(page, id = "") {
  window.location.hash = id
    ? `#/${page}/${encodeURIComponent(id)}`
    : `#/${page}`;
}

async function loadLiveReports(setter) {
  try {
    const response = await axios.get(
      `${API}/reports?limit=20`,
    );

    setter(response.data || []);
  } catch {
    // Report service may be temporarily unavailable.
    // The main dashboard continues to operate normally.
  }
}

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
  const [route, setRoute] = useState(() => getRoute());
  const [liveReports, setLiveReports] = useState([]);
  const [reportsOpen, setReportsOpen] = useState(false);
  const [seenReportIds, setSeenReportIds] = useState(() => {
    try {
      return JSON.parse(
        localStorage.getItem("rail-yojna-seen-reports") || "[]",
      );
    } catch {
      return [];
    }
  });

  useEffect(() => {
    const handleHashChange = () => setRoute(getRoute());
    window.addEventListener("hashchange", handleHashChange);

    if (!window.location.hash) {
      navigate("control");
    }

    return () => {
      window.removeEventListener("hashchange", handleHashChange);
    };
  }, []);

  useEffect(() => {
    loadLiveReports(setLiveReports);

    const source = new EventSource(
      `${API}/events/stream`,
    );

    source.addEventListener("rail_yojna", (event) => {
      try {
        const message = JSON.parse(event.data);

        if (
          message.type === "REPORT_CREATED" ||
          message.type === "REPORT_STATUS_CHANGED"
        ) {
          loadLiveReports(setLiveReports);
        }
      } catch {
        // Keep the dashboard alive if an event is malformed.
      }
    });

    return () => {
      source.close();
    };
  }, []);
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
  const [blockPlanningOpen, setBlockPlanningOpen] = useState(false);

  const [decisionBusy, setDecisionBusy] = useState(false);
  const [decisionMessage, setDecisionMessage] = useState("");
  const [decisionActor, setDecisionActor] = useState("planner");
  const [decisionNote, setDecisionNote] = useState("");

  const unreadReports = liveReports.filter(
    (report) => !seenReportIds.includes(report.report_id),
  );

  function openReport(report) {
    const nextSeen = Array.from(
      new Set([...seenReportIds, report.report_id]),
    );

    setSeenReportIds(nextSeen);

    localStorage.setItem(
      "rail-yojna-seen-reports",
      JSON.stringify(nextSeen),
    );

    setReportsOpen(false);

    if (report?.asset_id) {
      navigate("service", report.asset_id);
    } else {
      navigate("reports");
    }
  }

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

      const plannerEvents = (
        auditResponse.data.items || []
      ).filter((event) =>
        [
          "PLANNING_APPROVED",
          "PLANNING_MODIFIED",
          "PLANNING_REJECTED",
        ].includes(event.event_type)
      );

      setAudit(plannerEvents);

      const initialAsset = nextAssets[0] || null;

      const initialTask =
        nextPlan.find(
          (task) =>
            initialAsset &&
            task.asset_id === initialAsset.asset_id
        ) ||
        nextPlan[0] ||
        null;

      setSelectedTask((current) => {
        if (!current) return initialTask;

        return (
          nextPlan.find(
            (task) =>
              task.task_id === current.task_id
          ) ||
          nextPlan.find(
            (task) =>
              initialAsset &&
              task.asset_id === initialAsset.asset_id
          ) ||
          initialTask
        );
      });

      setSelectedAsset((current) => {
        if (!current) return initialAsset;

        return (
          nextAssets.find(
            (asset) =>
              asset.asset_id === current.asset_id
          ) || initialAsset || current
        );
      });

      if (!selectedAsset && initialAsset?.asset_id) {
        try {
          const detail = await axios.get(
            `${API}/assets/${encodeURIComponent(
              initialAsset.asset_id
            )}/risk`
          );

          setSelectedAsset(detail.data);
        } catch {
          // Watchlist remains usable without detail loading.
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

      navigate("service", assetId);

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
          <img
            className="boot-logo"
            src="/assets/rail-yojna-logo.png"
            alt="रेल-योजना"
          />
          <p>Maintenance decision support</p>
          <span>Connecting to live data…</span>
        </div>
      </div>
    );
  }

  if (route.page === "reports") {
    return (
      <div className="app">
        <header className="header">
          <div className="brand">
            <img
              className="brand-logo"
              src="/assets/rail-yojna-logo.png"
              alt="रेल-योजना"
            />
          </div>

          <div className="header-center">
            <div className="header-title-row">
              <div>
                <strong>Field Problem Reports</strong>
                <span>Capture and route field observations</span>
              </div>

              <nav className="top-nav" aria-label="Primary">
                <button
                  className="nav-tab"
                  onClick={() => navigate("control")}
                >
                  Control Room
                </button>
                <button className="nav-tab active">
                  Reports
                </button>
                <button
                  className="nav-tab"
                  onClick={() => navigate("service")}
                >
                  Service
                </button>
              </nav>
            </div>
          </div>

          <div className="header-actions">
            <button
              className={`live-reports-button ${
                unreadReports.length ? "has-new" : ""
              }`}
              onClick={() =>
                setReportsOpen((value) => !value)
              }
            >
              <span className="live-reports-icon">●</span>
              Live Reports
              {unreadReports.length > 0 && (
                <b>{unreadReports.length}</b>
              )}
            </button>

            <span className="connection online">
              <i />
              Live
            </span>
          </div>
        </header>

        {reportsOpen && (
          <div
            className="live-reports-popover"
            onMouseDown={(event) => {
                if (event.target === event.currentTarget) {
                  setReportsOpen(false);
                }
            }}
          >
            <div className="live-reports-panel">
                <div className="live-reports-header">
                  <div>
                    <span className="section-kicker">LIVE FEED</span>
                    <h3>Incoming reports</h3>
                  </div>

                  <button
                    className="modal-close"
                    onClick={() => setReportsOpen(false)}
                  >
                    ×
                  </button>
                </div>

                <div className="live-reports-list">
                  {liveReports.length === 0 ? (
                    <div className="empty">
                        No reports received yet.
                    </div>
                  ) : (
                    liveReports.slice(0, 12).map((report) => {
                        const unread = !seenReportIds.includes(
                          report.report_id,
                        );

                        return (
                          <button
                            key={report.report_id}
                            className={`live-report-row ${
                                unread ? "unread" : ""
                            }`}
                            onClick={() => openReport(report)}
                          >
                            <span className="live-report-dot" />

                            <span className="live-report-main">
                                <strong>{report.report_id}</strong>
                                <span>
                                  {report.problem_type} · {report.asset_id}
                                </span>
                                <small>
                                  {new Date(
                                    report.created_at,
                                  ).toLocaleString()}
                                </small>
                            </span>

                            <span
                                className={`report-severity ${String(
                                  report.severity || "",
                                ).toLowerCase()}`}
                            >
                                {report.severity}
                            </span>
                          </button>
                        );
                    })
                  )}
                </div>

                <div className="live-reports-footer">
                  <button
                    className="button secondary"
                    onClick={() => {
                        setReportsOpen(false);
                        navigate("reports");
                    }}
                  >
                    Open Reports
                  </button>
                </div>
            </div>
          </div>
        )}

        <Reports
          onServiceOpen={(assetId) => navigate("service", assetId)}
        />
      </div>
    );
  }

  if (route.page === "service") {
    return (
      <div className="app">
        <header className="header">
          <div className="brand">
            <img
              className="brand-logo"
              src="/assets/rail-yojna-logo.png"
              alt="रेल-योजना"
            />
          </div>

          <div className="header-center">
            <div className="header-title-row">
              <div>
                <strong>Asset Service</strong>
                <span>Live asset state and maintenance context</span>
              </div>

              <nav className="top-nav" aria-label="Primary">
                <button
                  className="nav-tab"
                  onClick={() => navigate("control")}
                >
                  Control Room
                </button>
                <button
                  className="nav-tab"
                  onClick={() => navigate("reports")}
                >
                  Reports
                </button>
                <button className="nav-tab active">
                  Service
                </button>
              </nav>
            </div>
          </div>

          <div className="header-actions">
            <button
              className={`live-reports-button ${
                unreadReports.length ? "has-new" : ""
              }`}
              onClick={() =>
                setReportsOpen((value) => !value)
              }
            >
              <span className="live-reports-icon">●</span>
              Live Reports
              {unreadReports.length > 0 && (
                <b>{unreadReports.length}</b>
              )}
            </button>

            <span className="connection online">
              <i />
              Live
            </span>
          </div>
        </header>

        {reportsOpen && (
          <div
            className="live-reports-popover"
            onMouseDown={(event) => {
                if (event.target === event.currentTarget) {
                  setReportsOpen(false);
                }
            }}
          >
            <div className="live-reports-panel">
                <div className="live-reports-header">
                  <div>
                    <span className="section-kicker">LIVE FEED</span>
                    <h3>Incoming reports</h3>
                  </div>

                  <button
                    className="modal-close"
                    onClick={() => setReportsOpen(false)}
                  >
                    ×
                  </button>
                </div>

                <div className="live-reports-list">
                  {liveReports.length === 0 ? (
                    <div className="empty">
                        No reports received yet.
                    </div>
                  ) : (
                    liveReports.slice(0, 12).map((report) => {
                        const unread = !seenReportIds.includes(
                          report.report_id,
                        );

                        return (
                          <button
                            key={report.report_id}
                            className={`live-report-row ${
                                unread ? "unread" : ""
                            }`}
                            onClick={() => openReport(report)}
                          >
                            <span className="live-report-dot" />

                            <span className="live-report-main">
                                <strong>{report.report_id}</strong>
                                <span>
                                  {report.problem_type} · {report.asset_id}
                                </span>
                                <small>
                                  {new Date(
                                    report.created_at,
                                  ).toLocaleString()}
                                </small>
                            </span>

                            <span
                                className={`report-severity ${String(
                                  report.severity || "",
                                ).toLowerCase()}`}
                            >
                                {report.severity}
                            </span>
                          </button>
                        );
                    })
                  )}
                </div>

                <div className="live-reports-footer">
                  <button
                    className="button secondary"
                    onClick={() => {
                        setReportsOpen(false);
                        navigate("reports");
                    }}
                  >
                    Open Reports
                  </button>
                </div>
            </div>
          </div>
        )}

        <Service
          assetId={route.id}
          onControlOpen={() => navigate("control")}
        />
      </div>
    );
  }

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <img
            className="brand-logo"
            src="/assets/rail-yojna-logo.png"
            alt="रेल-योजना"
          />
        </div>

        <div className="header-center">
          <div className="header-title-row">
            <div>
              <strong>
                {route.page === "reports"
                  ? "Field Problem Reports"
                  : route.page === "service"
                    ? "Asset Service"
                    : "Maintenance Operations"}
              </strong>
              <span>
                {route.page === "reports"
                  ? "Capture and route field observations"
                  : route.page === "service"
                    ? "Live asset state and maintenance context"
                    : "Risk, maintenance priority and human review"}
              </span>
            </div>

            <nav className="top-nav" aria-label="Primary">
              <button
                className={`nav-tab ${route.page === "control" ? "active" : ""}`}
                onClick={() => navigate("control")}
              >
                Control Room
              </button>
              <button
                className={`nav-tab ${route.page === "reports" ? "active" : ""}`}
                onClick={() => navigate("reports")}
              >
                Reports
              </button>
              <button
                className={`nav-tab ${route.page === "service" ? "active" : ""}`}
                onClick={() => navigate("service", route.id)}
              >
                Service
              </button>
            </nav>
          </div>
        </div>

        <div className="header-actions">
          <button
            className={`live-reports-button ${
              unreadReports.length ? "has-new" : ""
            }`}
            onClick={() =>
              setReportsOpen((value) => !value)
            }
          >
            <span className="live-reports-icon">●</span>
            Live Reports
            {unreadReports.length > 0 && (
              <b>{unreadReports.length}</b>
            )}
          </button>

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
            className="button block-primary"
            onClick={() => setBlockPlanningOpen(true)}
          >
            Block Planning
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

      {reportsOpen && (
        <div
          className="live-reports-popover"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setReportsOpen(false);
            }
          }}
        >
          <div className="live-reports-panel">
            <div className="live-reports-header">
              <div>
                <span className="section-kicker">LIVE FEED</span>
                <h3>Incoming reports</h3>
              </div>

              <button
                className="modal-close"
                onClick={() => setReportsOpen(false)}
              >
                ×
              </button>
            </div>

            <div className="live-reports-list">
              {liveReports.length === 0 ? (
                <div className="empty">
                  No reports received yet.
                </div>
              ) : (
                liveReports.slice(0, 12).map((report) => {
                  const unread = !seenReportIds.includes(
                    report.report_id,
                  );

                  return (
                    <button
                      key={report.report_id}
                      className={`live-report-row ${
                        unread ? "unread" : ""
                      }`}
                      onClick={() => openReport(report)}
                    >
                      <span className="live-report-dot" />

                      <span className="live-report-main">
                        <strong>{report.report_id}</strong>
                        <span>
                          {report.problem_type} · {report.asset_id}
                        </span>
                        <small>
                          {new Date(
                            report.created_at,
                          ).toLocaleString()}
                        </small>
                      </span>

                      <span
                        className={`report-severity ${String(
                          report.severity || "",
                        ).toLowerCase()}`}
                      >
                        {report.severity}
                      </span>
                    </button>
                  );
                })
              )}
            </div>

            <div className="live-reports-footer">
              <button
                className="button secondary"
                onClick={() => {
                  setReportsOpen(false);
                  navigate("reports");
                }}
              >
                Open Reports
              </button>
            </div>
          </div>
        </div>
      )}

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

      {blockPlanningOpen && (
        <BlockPlanningModal
          onClose={() => setBlockPlanningOpen(false)}
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
