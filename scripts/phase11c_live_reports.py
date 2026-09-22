from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"

APP = SRC / "App.jsx"
REPORTS = SRC / "pages" / "Reports.jsx"
CSS = SRC / "App.css"

# -------------------------------------------------------------------
# Reports.jsx -> real backend submission
# -------------------------------------------------------------------

reports = REPORTS.read_text(encoding="utf-8")

reports = reports.replace(
'''import { useState } from "react";
import "../App.css";

const REPORT_TYPES = [
''',
'''import { useState } from "react";
import axios from "axios";
import "../App.css";

const API = "http://127.0.0.1:8000/api/v1";

const REPORT_TYPES = [
''',
)

start = reports.index("export default function Reports")
new_reports = r'''export default function Reports({ onServiceOpen }) {
  const [assetId, setAssetId] = useState("");
  const [reporter, setReporter] = useState("");
  const [type, setType] = useState(REPORT_TYPES[0]);
  const [severity, setSeverity] = useState("Medium");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [createdReport, setCreatedReport] = useState(null);

  async function submitReport(event) {
    event.preventDefault();

    if (!assetId.trim() || !reporter.trim() || !description.trim()) {
      setMessage(
        "Asset ID, reporter and description are required.",
      );
      return;
    }

    try {
      setSaving(true);
      setMessage("");

      const response = await axios.post(
        `${API}/reports`,
        {
          asset_id: assetId.trim(),
          reporter: reporter.trim(),
          problem_type: type,
          severity,
          description: description.trim(),
        },
      );

      setCreatedReport(response.data);
      setMessage(
        `Report ${response.data.report_id} created successfully.`,
      );

      setDescription("");
    } catch (error) {
      setMessage(
        error?.response?.data?.detail ||
          "Report could not be submitted.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="module-page">
      <section className="module-hero reports-hero">
        <div>
          <span className="section-kicker">FIELD REPORTING</span>
          <h1>Report a railway problem</h1>
          <p>
            Capture an issue from the field and link it to an asset.
            Submitted reports become visible to the operations team.
          </p>
        </div>

        <div className="module-status">
          <span className="module-status-dot draft" />
          Live report service
        </div>
      </section>

      <section className="module-grid reports-grid">
        <article className="module-card">
          <div className="module-card-header">
            <div>
              <h2>New problem report</h2>
              <p>Create a real report in the Rail-Yojna backend.</p>
            </div>
          </div>

          <form className="report-form" onSubmit={submitReport}>
            <div className="form-two">
              <label>
                <span>Asset ID</span>
                <input
                  value={assetId}
                  onChange={(e) => setAssetId(e.target.value)}
                  placeholder="AST00000000"
                />
              </label>

              <label>
                <span>Reporter</span>
                <input
                  value={reporter}
                  onChange={(e) => setReporter(e.target.value)}
                  placeholder="Operator / inspector"
                />
              </label>
            </div>

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
              <button
                className="button primary"
                type="submit"
                disabled={saving}
              >
                {saving ? "Submitting…" : "Submit report"}
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

            {message && (
              <div className="module-message">
                {message}
              </div>
            )}

            {createdReport && (
              <div className="created-report">
                <div>
                  <span>Report ID</span>
                  <strong>{createdReport.report_id}</strong>
                </div>

                <div>
                  <span>Status</span>
                  <strong>{createdReport.status}</strong>
                </div>

                <div>
                  <span>Created</span>
                  <strong>
                    {new Date(
                      createdReport.created_at,
                    ).toLocaleString()}
                  </strong>
                </div>
              </div>
            )}
          </form>
        </article>

        <article className="module-card report-flow-card">
          <div className="module-card-header">
            <div>
              <h2>Reporting lifecycle</h2>
              <p>Every report moves through an explicit status.</p>
            </div>
          </div>

          <div className="workflow">
            <div><b>01</b><span>NEW</span></div>
            <div><b>02</b><span>TRIAGED</span></div>
            <div><b>03</b><span>VERIFIED</span></div>
            <div><b>04</b><span>ASSIGNED</span></div>
            <div><b>05</b><span>IN PROGRESS</span></div>
            <div><b>06</b><span>RESOLVED / CLOSED</span></div>
          </div>

          <div className="module-note">
            A submitted report is linked to its asset and is immediately
            available to the live report notification center.
          </div>
        </article>
      </section>
    </main>
  );
}
'''

reports = reports[:start] + new_reports
REPORTS.write_text(reports, encoding="utf-8")

# -------------------------------------------------------------------
# App.jsx -> live reports state + notification center
# -------------------------------------------------------------------

app = APP.read_text(encoding="utf-8")

# Add report state after route state.
anchor = '  const [route, setRoute] = useState(() => getRoute());\n'
if anchor in app and "liveReports" not in app:
    app = app.replace(
        anchor,
        anchor
        + '''  const [liveReports, setLiveReports] = useState([]);
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
''',
        1,
    )

# Add report loader after navigate helper.
marker = "function navigate(page, id = \"\") {"
pos = app.find(marker)
if pos != -1:
    end = app.find("}\n", pos) + 2

    if "async function loadLiveReports" not in app:
        helper = r'''
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
'''
        app = app[:end] + helper + app[end:]

# Add polling effect.
anchor = '''  useEffect(() => {
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
if anchor in app and "loadLiveReports(setLiveReports)" not in app:
    addition = '''
  useEffect(() => {
    loadLiveReports(setLiveReports);

    const interval = window.setInterval(() => {
      loadLiveReports(setLiveReports);
    }, 5000);

    return () => window.clearInterval(interval);
  }, []);
