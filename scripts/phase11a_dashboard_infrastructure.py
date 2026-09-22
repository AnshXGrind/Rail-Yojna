from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"
PAGES = SRC / "pages"

PAGES.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------
# Reports page
# ---------------------------------------------------------------------

(PAGES / "Reports.jsx").write_text(r'''import { useState } from "react";
import "../App.css";

const REPORT_TYPES = [
  "Rail defect",
  "Track geometry",
  "Sleeper",
  "Ballast",
  "Electrical",
  "Drainage",
  "Obstacle",
  "Weather damage",
  "Other",
];

export default function Reports({ onServiceOpen }) {
  const [assetId, setAssetId] = useState("");
  const [type, setType] = useState(REPORT_TYPES[0]);
  const [severity, setSeverity] = useState("Medium");
  const [description, setDescription] = useState("");
  const [message, setMessage] = useState("");

  function saveDraft(event) {
    event.preventDefault();

    const draft = {
      asset_id: assetId.trim(),
      type,
      severity,
      description: description.trim(),
      saved_at: new Date().toISOString(),
      status: "draft",
    };

    localStorage.setItem(
      "rail-yojna-report-draft",
      JSON.stringify(draft),
    );

    setMessage(
      "Report draft saved locally. Live report submission will be connected to the backend in the next infrastructure phase.",
    );
  }

  return (
    <main className="module-page">
      <section className="module-hero reports-hero">
        <div>
          <span className="section-kicker">FIELD REPORTING</span>
          <h1>Report a railway problem</h1>
          <p>
            Capture an issue from the field and link it to an asset.
            This phase establishes the reporting workflow without
            inventing backend records.
          </p>
        </div>

        <div className="module-status">
          <span className="module-status-dot draft" />
          Reporting backend: being integrated
        </div>
      </section>

      <section className="module-grid reports-grid">
        <article className="module-card">
          <div className="module-card-header">
            <div>
              <h2>New problem report</h2>
              <p>Prepare a report for backend submission.</p>
            </div>
          </div>

          <form className="report-form" onSubmit={saveDraft}>
            <label>
              <span>Asset ID</span>
              <input
                value={assetId}
                onChange={(e) => setAssetId(e.target.value)}
                placeholder="AST00000000"
              />
            </label>

            <div className="form-two">
              <label>
                <span>Problem type</span>
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value)}
                >
                  {REPORT_TYPES.map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
              </label>

              <label>
                <span>Severity</span>
                <select
                  value={severity}
                  onChange={(e) => setSeverity(e.target.value)}
                >
                  <option>Low</option>
                  <option>Medium</option>
                  <option>High</option>
                  <option>Critical</option>
                </select>
              </label>
            </div>

            <label>
              <span>Description</span>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe what was observed..."
                rows={7}
              />
            </label>

            <div className="module-actions">
              <button className="button primary" type="submit">
                Save draft
              </button>

              {assetId.trim() && (
                <button
                  className="button secondary"
                  type="button"
                  onClick={() => onServiceOpen(assetId.trim())}
                >
                  Open asset service
                </button>
              )}
            </div>

            {message && <div className="module-message">{message}</div>}
          </form>
        </article>

        <article className="module-card report-flow-card">
          <div className="module-card-header">
            <div>
              <h2>Reporting lifecycle</h2>
              <p>The intended live workflow.</p>
            </div>
          </div>

          <div className="workflow">
            <div><b>01</b><span>Report observed problem</span></div>
            <div><b>02</b><span>Link report to asset</span></div>
            <div><b>03</b><span>Verify and triage</span></div>
            <div><b>04</b><span>Update risk / planning</span></div>
            <div><b>05</b><span>Create maintenance work</span></div>
            <div><b>06</b><span>Close with evidence</span></div>
          </div>

          <div className="module-note">
            No fake report count or status metrics are displayed yet.
            Once report APIs exist, this panel will become live.
          </div>
        </article>
      </section>
    </main>
  );
}
''', encoding="utf-8")

# ---------------------------------------------------------------------
# Service page
# ---------------------------------------------------------------------

