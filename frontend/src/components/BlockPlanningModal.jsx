import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  MapContainer,
  TileLayer,
  LayersControl,
  useMap,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";

const API = "http://127.0.0.1:8000/api/v1";
const INDIA = [22.9734, 78.6569];

function FitIndia() {
  const map = useMap();

  useEffect(() => {
    map.setView(INDIA, 5);
  }, [map]);

  return null;
}

function Risk({ value }) {
  const risk = Number(value || 0);

  let label = "Low";
  let cls = "low";

  if (risk >= 0.5) {
    label = "Critical";
    cls = "critical";
  } else if (risk >= 0.2) {
    label = "High";
    cls = "high";
  } else if (risk >= 0.05) {
    label = "Medium";
    cls = "medium";
  }

  return (
    <span className={`risk-chip ${cls}`}>
      {(risk * 100).toFixed(2)}% · {label}
    </span>
  );
}

function hours(value) {
  return (Number(value || 0) / 60).toFixed(1);
}

function dateTime(value) {
  if (!value) return "—";

  return new Date(value).toLocaleString([], {
    dateStyle: "short",
    timeStyle: "short",
  });
}

export default function BlockPlanningModal({ onClose }) {
  const [plan, setPlan] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [candidateSummary, setCandidateSummary] = useState(null);

  const [date, setDate] = useState("");
  const [section, setSection] = useState("");
  const [track, setTrack] = useState("");

  const [selectedCandidate, setSelectedCandidate] = useState(null);

  const [loading, setLoading] = useState(true);
  const [candidateLoading, setCandidateLoading] = useState(false);
  const [error, setError] = useState("");
  const [decisionState, setDecisionState] = useState("DRAFT");
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [decisionNote, setDecisionNote] = useState("");
  const [blockAssessment, setBlockAssessment] = useState(null);
  const [assessmentLoading, setAssessmentLoading] = useState(false);

  const [operationalAssessment, setOperationalAssessment] = useState(null);
  const [operationalLoading, setOperationalLoading] = useState(false);

  async function loadPlan(selectedDate = "") {
    try {
      setLoading(true);
      setError("");

      const params = selectedDate
        ? { planned_date: selectedDate, limit: 1000 }
        : { limit: 1000 };

      const response = await axios.get(
        `${API}/planning/blocks`,
        { params },
      );

      setPlan(response.data);
    } catch (err) {
      console.error(err);

      setError(
        err?.response?.data?.detail ||
          "Planning data could not be loaded.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function loadCandidates({
    plannedDate = date,
    sectionId = section,
    trackId = track,
  } = {}) {
    try {
      setCandidateLoading(true);
      setError("");

      const params = {
        limit: 50,
      };

      if (plannedDate) {
        params.planned_date = plannedDate;
      }

      if (sectionId) {
        params.section_id = sectionId;
      }

      if (trackId) {
        params.track_id = trackId;
      }

      const response = await axios.get(
        `${API}/planning/blocks/candidates`,
        { params },
      );

      setCandidates(response.data?.items || []);
      setCandidateSummary(response.data?.summary || null);

      setSelectedCandidate(null);
      setOperationalAssessment(null);
      setBlockAssessment(null);
      setDecisionState("DRAFT");
    } catch (err) {
      console.error(err);

      setError(
        err?.response?.data?.detail ||
          "Block candidates could not be generated.",
      );

      setCandidates([]);
      setCandidateSummary(null);
    } finally {
      setCandidateLoading(false);
    }
  }

  useEffect(() => {
    loadPlan();
    loadCandidates({
      plannedDate: "",
      sectionId: "",
      trackId: "",
    });
  }, []);

  const allItems = plan?.items || [];

  const sections = useMemo(
    () =>
      [...new Set(
        allItems
          .map((item) => item.section_id)
          .filter(Boolean),
      )].sort(),
    [allItems],
  );

  const tracks = useMemo(
    () =>
      [...new Set(
        allItems
          .filter((item) =>
            section
              ? item.section_id === section
              : true,
          )
          .map((item) => item.track_id)
          .filter(Boolean),
      )].sort(),
    [allItems, section],
  );

  const feasibleCandidates = useMemo(
    () =>
      candidates.filter(
        (candidate) => candidate.feasible,
      ),
    [candidates],
  );

  const topCandidates = useMemo(
    () =>
      [...feasibleCandidates].sort(
        (a, b) =>
          Number(b.score || 0) -
          Number(a.score || 0),
      ),
    [feasibleCandidates],
  );

  async function refresh() {
    await Promise.all([
      loadPlan(date),
      loadCandidates({
        plannedDate: date,
        sectionId: section,
        trackId: track,
      }),
    ]);
  }

  async function loadOperationalAssessment(candidate) {
    if (!candidate?.block_id) {
      setOperationalAssessment(null);
      return;
    }

    try {
      setOperationalLoading(true);
      setError("");

      const params = candidate.planned_date
        ? {
            planned_date: candidate.planned_date.slice(0, 10),
          }
        : {};

      const response = await axios.get(
        `${API}/planning/blocks/${candidate.block_id}/operational-assessment`,
        { params },
      );

      setOperationalAssessment(response.data || null);
    } catch (err) {
      console.error(err);

      setOperationalAssessment(null);

      setError(
        err?.response?.data?.detail ||
          "Operational assessment could not be loaded.",
      );
    } finally {
      setOperationalLoading(false);
    }
  }


  async function loadBlockAssessment(candidate) {
    if (!candidate?.block_id) {
      setBlockAssessment(null);
      return;
    }

    try {
      setAssessmentLoading(true);
      setError("");

      const params = candidate.planned_date
        ? {
            planned_date:
              candidate.planned_date.slice(0, 10),
          }
        : {};

      const response = await axios.get(
        `${API}/planning/blocks/${candidate.block_id}/assessment`,
        { params },
      );

      setBlockAssessment(response.data || null);

      const status =
        response.data?.overall_status;

      if (status === "READY_FOR_HUMAN_REVIEW") {
        setDecisionState("READY");
      } else {
        setDecisionState("REVIEW");
      }
    } catch (err) {
      console.error(err);

      setBlockAssessment(null);

      setError(
        err?.response?.data?.detail ||
          "Complete block assessment could not be loaded.",
      );
    } finally {
      setAssessmentLoading(false);
    }
  }

  async function decide(decision) {
    if (!selectedCandidate) return;

    try {
      setDecisionBusy(true);
      setError("");

      const response = await axios.post(
        `${API}/planning/blocks/${selectedCandidate.block_id}/decision`,
        {
          decision,
          actor: "planner",
          note: decisionNote,
          task_ids: selectedCandidate.task_ids || [],
        },
      );

      setDecisionState(
        response.data?.decision?.toUpperCase() ||
          decision.toUpperCase(),
      );
    } catch (err) {
      console.error(err);

      setError(
        err?.response?.data?.detail ||
          "Block decision could not be recorded.",
      );
    } finally {
      setDecisionBusy(false);
    }
  }

  return (
    <div className="block-modal-backdrop">
      <div className="block-planner-workspace">
        <header className="block-planner-header">
          <div>
            <span className="section-kicker">
              RAIL-YOJNA · BLOCK DECISION SUPPORT
            </span>

            <h2>Block Planning Center</h2>

            <p>
              Recommended maintenance blocks generated from
              selected work, risk and available maintenance
              windows.
            </p>
          </div>

          <div className="block-header-actions">
            <span
              className={`planner-state ${decisionState.toLowerCase()}`}
            >
              {decisionState}
            </span>

            <button
              className="modal-close"
              onClick={onClose}
              aria-label="Close block planning"
            >
              ×
            </button>
          </div>
        </header>

        {error && (
          <div className="service-error">
            <strong>Planning warning</strong>
            <span>{error}</span>
          </div>
        )}

        {loading || candidateLoading ? (
          <div className="block-loading">
            {candidateLoading
              ? "Generating recommended maintenance blocks…"
              : "Loading live planning data…"}
          </div>
        ) : (
          <>
            <div className="block-planner-summary">
              <div>
                <span>Block tasks</span>
                <strong>
                  {plan?.summary?.block_tasks ?? 0}
                </strong>
              </div>

              <div>
                <span>Planned hours</span>
                <strong>
                  {Number(
                    plan?.summary?.planned_hours || 0,
                  ).toFixed(1)}
                </strong>
              </div>

              <div>
                <span>Candidates</span>
                <strong>
                  {candidateSummary?.candidates ?? 0}
                </strong>
              </div>

              <div className="selected-summary">
                <span>Feasible</span>
                <strong>
                  {candidateSummary?.feasible ?? 0}
                </strong>
              </div>

              <div>
                <span>Sections</span>
                <strong>
                  {plan?.summary?.sections ?? 0}
                </strong>
              </div>

              <div>
                <span>Tracks</span>
                <strong>
                  {plan?.summary?.tracks ?? 0}
                </strong>
              </div>
            </div>

            <div className="block-planner-toolbar">
              <label>
                <span>Planned date</span>

                <select
                  value={date}
                  onChange={async (event) => {
                    const value = event.target.value;

                    setDate(value);
                    setSection("");
                    setTrack("");

                    await Promise.all([
                      loadPlan(value),
                      loadCandidates({
                        plannedDate: value,
                        sectionId: "",
                        trackId: "",
                      }),
                    ]);
                  }}
                >
                  <option value="">
                    All planned dates
                  </option>

                  {(plan?.available_dates || []).map(
                    (item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ),
                  )}
                </select>
              </label>

              <label>
                <span>Section</span>

                <select
                  value={section}
                  onChange={async (event) => {
                    const value = event.target.value;

                    setSection(value);
                    setTrack("");

                    await loadCandidates({
                      plannedDate: date,
                      sectionId: value,
                      trackId: "",
                    });
                  }}
                >
                  <option value="">
                    All sections
                  </option>

                  {sections.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span>Track</span>

                <select
                  value={track}
                  onChange={async (event) => {
                    const value = event.target.value;

                    setTrack(value);

                    await loadCandidates({
                      plannedDate: date,
                      sectionId: section,
                      trackId: value,
                    });
                  }}
                >
                  <option value="">
                    All tracks
                  </option>

                  {tracks.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>

              <button
                className="button secondary"
                onClick={refresh}
              >
                Refresh
              </button>
            </div>

            <div className="block-planner-body">
              <section className="block-candidates-panel">
                <div className="block-panel-heading">
                  <div>
                    <span className="section-kicker">
                      SYSTEM RECOMMENDATIONS
                    </span>

                    <h3>
                      Recommended maintenance blocks
                    </h3>
                  </div>

                  <span>
                    {topCandidates.length} feasible
                  </span>
                </div>

                <div className="candidate-list">
                  {topCandidates.length === 0 ? (
                    <div className="block-empty-state">
                      <strong>
                        No feasible block candidate
                      </strong>

                      <p>
                        The current maintenance windows do not
                        produce a feasible grouped block under
                        the available planning constraints.
                      </p>
                    </div>
                  ) : (
                    topCandidates.map(
                      (candidate, index) => {
                        const selected =
                          selectedCandidate?.block_id ===
                          candidate.block_id;

                        return (
                          <button
                            type="button"
                            key={candidate.block_id}
                            className={`candidate-card ${
                              selected ? "selected" : ""
                            } ${
                              index === 0
                                ? "recommended"
                                : ""
                            }`}
                            onClick={() => {
                              setSelectedCandidate(
                                candidate,
                              );
                              setDecisionState("REVIEW");
                              setOperationalAssessment(null);
                              setBlockAssessment(null);
                              loadBlockAssessment(candidate);
                            }}
                          >
                            <div className="candidate-card-head">
                              <div>
                                <span className="candidate-rank">
                                  {index === 0
                                    ? "TOP RECOMMENDATION"
                                    : `CANDIDATE ${index + 1}`}
                                </span>

                                <strong>
                                  {candidate.block_id}
                                </strong>
                              </div>

                              <span className="candidate-score">
                                {(
                                  Number(
                                    candidate.score || 0,
                                  ) * 100
                                ).toFixed(1)}
                              </span>
                            </div>

                            <div className="candidate-route">
                              <strong>
                                {candidate.section_id ||
                                  "Unknown section"}
                              </strong>

                              <span>·</span>

                              <strong>
                                {candidate.track_id ||
                                  "Unknown track"}
                              </strong>

                              <span>·</span>

                              <span>
                                {candidate.planned_date?.slice(
                                  0,
                                  10,
                                ) || "Unscheduled"}
                              </span>
                            </div>

                            <div className="candidate-stats">
                              <div>
                                <span>Tasks</span>
                                <strong>
                                  {candidate.task_count}
                                </strong>
                              </div>

                              <div>
                                <span>Duration</span>
                                <strong>
                                  {Number(
                                    candidate.total_duration_hours ||
                                      0,
                                  ).toFixed(1)}{" "}
                                  h
                                </strong>
                              </div>

                              <div>
                                <span>Window</span>
                                <strong>
                                  {Number(
                                    candidate.utilization ||
                                      0,
                                  ) * 100 >=
                                  0
                                    ? `${(
                                        Number(
                                          candidate.utilization ||
                                            0,
                                        ) * 100
                                      ).toFixed(0)}%`
                                    : "—"}
                                </strong>
                              </div>

                              <div>
                                <span>Risk covered</span>
                                <strong>
                                  {Number(
                                    candidate.risk_covered ||
                                      0,
                                  ).toFixed(3)}
                                </strong>
                              </div>
                            </div>

                            <div className="candidate-reasons">
                              {(
                                candidate.reasons || []
                              ).map((reason) => (
                                <span key={reason}>
                                  ✓ {reason}
                                </span>
                              ))}
                            </div>
                          </button>
                        );
                      },
                    )
                  )}
                </div>
              </section>

              <section className="block-map-panel">
                <div className="block-panel-heading">
                  <div>
                    <span className="section-kicker">
                      NETWORK CONTEXT
                    </span>

                    <h3>Railway map</h3>
                  </div>

                  <span>Reference view</span>
                </div>

                <div className="block-map">
                  <MapContainer
                    center={INDIA}
                    zoom={5}
                    scrollWheelZoom
                    style={{
                      height: "100%",
                      width: "100%",
                    }}
                  >
                    <FitIndia />

                    <LayersControl position="topright">
                      <LayersControl.BaseLayer
                        checked
                        name="OpenStreetMap"
                      >
                        <TileLayer
                          attribution="&copy; OpenStreetMap contributors"
                          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                        />
                      </LayersControl.BaseLayer>

                      <LayersControl.BaseLayer
                        name="OpenRailwayMap"
                      >
                        <TileLayer
                          attribution="Railway data &copy; OpenStreetMap contributors"
                          url="https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png"
                          maxZoom={19}
                        />
                      </LayersControl.BaseLayer>
                    </LayersControl>
                  </MapContainer>

                  <div className="map-notice">
                    Network context only. Asset geometry and
                    train occupancy are not yet connected to
                    the current synthetic planning records.
                  </div>
                </div>
              </section>

              <aside className="block-decision-panel">
                <div className="block-panel-heading">
                  <div>
                    <span className="section-kicker">
                      PLANNER REVIEW
                    </span>

                    <h3>Decision</h3>
                  </div>
                </div>

                {!selectedCandidate ? (
                  <div className="block-empty-state">
                    <strong>
                      Select a recommended block
                    </strong>

                    <p>
                      Rail-Yojna has generated feasible
                      candidates. Select one to inspect its
                      workload, planning window and reasons.
                    </p>
                  </div>
                ) : (
                  <div className="candidate-review">
                    <div className="review-hero">
                      <span>Selected recommendation</span>

                      <strong>
                        {selectedCandidate.block_id}
                      </strong>

                      <div>
                        {selectedCandidate.section_id} ·{" "}
                        {selectedCandidate.track_id}
                      </div>
                    </div>

                    <div className="review-grid">
                      <div>
                        <span>Tasks</span>
                        <strong>
                          {selectedCandidate.task_count}
                        </strong>
                      </div>

                      <div>
                        <span>Duration</span>
                        <strong>
                          {Number(
                            selectedCandidate.total_duration_hours ||
                              0,
                          ).toFixed(1)}{" "}
                          h
                        </strong>
                      </div>

                      <div>
                        <span>Risk covered</span>
                        <strong>
                          {Number(
                            selectedCandidate.risk_covered ||
                              0,
                          ).toFixed(3)}
                        </strong>
                      </div>

                      <div>
                        <span>Window use</span>
                        <strong>
                          {(
                            Number(
                              selectedCandidate.utilization ||
                                0,
                            ) * 100
                          ).toFixed(0)}
                          %
                        </strong>
                      </div>
                    </div>

                    <div className="review-window">
                      <span>Recommended planning window</span>

                      <strong>
                        {dateTime(
                          selectedCandidate.window_start,
                        )}
                      </strong>

                      <span>to</span>

                      <strong>
                        {dateTime(
                          selectedCandidate.window_finish,
                        )}
                      </strong>
                    </div>

                    <div className="review-tasks">
                      <div className="review-section-title">
                        Included work
                      </div>

                      {(
                        selectedCandidate.tasks || []
                      ).map((task) => (
                        <div
                          className="review-task"
                          key={task.task_id}
                        >
                          <div>
                            <strong>
                              {task.task_id}
                            </strong>

                            <span>
                              {task.task_type ||
                                "Maintenance"}
                            </span>
                          </div>

                          <div>
                            <Risk value={task.risk} />

                            <small>
                              {hours(
                                task.duration_minutes,
                              )}{" "}
                              h
                            </small>
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="planner-explanation">
                      <strong>
                        Why Rail-Yojna recommends this
                      </strong>

                      <ul>
                        {(
                          selectedCandidate.reasons || []
                        ).map((reason) => (
                          <li key={reason}>
                            {reason}
                          </li>
                        ))}
                      </ul>
                    </div>


                    <div className="unified-assessment">
                      <div className="unified-assessment-head">
                        <div>
                          <span className="section-kicker">
                            BLOCK READINESS
                          </span>

                          <strong>
                            Full planning assessment
                          </strong>
                        </div>

                        {assessmentLoading && (
                          <span className="assessment-loading">
                            Evaluating…
                          </span>
                        )}
                      </div>

                      {!blockAssessment ? (
                        <div className="assessment-placeholder">
                          Select a block recommendation to evaluate
                          maintenance, safety, train and resource
                          constraints.
                        </div>
                      ) : (
                        <>
                          <div
                            className={`overall-readiness ${String(
                              blockAssessment.overall_status ||
                                "",
                            )
                              .toLowerCase()
                              .replaceAll("_", "-")}`}
                          >
                            <strong>
                              {blockAssessment.overall_status}
                            </strong>

                            <span>
                              Human planner review is still
                              required.
                            </span>
                          </div>

                          <div className="assessment-grid">
                            <div>
                              <span>Maintenance</span>
                              <strong>
                                {blockAssessment.maintenance
                                  ?.status || "—"}
                              </strong>
                            </div>

                            <div>
                              <span>Safety</span>
                              <strong>
                                {blockAssessment.safety
                                  ?.status || "—"}
                              </strong>
                            </div>

                            <div>
                              <span>Train</span>
                              <strong>
                                {blockAssessment.trains
                                  ?.status || "—"}
                              </strong>
                            </div>

                            <div>
                              <span>Resources</span>
                              <strong>
                                {blockAssessment.resources
                                  ?.status || "—"}
                              </strong>
                            </div>

                            <div>
                              <span>Materials</span>
                              <strong>
                                {blockAssessment.materials
                                  ?.status || "—"}
                              </strong>
                            </div>
                          </div>

                          <div className="assessment-reasons">
                            <strong>
                              Decision basis
                            </strong>

                            <ul>
                              {(blockAssessment.reasons ||
                                []).map((reason) => (
                                <li key={reason}>
                                  {reason}
                                </li>
                              ))}
                            </ul>
                          </div>

                          {(blockAssessment.trains
                            ?.available_windows || []
                          ).length > 0 && (
                            <div className="assessment-alternatives">
                              <div className="review-section-title">
                                Alternative operational windows
                              </div>

                              {blockAssessment.trains.available_windows
                                .slice(0, 4)
                                .map((window, index) => (
                                  <div
                                    className={
                                      index === 0
                                        ? "assessment-window best"
                                        : "assessment-window"
                                    }
                                    key={`${window.start}-${window.finish}`}
                                  >
                                    <span>
                                      {new Date(
                                        window.start,
                                      ).toLocaleString([], {
                                        dateStyle: "short",
                                        timeStyle: "short",
                                      })}
                                    </span>

                                    <strong>→</strong>

                                    <span>
                                      {new Date(
                                        window.finish,
                                      ).toLocaleString([], {
                                        dateStyle: "short",
                                        timeStyle: "short",
                                      })}
                                    </span>

                                    {index === 0 && (
                                      <b>
                                        RECOMMENDED
                                      </b>
                                    )}
                                  </div>
                                ))}
                            </div>
                          )}

                          {(blockAssessment.trains
                            ?.conflicts || []
                          ).length > 0 && (
                            <div className="assessment-conflicts">
                              <div className="review-section-title">
                                Train conflicts
                              </div>

                              {blockAssessment.trains.conflicts
                                .slice(0, 5)
                                .map((item) => (
                                  <div
                                    key={item.movement_id}
                                  >
                                    <strong>
                                      {item.train_id}
                                    </strong>

                                    <span>
                                      {new Date(
                                        item.occupied_start,
                                      ).toLocaleTimeString([], {
                                        hour: "2-digit",
                                        minute: "2-digit",
                                      })}
                                      {" → "}
                                      {new Date(
                                        item.occupied_finish,
                                      ).toLocaleTimeString([], {
                                        hour: "2-digit",
                                        minute: "2-digit",
                                      })}
                                    </span>
                                  </div>
                                ))}
                            </div>
                          )}
                        </>
                      )}
                    </div>

                    <div className="operational-assessment">
                      <div className="operational-heading">
                        <div>
                          <span className="section-kicker">
                            OPERATIONAL ASSESSMENT
                          </span>

                          <strong>
                            Train and safety compatibility
                          </strong>
                        </div>

                        {operationalLoading && (
                          <span className="assessment-loading">
                            Checking…
                          </span>
                        )}
                      </div>

                      {operationalLoading ? (
                        <div className="assessment-placeholder">
                          Evaluating train occupancy, clearance
                          and safety constraints…
                        </div>
                      ) : !operationalAssessment ? (
                        <div className="assessment-placeholder">
                          Select a candidate to run operational
                          assessment.
                        </div>
                      ) : (
                        <>
                          <div
                            className={`operational-status ${
                              String(
                                operationalAssessment.status ||
                                  "",
                              )
                                .toLowerCase()
                                .replaceAll("_", "-")
                            }`}
                          >
                            <strong>
                              {operationalAssessment.status ||
                                "UNKNOWN"}
                            </strong>

                            <span>
                              {operationalAssessment.reason ||
                                "No assessment explanation available."}
                            </span>
                          </div>

                          <div className="operational-metrics">
                            <div>
                              <span>
                                Movement records
                              </span>

                              <strong>
                                {operationalAssessment
                                  .data_coverage
                                  ?.movement_records ?? "—"}
                              </strong>
                            </div>

                            <div>
                              <span>
                                Same-track movements
                              </span>

                              <strong>
                                {operationalAssessment
                                  .data_coverage
                                  ?.same_track_records ?? "—"}
                              </strong>
                            </div>

                            <div>
                              <span>
                                Min. block
                              </span>

                              <strong>
                                {operationalAssessment
                                  .safety
                                  ?.minimum_block_duration_minutes ??
                                  "—"}{" "}
                                min
                              </strong>
                            </div>

                            <div>
                              <span>
                                Clearance
                              </span>

                              <strong>
                                {operationalAssessment
                                  .safety
                                  ?.minimum_clearance_minutes ??
                                  "—"}{" "}
                                min
                              </strong>
                            </div>
                          </div>

                          {(
                            operationalAssessment
                              .train_conflicts || []
                          ).length > 0 && (
                            <div className="train-conflict-list">
                              <div className="review-section-title">
                                Detected train occupancy
                              </div>

                              {operationalAssessment
                                .train_conflicts
                                .slice(0, 6)
                                .map((conflict) => (
                                  <div
                                    className="train-conflict-row"
                                    key={
                                      conflict.movement_id
                                    }
                                  >
                                    <div>
                                      <strong>
                                        {
                                          conflict.train_id
                                        }
                                      </strong>

                                      <span>
                                        {
                                          conflict.movement_id
                                        }
                                      </span>
                                    </div>

                                    <div>
                                      <small>
                                        {new Date(
                                          conflict.occupied_start,
                                        ).toLocaleTimeString(
                                          [],
                                          {
                                            hour: "2-digit",
                                            minute:
                                              "2-digit",
                                          },
                                        )}
                                        {" → "}
                                        {new Date(
                                          conflict.occupied_finish,
                                        ).toLocaleTimeString(
                                          [],
                                          {
                                            hour: "2-digit",
                                            minute:
                                              "2-digit",
                                          },
                                        )}
                                      </small>
                                    </div>
                                  </div>
                                ))}
                            </div>
                          )}

                          {(
                            operationalAssessment
                              .available_windows || []
                          ).length > 0 && (
                            <div className="alternative-windows">
                              <div className="review-section-title">
                                Available operational windows
                              </div>

                              {operationalAssessment
                                .available_windows
                                .slice(0, 5)
                                .map((window, index) => (
                                  <div
                                    className={`window-option ${
                                      index === 0
                                        ? "best"
                                        : ""
                                    }`}
                                    key={`${window.start}-${window.finish}`}
                                  >
                                    <div>
                                      <strong>
                                        {new Date(
                                          window.start,
                                        ).toLocaleString(
                                          [],
                                          {
                                            dateStyle:
                                              "short",
                                            timeStyle:
                                              "short",
                                          },
                                        )}
                                      </strong>

                                      <span>to</span>

                                      <strong>
                                        {new Date(
                                          window.finish,
                                        ).toLocaleString(
                                          [],
                                          {
                                            dateStyle:
                                              "short",
                                            timeStyle:
                                              "short",
                                          },
                                        )}
                                      </strong>
                                    </div>

                                    {index === 0 && (
                                      <span className="best-window">
                                        RECOMMENDED
                                      </span>
                                    )}
                                  </div>
                                ))}
                            </div>
                          )}
                        </>
                      )}
                    </div>

                    <div className="constraint-review">
                      <strong>
                        Constraint status
                      </strong>

                      <div>
                        {Object.entries(
                          selectedCandidate.constraint_status ||
                            {},
                        ).map(
                          ([name, status]) => (
                            <span
                              key={name}
                              className={
                                status ===
                                "evaluated"
                                  ? "checked"
                                  : "unevaluated"
                              }
                            >
                              {status ===
                              "evaluated"
                                ? "✓"
                                : "○"}{" "}
                              {name.replaceAll(
                                "_",
                                " ",
                              )}
                            </span>
                          ),
                        )}
                      </div>
                    </div>

                    <label className="decision-note">
                      <span>
                        Planner note
                      </span>

                      <textarea
                        value={decisionNote}
                        onChange={(event) =>
                          setDecisionNote(
                            event.target.value,
                          )
                        }
                        placeholder="Record why the block was approved, modified or rejected."
                        rows={3}
                      />
                    </label>

                    <div className="planner-actions">
                      <button
                        className="button secondary"
                        disabled={decisionBusy}
                        onClick={() =>
                          decide("modify")
                        }
                      >
                        Modify
                      </button>

                      <button
                        className="button danger-button"
                        disabled={decisionBusy}
                        onClick={() =>
                          decide("reject")
                        }
                      >
                        Reject
                      </button>

                      <button
                        className="button primary"
                        disabled={
                          decisionBusy ||
                          assessmentLoading ||
                          !blockAssessment ||
                          blockAssessment.overall_status !==
                            "READY_FOR_HUMAN_REVIEW"
                        }
                        onClick={() =>
                          decide("approve")
                        }
                      >
                        Approve
                      </button>
                    </div>

                    <div className="planner-safety-note">
                      Approval records a human planning
                      decision only. It does not issue a
                      railway block authority, route command or
                      signalling instruction.
                    </div>
                  </div>
                )}
              </aside>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
