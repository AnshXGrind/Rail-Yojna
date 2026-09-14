import { useState } from "react";
import axios from "axios";

const API = "http://127.0.0.1:8000/api/v1";

const initialForm = {
  asset_id: "AST00015579",
  timestamp: "2025-12-31T23:59:59Z",
  condition_score: "14.697",
  degradation_rate: "1.541",
  measurement_value: "85.9196",
  inspection_quality: "0.9347",
  measurement_confidence: "0.8431",
};

function RiskBadge({ risk }) {
  const percent = risk * 100;

  let label = "Low";
  let cls = "low";

  if (percent >= 50) {
    label = "Critical";
    cls = "critical";
  } else if (percent >= 20) {
    label = "High";
    cls = "high";
  } else if (percent >= 5) {
    label = "Moderate";
    cls = "moderate";
  }

  return (
    <span className={`risk-badge ${cls}`}>
      {percent.toFixed(2)}% · {label}
    </span>
  );
}

export default function LivePrediction({ onAssetOpen }) {
  const [form, setForm] = useState(initialForm);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function updateField(name, value) {
    setForm((current) => ({
      ...current,
      [name]: value,
    }));
  }

  async function predict(event) {
    event.preventDefault();

    try {
      setLoading(true);
      setError("");
      setResult(null);

      const payload = {
        asset_id: form.asset_id.trim(),
        timestamp: form.timestamp,
        condition_score: Number(form.condition_score),
        degradation_rate: Number(form.degradation_rate),
        measurement_value: Number(form.measurement_value),
        inspection_quality: Number(form.inspection_quality),
        measurement_confidence: Number(form.measurement_confidence),
      };

      const response = await axios.post(
        `${API}/risk/predict`,
        payload
      );

      setResult(response.data);
    } catch (err) {
      console.error(err);

      const detail =
        err?.response?.data?.detail ||
        "Prediction request failed.";

      setError(String(detail));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ML inference</div>
          <h2>Live risk prediction</h2>
          <p>
            Submit a new asset observation to the validated V2
            failure-risk inference pipeline.
          </p>
        </div>
      </div>

      <div className="prediction-layout">
        <form
          className="panel prediction-form"
          onSubmit={predict}
        >
          <div className="panel-title-row">
            <div>
              <h3>Observation</h3>
              <p>
                These values are passed to the model through
                FastAPI.
              </p>
            </div>
          </div>

          <div className="form-grid">
            <label>
              <span>Asset ID</span>
              <input
                value={form.asset_id}
                onChange={(e) =>
                  updateField("asset_id", e.target.value)
                }
                required
              />
            </label>

            <label>
              <span>Observation timestamp</span>
              <input
                type="datetime-local"
                value={form.timestamp
                  .replace("Z", "")
                  .slice(0, 16)}
                onChange={(e) =>
                  updateField(
                    "timestamp",
                    `${e.target.value}:00Z`
                  )
                }
                required
              />
            </label>

            <label>
              <span>Condition score</span>
              <input
                type="number"
                step="any"
                value={form.condition_score}
                onChange={(e) =>
                  updateField(
                    "condition_score",
                    e.target.value
                  )
                }
                required
              />
            </label>

            <label>
              <span>Degradation rate</span>
              <input
                type="number"
                step="any"
                value={form.degradation_rate}
                onChange={(e) =>
                  updateField(
                    "degradation_rate",
                    e.target.value
                  )
                }
                required
              />
            </label>

            <label>
              <span>Measurement value</span>
              <input
                type="number"
                step="any"
                value={form.measurement_value}
                onChange={(e) =>
                  updateField(
                    "measurement_value",
                    e.target.value
                  )
                }
                required
              />
            </label>

            <label>
              <span>Inspection quality</span>
              <input
                type="number"
                min="0"
                step="any"
                value={form.inspection_quality}
                onChange={(e) =>
                  updateField(
                    "inspection_quality",
                    e.target.value
                  )
                }
                required
              />
            </label>

            <label>
              <span>Measurement confidence</span>
              <input
                type="number"
                min="0"
                max="1"
                step="any"
                value={form.measurement_confidence}
                onChange={(e) =>
                  updateField(
                    "measurement_confidence",
                    e.target.value
                  )
                }
                required
              />
            </label>
          </div>

          <div className="form-footer">
            <span>
              Model: failure_30d_v2_logistic
            </span>

            <button
              className="primary-button"
              type="submit"
              disabled={loading}
            >
              {loading
                ? "Running model…"
                : "Predict risk"}
            </button>
          </div>

          {error && (
            <div className="form-error">
              {error}
            </div>
          )}
        </form>

        <section className="panel prediction-result">
          <div className="panel-title-row">
            <div>
              <h3>Prediction result</h3>
              <p>Calculated by the backend model pipeline.</p>
            </div>
          </div>

          {!result && !loading && (
            <div className="empty-state">
              Submit an observation to calculate risk.
            </div>
          )}

          {loading && (
            <div className="prediction-loading">
              <div className="loading-spinner" />
              <span>
                Building historical features and running inference…
              </span>
            </div>
          )}

          {result && !loading && (
            <div className="result-body">
              <div className="result-risk">
                <span>30-day failure probability</span>

                <strong>
                  {(result.risk_probability * 100).toFixed(
                    2
                  )}
                  %
                </strong>

                <RiskBadge risk={result.risk_probability} />
              </div>

              <div className="result-grid">
                <div>
                  <span>Asset</span>
                  <strong>{result.asset_id}</strong>
                </div>

                <div>
                  <span>Raw probability</span>
                  <strong>
                    {result.raw_probability.toFixed(6)}
                  </strong>
                </div>

                <div>
                  <span>Risk horizon</span>
                  <strong>
                    {result.prediction_horizon_days} days
                  </strong>
                </div>

                <div>
                  <span>Calibration</span>
                  <strong>{result.calibration}</strong>
                </div>
              </div>

              <div className="result-note">
                <strong>Decision-support output</strong>
                <p>
                  This prediction is an ML estimate for the
                  supplied observation. It does not authorize
                  maintenance, blocks, signalling changes, or
                  train movements.
                </p>
              </div>

              {onAssetOpen && (
                <button
                  className="secondary-button"
                  onClick={() =>
                    onAssetOpen(result.asset_id)
                  }
                >
                  Open asset assessment
                </button>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