(PAGES / "Service.jsx").write_text(r'''import { useEffect, useMemo, useState } from "react";
import axios from "axios";

const API = "http://127.0.0.1:8000/api/v1";

function riskBand(value) {
  const risk = Number(value || 0);
  if (risk >= 0.5) return { label: "Critical", cls: "critical" };
  if (risk >= 0.2) return { label: "High", cls: "high" };
  if (risk >= 0.05) return { label: "Medium", cls: "medium" };
  return { label: "Low", cls: "low" };
}

function RiskChip({ value }) {
  const band = riskBand(value);
  return (
    <span className={`risk-chip ${band.cls}`}>
      {(Number(value || 0) * 100).toFixed(3)}% · {band.label}
    </span>
  );
}

export default function Service({ assetId, onControlOpen }) {
  const [search, setSearch] = useState(assetId || "");
  const [currentId, setCurrentId] = useState(assetId || "");
  const [asset, setAsset] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (assetId) {
      setSearch(assetId);
      loadAsset(assetId);
    }
  }, [assetId]);

  async function loadAsset(id) {
    if (!id.trim()) return;

    try {
      setLoading(true);
      setError("");

      const [assetResponse, planResponse] = await Promise.all([
        axios.get(
          `${API}/assets/${encodeURIComponent(id.trim())}/risk`,
        ),
        axios.get(`${API}/planning/plan?limit=1500`),
      ]);

      setCurrentId(id.trim());
      setAsset(assetResponse.data);

      const allTasks = planResponse.data.items || [];
      setTasks(
        allTasks
          .filter((task) => task.asset_id === id.trim())
          .sort(
            (a, b) =>
              Number(b.calibrated_risk || 0) -
              Number(a.calibrated_risk || 0),
          ),
      );
    } catch (err) {
      console.error(err);
      setAsset(null);
      setTasks([]);
      setError(
        err?.response?.data?.detail ||
          `Unable to load asset ${id.trim()}.`,
      );
    } finally {
      setLoading(false);
    }
  }

  const primaryTask = useMemo(() => tasks[0] || null, [tasks]);

  return (
    <main className="module-page service-page">
      <section className="module-hero service-hero">
        <div>
          <span className="section-kicker">ASSET SERVICE</span>
          <h1>Asset service record</h1>
          <p>
            One place for the current asset state and its maintenance
            context.
          </p>
        </div>

        <div className="service-search">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") loadAsset(search);
            }}
            placeholder="Search asset ID"
          />
          <button
            className="button primary"
            onClick={() => loadAsset(search)}
            disabled={loading}
          >
            {loading ? "Loading…" : "Open"}
          </button>
        </div>
      </section>

      {error && (
        <div className="service-error">
          <strong>Asset lookup failed</strong>
          <span>{error}</span>
        </div>
      )}

      {!asset ? (
        <section className="module-card service-empty">
          <h2>{currentId ? "Asset unavailable" : "Search an asset"}</h2>
          <p>
            Enter a real asset ID from the Control Room risk watchlist.
            No placeholder asset data is shown.
          </p>
        </section>
      ) : (
        <>
          <section className="service-overview">
            <article className="service-identity module-card">
              <span className="section-kicker">ASSET</span>
              <h2>{asset.asset_id}</h2>
              <p>
                {asset.asset_type ||
                  asset.asset_name ||
                  "Railway infrastructure asset"}
              </p>

              <div className="service-risk">
                <RiskChip value={asset.risk} />
              </div>
            </article>

            <article className="module-card service-stat">
              <span>Condition</span>
              <strong>
                {asset.condition_score != null
                  ? Number(asset.condition_score).toFixed(1)
                  : "—"}
              </strong>
            </article>

            <article className="module-card service-stat">
              <span>Criticality</span>
              <strong>
                {asset.criticality != null
                  ? Number(asset.criticality).toFixed(2)
                  : "—"}
              </strong>
            </article>

            <article className="module-card service-stat">
              <span>Risk probability</span>
              <strong>
                {(Number(asset.risk || 0) * 100).toFixed(3)}%
              </strong>
            </article>
          </section>

          <section className="service-grid">
            <article className="module-card">
              <div className="module-card-header">
                <div>
                  <h2>Maintenance context</h2>
                  <p>Selected recommendations linked to this asset.</p>
                </div>

                {primaryTask && (
                  <button
                    className="button secondary"
                    onClick={onControlOpen}
                  >
                    Open Control Room
                  </button>
                )}
              </div>

              {tasks.length === 0 ? (
                <div className="service-empty compact">
                  No selected maintenance task is currently linked to
                  this asset.
                </div>
              ) : (
                <div className="service-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Task</th>
                        <th>Type</th>
                        <th>Risk</th>
                        <th>Priority</th>
                        <th>Block</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tasks.slice(0, 10).map((task) => (
                        <tr key={task.task_id}>
                          <td><strong>{task.task_id}</strong></td>
                          <td>{task.task_type}</td>
                          <td>
                            <RiskChip value={task.calibrated_risk} />
                          </td>
                          <td>{task.priority}</td>
                          <td>
                            {task.block_required ? "Required" : "No"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </article>

            <article className="module-card">
              <div className="module-card-header">
                <div>
                  <h2>Service timeline</h2>
                  <p>Reserved for live inspection, defect and maintenance history.</p>
                </div>
              </div>

              <div className="timeline-placeholder">
                <div className="timeline-node">
                  <span />
                  <div>
                    <strong>Current asset state</strong>
                    <small>Live risk record loaded from backend</small>
                  </div>
                </div>

                <div className="timeline-node muted-node">
                  <span />
                  <div>
                    <strong>Inspection history</strong>
                    <small>Will connect to operational inspection records</small>
                  </div>
                </div>

                <div className="timeline-node muted-node">
                  <span />
                  <div>
                    <strong>Defect / report history</strong>
                    <small>Will connect to the Reports service</small>
                  </div>
                </div>

                <div className="timeline-node muted-node">
                  <span />
                  <div>
                    <strong>Maintenance history</strong>
                    <small>Will connect to completed work records</small>
                  </div>
                </div>
              </div>
            </article>
          </section>
        </>
      )}
    </main>
  );
}
''', encoding="utf-8")

