import { useEffect, useState } from "react";

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
