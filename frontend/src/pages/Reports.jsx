import { useState } from "react";
import axios from "axios";
import "../App.css";

const API = "http://127.0.0.1:8000/api/v1";

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