# ---------------------------------------------------------------------
# Patch App.jsx
# ---------------------------------------------------------------------

app_path = SRC / "App.jsx"
app = app_path.read_text(encoding="utf-8")

app = app.replace(
    'import LivePrediction from "./components/LivePrediction";',
    'import LivePrediction from "./components/LivePrediction";\n'
    'import Reports from "./pages/Reports";\n'
    'import Service from "./pages/Service";'
)

# Add route state after API constants.
needle = 'const ASSET_PAGE_OPTIONS = [25, 50, 100];\n'
insert = '''const ASSET_PAGE_OPTIONS = [25, 50, 100];

function getRoute() {
  const hash = window.location.hash || "#/control";
  const match = hash.match(/^#\\/([^\\/]+)(?:\\/(.*))?$/);
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
'''
if needle in app and "function getRoute()" not in app:
    app = app.replace(needle, insert)

# Add route state.
needle = 'export default function App() {\n'
insert = '''export default function App() {
  const [route, setRoute] = useState(() => getRoute());

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
'''
if needle in app and 'const [route, setRoute]' not in app:
    app = app.replace(needle, insert, 1)

# Insert navigation into header center.
old = '''        <div className="header-center">
          <strong>Maintenance Operations</strong>
          <span>
            Risk, maintenance priority and human review
          </span>
        </div>
'''
new = '''        <div className="header-center">
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
'''
if old in app:
    app = app.replace(old, new, 1)

# Add early route-specific rendering before existing dashboard return.
marker = '  return (\n    <div className="app">\n'
replacement = '''  if (route.page === "reports") {
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
            <span className="connection online">
              <i />
              Live
            </span>
          </div>
        </header>

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
            <span className="connection online">
              <i />
              Live
            </span>
          </div>
        </header>

        <Service
          assetId={route.id}
          onControlOpen={() => navigate("control")}
        />
      </div>
    );
  }

  return (
    <div className="app">
'''
if marker in app:
    app = app.replace(marker, replacement, 1)

# Existing control header navigation needs to be clickable to other pages.
old = '''        <div className="header-center">
          <strong>Maintenance Operations</strong>
          <span>
            Risk, maintenance priority and human review
          </span>
        </div>
'''
new = '''        <div className="header-center">
          <div className="header-title-row">
            <div>
              <strong>Maintenance Operations</strong>
              <span>Risk, maintenance priority and human review</span>
            </div>

            <nav className="top-nav" aria-label="Primary">
              <button className="nav-tab active">
                Control Room
              </button>
              <button
                className="nav-tab"
                onClick={() => navigate("reports")}
              >
                Reports
              </button>
              <button
                className="nav-tab"
                onClick={() =>
                  navigate("service", selectedAsset?.asset_id || "")
                }
              >
                Service
              </button>
            </nav>
          </div>
        </div>
'''
# Only replace the remaining control header occurrence.
if old in app:
    app = app.replace(old, new, 1)