'''
    app = app.replace(anchor, anchor + addition, 1)

# Add notification helpers before loading dashboard.
marker = "  async function loadDashboard(initial = false) {"
if marker in app and "const unreadReports" not in app:
    helpers = r'''  const unreadReports = liveReports.filter(
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

'''
    app = app.replace(marker, helpers + marker, 1)

# Put notification button into CONTROL header actions.
old = '''          <span
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
'''
new = '''          <button
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
'''
if old in app:
    app = app.replace(old, new, 1)

# Do the same in Reports route header.
old = '''          <div className="header-actions">
            <span className="connection online">
              <i />
              Live
            </span>
          </div>
'''
new = '''          <div className="header-actions">
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
'''
# replace first two report/service header occurrences carefully
app = app.replace(old, new, 1)
app = app.replace(old, new, 1)

# Insert popup before error banner in each returned layout by defining one component-like JSX
popup = r'''
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
'''

# Place popup after <div className="app"> in every app return,
# but avoid duplication by inserting before error banners / page main.
app = app.replace(
    '\n      {error && (\n',
    popup + '\n      {error && (\n',
)

# Reports/Service don't have error marker. Add popup before <Reports
app = app.replace(
    '\n        <Reports\n',
    popup.replace("      ", "        ")
    + '\n        <Reports\n',
    1,
)

app = app.replace(
    '\n        <Service\n',
    popup.replace("      ", "        ")
    + '\n        <Service\n',
    1,
)

APP.write_text(app, encoding="utf-8")

# -------------------------------------------------------------------
# CSS
# -------------------------------------------------------------------

css = CSS.read_text(encoding="utf-8")

css += r'''

/* ================================================================
   PHASE 11C — LIVE REPORT NOTIFICATIONS
   ================================================================ */

.live-reports-button {
  height: 31px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 9px;
  border: 1px solid #dce3e8;
  border-radius: 7px;
  background: #fff;
  color: #51616c;
  font-size: 8px;
  font-weight: 800;
}

.live-reports-button:hover {
  background: #f3f7fa;
  border-color: #cbd9e2;
}

.live-reports-button.has-new {
  border-color: #f0c88d;
  background: #fff8ed;
  color: #8c5f1f;
}

.live-reports-button b {
  min-width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: #dc5a54;
  color: #fff;
  font-size: 7px;
}

.live-reports-icon {
  color: #e8922f;
  font-size: 8px;
}

.live-reports-popover {
  position: fixed;
  inset: 66px 0 0;
  z-index: 90;
  pointer-events: none;
}

.live-reports-panel {
  pointer-events: auto;
  position: absolute;
  top: 8px;
  right: 18px;
  width: min(440px, calc(100vw - 36px));
  max-height: 620px;
  display: grid;
  grid-template-rows: 62px minmax(0, 1fr) 48px;
  overflow: hidden;
  border: 1px solid #d4dfe6;
  border-radius: 11px;
  background: #f8fafb;
  box-shadow: 0 22px 60px rgba(0, 0, 0, .18);
}

.live-reports-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 13px;
  border-bottom: 1px solid #e2e9ed;
  background: #fff;
}

.live-reports-header h3 {
  margin: 2px 0 0;
  color: #17365d;
  font-size: 15px;
}

.live-reports-list {
  min-height: 0;
  overflow: auto;
  background: #fff;
}

.live-report-row {
  width: 100%;
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  padding: 10px 12px;
  border: 0;
  border-bottom: 1px solid #edf0f2;
  background: #fff;
  text-align: left;
}

.live-report-row:hover {
  background: #f5f9fb;
}

.live-report-row.unread {
  background: #fffaf1;
}

.live-report-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #aeb8bf;
}

.live-report-row.unread .live-report-dot {
  background: #e8922f;
  box-shadow: 0 0 0 4px #fff0d8;
}

.live-report-main {
  min-width: 0;
}

.live-report-main strong,
.live-report-main span,
.live-report-main small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.live-report-main strong {
  color: #314957;
  font-size: 9px;
}

.live-report-main span {
  margin-top: 2px;
  color: #6f7e89;
  font-size: 8px;
}

.live-report-main small {
  margin-top: 2px;
  color: #9aa5ad;
  font-size: 6px;
}

.report-severity {
  padding: 4px 6px;
  border-radius: 999px;
  font-size: 6px;
  font-weight: 850;
}

.report-severity.low {
  background: #e7f5ec;
  color: #24764c;
}

.report-severity.medium {
  background: #fff4d5;
  color: #977118;
}

.report-severity.high {
  background: #ffead9;
  color: #aa5923;
}

.report-severity.critical {
  background: #fde3e3;
  color: #a83f3f;
}

.live-reports-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 8px 10px;
  border-top: 1px solid #e2e9ed;
  background: #f8fafb;
}

.created-report {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.created-report > div {
  padding: 8px;
  border: 1px solid #e2e9ed;
  border-radius: 7px;
  background: #f8fafb;
}

.created-report span,
.created-report strong {
  display: block;
}

.created-report span {
  color: #85929b;
  font-size: 7px;
}

.created-report strong {
  margin-top: 3px;
  color: #334b5a;
  font-size: 8px;
}
'''

CSS.write_text(css, encoding="utf-8")

print("Phase 11C live report integration patched.")
print("Reports now submit to backend.")
print("Top-bar Live Reports notification center added.")
print("Live feed refreshes every 5 seconds.")
