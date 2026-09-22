import { useEffect, useMemo, useState } from "react";
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