# Make asset click open Service as well as select it.
old = '''      setSelectedAsset(response.data);

      const relatedTask = plan
'''
new = '''      setSelectedAsset(response.data);

      navigate("service", assetId);

      const relatedTask = plan
'''
if old in app:
    app = app.replace(old, new, 1)

app_path.write_text(app, encoding="utf-8")

# ---------------------------------------------------------------------
# Add infrastructure CSS
# ---------------------------------------------------------------------

css_path = SRC / "App.css"
css = css_path.read_text(encoding="utf-8")

css += r'''

/* ================================================================
   PHASE 11A — SHARED DASHBOARD INFRASTRUCTURE
   ================================================================ */

.header-title-row {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.top-nav {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.nav-tab {
  height: 30px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: #6f7d87;
  font-size: 9px;
  font-weight: 750;
}

.nav-tab:hover {
  background: #f1f5f8;
  color: #294b67;
}

.nav-tab.active {
  border-color: #d5e3ed;
  background: #edf5fb;
  color: #17365d;
}

.module-page {
  height: calc(100vh - 66px);
  padding: 16px 18px;
  overflow: auto;
  background: #eef2f5;
}

.module-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 18px;
  border: 1px solid #dce4e8;
  border-radius: 12px;
  background: #fff;
}

.module-hero h1 {
  margin: 4px 0 0;
  color: #17365d;
  font-size: 23px;
  letter-spacing: -0.4px;
}

.module-hero p {
  max-width: 720px;
  margin: 6px 0 0;
  color: #778691;
  font-size: 10px;
  line-height: 1.55;
}

.module-status {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 10px;
  border: 1px solid #e1e7eb;
  border-radius: 999px;
  background: #f8fafb;
  color: #74818b;
  font-size: 8px;
  white-space: nowrap;
}

.module-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #e8922f;
}

.module-status-dot.draft {
  background: #e8922f;
}

.module-grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: 1.25fr .75fr;
  gap: 12px;
}

.module-card {
  min-width: 0;
  border: 1px solid #dce4e8;
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
}

.module-card-header {
  min-height: 58px;
  padding: 11px 13px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid #edf0f2;
}

.module-card-header h2 {
  margin: 0;
  color: #21394b;
  font-size: 13px;
}

.module-card-header p {
  margin: 3px 0 0;
  color: #8a969f;
  font-size: 8px;
}

.report-form {
  padding: 15px;
  display: grid;
  gap: 11px;
}

.report-form label > span,
.service-search label > span {
  display: block;
  margin-bottom: 4px;
  color: #74828c;
  font-size: 8px;
  font-weight: 750;
}

.report-form input,
.report-form select,
.report-form textarea,
.service-search input {
  width: 100%;
  border: 1px solid #d6e0e5;
  border-radius: 7px;
  background: #fff;
  color: #293c49;
  font-size: 9px;
  outline: none;
}

.report-form input,
.report-form select,
.service-search input {
  height: 34px;
  padding: 0 9px;
}

.report-form textarea {
  min-height: 130px;
  padding: 8px 9px;
  resize: vertical;
}

.report-form input:focus,
.report-form select:focus,
.report-form textarea:focus,
.service-search input:focus {
  border-color: #5c82a7;
  box-shadow: 0 0 0 2px rgba(92, 130, 167, .10);
}

.form-two {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.module-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.module-message {
  padding: 9px 10px;
  border-left: 3px solid #2da56b;
  background: #f0f8f3;
  color: #4c6e5a;
  font-size: 8px;
  line-height: 1.5;
}

.workflow {
  padding: 14px;
  display: grid;
  gap: 8px;
}

.workflow > div {
  display: grid;
  grid-template-columns: 31px 1fr;
  gap: 9px;
  align-items: center;
  min-height: 42px;
  padding: 7px 9px;
  border: 1px solid #e6ecef;
  border-radius: 8px;
  background: #fbfcfd;
}

.workflow b {
  color: #2f7dc5;
  font-size: 8px;
}

.workflow span {
  color: #53636f;
  font-size: 9px;
}

.module-note {
  margin: 0 14px 14px;
  padding: 10px;
  border-radius: 8px;
  background: #fff8ed;
  border: 1px solid #f1dfbf;
  color: #806a49;
  font-size: 8px;
  line-height: 1.5;
}

.service-search {
  display: flex;
  align-items: center;
  gap: 7px;
  width: min(390px, 100%);
}

.service-search input {
  min-width: 0;
}

.service-error {
  margin-top: 10px;
  padding: 10px 12px;
  display: flex;
  gap: 7px;
  border: 1px solid #ebc5c5;
  border-radius: 8px;
  background: #fff5f5;
  color: #813c3c;
  font-size: 8px;
}

.service-empty {
  margin-top: 12px;
  padding: 40px 20px;
  text-align: center;
  color: #8c99a2;
}

.service-empty h2 {
  margin: 0;
  color: #425563;
  font-size: 15px;
}

.service-empty p {
  max-width: 520px;
  margin: 7px auto 0;
  font-size: 9px;
  line-height: 1.5;
}

.service-overview {
  margin-top: 12px;
  display: grid;
  grid-template-columns: 2fr repeat(3, 1fr);
  gap: 10px;
}

.service-identity {
  padding: 14px;
}

.service-identity h2 {
  margin: 4px 0 0;
  color: #17365d;
  font-size: 20px;
}

.service-identity p {
  margin: 4px 0 0;
  color: #8a969f;
  font-size: 8px;
}

.service-risk {
  margin-top: 12px;
}

.service-stat {
  min-height: 92px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.service-stat span {
  color: #7f8c95;
  font-size: 8px;
  text-transform: uppercase;
  letter-spacing: .05em;
}

.service-stat strong {
  margin-top: 4px;
  color: #253946;
  font-size: 21px;
}

.service-grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: 1.3fr .7fr;
  gap: 12px;
}

.service-table-wrap {
  max-height: 320px;
  overflow: auto;
}

.service-table-wrap table {
  width: 100%;
  border-collapse: collapse;
  font-size: 8px;
}

.service-table-wrap th,
.service-table-wrap td {
  padding: 8px 10px;
  border-bottom: 1px solid #edf0f2;
  text-align: left;
  white-space: nowrap;
}

.service-table-wrap th {
  position: sticky;
  top: 0;
  background: #f7fafb;
  color: #7d8993;
}

.timeline-placeholder {
  padding: 14px;
}

.timeline-node {
  position: relative;
  display: grid;
  grid-template-columns: 15px 1fr;
  gap: 9px;
  min-height: 56px;
}

.timeline-node:not(:last-child)::after {
  content: "";
  position: absolute;
  top: 12px;
  left: 6px;
  bottom: 0;
  width: 1px;
  background: #d9e2e7;
}

.timeline-node > span {
  width: 13px;
  height: 13px;
  margin-top: 2px;
  border: 3px solid #e5f0f7;
  border-radius: 50%;
  background: #2f7dc5;
  z-index: 1;
}

.timeline-node strong,
.timeline-node small {
  display: block;
}

.timeline-node strong {
  color: #465965;
  font-size: 9px;
}

.timeline-node small {
  margin-top: 3px;
  color: #96a1a8;
  font-size: 7px;
}

.muted-node > span {
  background: #b6c1c8;
  border-color: #eef1f3;
}

@media (max-width: 1350px) {
  .header-title-row {
    gap: 10px;
  }

  .top-nav {
    gap: 2px;
  }

  .nav-tab {
    padding: 0 7px;
  }

  .module-grid,
  .service-grid {
    grid-template-columns: 1fr;
  }

  .service-overview {
    grid-template-columns: 2fr repeat(3, 1fr);
  }
}

@media (max-width: 1120px) {
  .header-title-row > div:first-child {
    display: none;
  }

  .service-overview {
    grid-template-columns: 1fr 1fr;
  }

  .service-search {
    width: 320px;
  }
}
'''

css_path.write_text(css, encoding="utf-8")

print("Phase 11A infrastructure created.")
print("Created:")
print(" - frontend/src/pages/Reports.jsx")
print(" - frontend/src/pages/Service.jsx")
print(" - updated frontend/src/App.jsx")
print(" - updated frontend/src/App.css")
