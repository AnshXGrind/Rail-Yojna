from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend/app"
SRC = ROOT / "frontend/src"

# ---------------------------------------------------------------------
# 1. Block planning service
# ---------------------------------------------------------------------

(ROOT / "backend/app/services/block_service.py").write_text(
r'''
from __future__ import annotations

from typing import Any

import pandas as pd

from backend.app.services.planning_service import load_plan


def _clean(value: Any):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _iso(value):
    value = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(value):
        return None
    return value.isoformat()


def get_block_plan(
    *,
    planned_date: str | None = None,
    limit: int = 500,
) -> dict:
    df = load_plan()

    blocks = df[
        (df["selected"] == 1)
        & (df["block_required"].astype(bool))
    ].copy()

    if planned_date:
        dates = pd.to_datetime(
            blocks["planned_date"],
            utc=True,
            errors="coerce",
        ).dt.strftime("%Y-%m-%d")

        blocks = blocks[dates == planned_date]

    blocks["planned_date_sort"] = pd.to_datetime(
        blocks["planned_date"],
        utc=True,
        errors="coerce",
    )

    blocks["earliest_sort"] = pd.to_datetime(
        blocks["earliest_start"],
        utc=True,
        errors="coerce",
    )

    blocks = blocks.sort_values(
        ["planned_date_sort", "earliest_sort", "section_id", "track_id"]
    ).head(max(1, min(int(limit), 1000)))

    items = []

    for _, row in blocks.iterrows():
        items.append({
            "task_id": _clean(row["task_id"]),
            "asset_id": _clean(row["asset_id"]),
            "section_id": _clean(row.get("section_id")),
            "track_id": _clean(row.get("track_id")),
            "task_type": _clean(row["task_type"]),
            "priority": _clean(row["priority"]),
            "risk": _clean(row["calibrated_risk"]),
            "condition_score": _clean(row["condition_score"]),
            "duration_minutes": _clean(
                row["estimated_duration_minutes"]
            ),
            "planned_date": _iso(row["planned_date"]),
            "earliest_start": _iso(row.get("earliest_start")),
            "latest_finish": _iso(row.get("latest_finish")),
            "decision": _clean(row.get("decision")),
        })

    # Detect overlapping planning windows on the same track.
    # This is a planning-data consistency signal, not an authority
    # to issue a railway block.
    conflicts = []

    conflict_df = blocks.dropna(
        subset=["earliest_sort"]
    ).copy()

    for track_id, group in conflict_df.groupby(
        conflict_df["track_id"].astype(str)
    ):
        group = group.sort_values("earliest_sort")

        rows = list(group.iterrows())

        for i in range(len(rows)):
            _, left = rows[i]

            left_start = left["earliest_sort"]
            left_finish = pd.to_datetime(
                left.get("latest_finish"),
                utc=True,
                errors="coerce",
            )

            if pd.isna(left_finish):
                continue

            for j in range(i + 1, len(rows)):
                _, right = rows[j]

                right_start = right["earliest_sort"]

                if pd.isna(right_start):
                    continue

                if right_start > left_finish:
                    break

                conflicts.append({
                    "track_id": track_id,
                    "task_a": _clean(left["task_id"]),
                    "task_b": _clean(right["task_id"]),
                    "section_a": _clean(left.get("section_id")),
                    "section_b": _clean(right.get("section_id")),
                })

                if len(conflicts) >= 100:
                    break

            if len(conflicts) >= 100:
                break

        if len(conflicts) >= 100:
            break

    unique_dates = (
        pd.to_datetime(
            df.loc[
                (df["selected"] == 1)
                & (df["block_required"].astype(bool)),
                "planned_date",
            ],
            utc=True,
            errors="coerce",
        )
        .dropna()
        .dt.strftime("%Y-%m-%d")
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    summary_source = df[
        (df["selected"] == 1)
        & (df["block_required"].astype(bool))
    ]

    return {
        "items": items,
        "summary": {
            "block_tasks": int(len(summary_source)),
            "planned_hours": float(
                summary_source["estimated_duration_minutes"].sum()
                / 60
            ),
            "sections": int(
                summary_source["section_id"].nunique()
            ),
            "tracks": int(
                summary_source["track_id"].nunique()
            ),
            "schedule_overlaps": int(len(conflicts)),
        },
        "available_dates": unique_dates,
        "conflicts": conflicts,
        "data_mode": "synthetic",
        "planner_version": "maintenance_plan_v2",
        "map": {
            "network_source": "OpenStreetMap + OpenRailwayMap",
            "asset_coordinates_available": False,
            "note": (
                "Current synthetic planning records do not contain "
                "geographic coordinates for asset/task mapping."
            ),
        },
    }
'''
, encoding="utf-8"
)

# ---------------------------------------------------------------------
# 2. Backend route
# ---------------------------------------------------------------------

routes_path = BACKEND / "api/routes.py"
routes = routes_path.read_text(encoding="utf-8")

if "from backend.app.services.block_service import get_block_plan" not in routes:
    anchor = (
        "from backend.app.services.planning_service import (\n"
        "    get_plan,"
    )

    routes = routes.replace(
        anchor,
        "from backend.app.services.block_service import get_block_plan\n"
        + anchor,
        1,
    )

if '"/planning/blocks"' not in routes:
    insert_before = '@router.get("/planning/metrics")'

    block_route = r'''
@router.get("/planning/blocks")
def planning_blocks(
    planned_date: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000),
):
    return get_block_plan(
        planned_date=planned_date,
        limit=limit,
    )


'''

    if insert_before not in routes:
        raise SystemExit(
            "Could not locate planning metrics route."
        )

    routes = routes.replace(
        insert_before,
        block_route + insert_before,
        1,
    )

routes_path.write_text(routes, encoding="utf-8")

# ---------------------------------------------------------------------
# 3. Block Planning frontend
# ---------------------------------------------------------------------

(SRC / "components/BlockPlanningModal.jsx").write_text(
r'''import { useEffect, useMemo, useState } from "react";
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

  if (risk >= 0.50) {
    label = "Critical";
    cls = "critical";
  } else if (risk >= 0.20) {
    label = "High";
    cls = "high";
  } else if (risk >= 0.05) {
    label = "Medium";
    cls = "medium";
  }

  return (
    <span className={`risk-chip ${cls}`}>
      {(risk * 100).toFixed(3)}% · {label}
    </span>
  );
}

export default function BlockPlanningModal({ onClose }) {
  const [data, setData] = useState(null);
  const [date, setDate] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load(selectedDate = "") {
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

      setData(response.data);
    } catch (err) {
      console.error(err);

      setError(
        err?.response?.data?.detail ||
          "Block planning data could not be loaded.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const selectedItems = data?.items || [];

  const grouped = useMemo(() => {
    const groups = new Map();

    selectedItems.forEach((item) => {
      const key =
        item.planned_date?.slice(0, 10) ||
        "Unscheduled";

      if (!groups.has(key)) {
        groups.set(key, []);
      }

      groups.get(key).push(item);
    });

    return Array.from(groups.entries());
  }, [selectedItems]);

  return (
    <div className="block-modal-backdrop">
      <div className="block-modal">
        <div className="block-modal-header">
          <div>
            <span className="section-kicker">
              BLOCK PLANNING
            </span>
            <h2>Maintenance block planning</h2>
            <p>
              Selected work requiring planned track access.
            </p>
          </div>

          <button
            className="modal-close"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        {error && (
          <div className="service-error">
            <strong>Block planning unavailable</strong>
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="block-loading">
            Loading live planning data…
          </div>
        ) : (
          <div className="block-layout">
            <section className="block-left">
              <div className="block-summary-grid">
                <div>
                  <span>Block tasks</span>
                  <strong>
                    {data?.summary?.block_tasks ?? "—"}
                  </strong>
                </div>

                <div>
                  <span>Planned hours</span>
                  <strong>
                    {data?.summary?.planned_hours?.toFixed(1) ?? "—"}
                  </strong>
                </div>

                <div>
                  <span>Sections</span>
                  <strong>
                    {data?.summary?.sections ?? "—"}
                  </strong>
                </div>

                <div>
                  <span>Tracks</span>
                  <strong>
                    {data?.summary?.tracks ?? "—"}
                  </strong>
                </div>

                <div className="warning">
                  <span>Window overlaps</span>
                  <strong>
                    {data?.summary?.schedule_overlaps ?? "—"}
                  </strong>
                </div>
              </div>

              <div className="block-toolbar">
                <label>
                  <span>Date</span>
                  <select
                    value={date}
                    onChange={(event) => {
                      const value = event.target.value;
                      setDate(value);
                      load(value);
                    }}
                  >
                    <option value="">All planned dates</option>
                    {(data?.available_dates || []).map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </label>

                <button
                  className="button secondary"
                  onClick={() => load(date)}
                >
                  Refresh
                </button>
              </div>

              <div className="block-table-wrap">
                {grouped.length === 0 ? (
                  <div className="empty">
                    No selected block tasks for this filter.
                  </div>
                ) : (
                  grouped.map(([groupDate, items]) => (
                    <div
                      className="block-day-group"
                      key={groupDate}
                    >
                      <div className="block-day-heading">
                        <strong>{groupDate}</strong>
                        <span>
                          {items.length} block task
                          {items.length === 1 ? "" : "s"}
                        </span>
                      </div>

                      <table>
                        <thead>
                          <tr>
                            <th>Task</th>
                            <th>Section</th>
                            <th>Track</th>
                            <th>Risk</th>
                            <th>Priority</th>
                            <th>Window</th>
                          </tr>
                        </thead>

                        <tbody>
                          {items.map((item) => (
                            <tr key={item.task_id}>
                              <td>
                                <strong>
                                  {item.task_id}
                                </strong>
                              </td>

                              <td>
                                {item.section_id || "—"}
                              </td>

                              <td>
                                {item.track_id || "—"}
                              </td>

                              <td>
                                <Risk value={item.risk} />
                              </td>

                              <td>
                                {item.priority || "—"}
                              </td>

                              <td>
                                {item.earliest_start
                                  ? new Date(
                                      item.earliest_start,
                                    ).toLocaleTimeString([], {
                                      hour: "2-digit",
                                      minute: "2-digit",
                                    })
                                  : "—"}
                                {" → "}
                                {item.latest_finish
                                  ? new Date(
                                      item.latest_finish,
                                    ).toLocaleTimeString([], {
                                      hour: "2-digit",
                                      minute: "2-digit",
                                    })
                                  : "—"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ))
                )}
              </div>

              <div className="block-disclaimer">
                Overlap detection is derived from planning time
                windows. It is not a signalling or block-authority
                decision.
              </div>
            </section>

            <section className="block-map-panel">
              <div className="block-map-header">
                <div>
                  <strong>Indian rail network</strong>
                  <span>
                    OpenStreetMap + OpenRailwayMap reference layer
                  </span>
                </div>

                <span className="network-live">
                  NETWORK MAP
                </span>
              </div>

              <div className="block-map">
                <MapContainer
                  center={INDIA}
                  zoom={5}
                  minZoom={4}
                  maxZoom={18}
                  scrollWheelZoom
                  style={{
                    width: "100%",
                    height: "100%",
                  }}
                >
                  <LayersControl position="topright">
                    <LayersControl.BaseLayer
                      checked
                      name="OpenStreetMap"
                    >
                      <TileLayer
                        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
                        attribution='&copy; OpenStreetMap contributors'
                      />
                    </LayersControl.BaseLayer>

                    <LayersControl.Overlay
                      checked
                      name="Railway infrastructure"
                    >
                      <TileLayer
                        url="https://tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png"
                        attribution='Railway rendering: <a href="https://www.openrailwaymap.org/">OpenRailwayMap</a>, map data <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
                        maxZoom={19}
                        tileSize={256}
                      />
                    </LayersControl.Overlay>

                    <LayersControl.Overlay
                      name="Railway max speeds"
                    >
                      <TileLayer
                        url="https://tiles.openrailwaymap.org/maxspeed/{z}/{x}/{y}.png"
                        attribution='OpenRailwayMap / OpenStreetMap contributors'
                        maxZoom={19}
                        tileSize={256}
                      />
                    </LayersControl.Overlay>

                    <LayersControl.Overlay
                      name="Railway signalling"
                    >
                      <TileLayer
                        url="https://tiles.openrailwaymap.org/signals/{z}/{x}/{y}.png"
                        attribution='OpenRailwayMap / OpenStreetMap contributors'
                        maxZoom={19}
                        tileSize={256}
                      />
                    </LayersControl.Overlay>
                  </LayersControl>

                  <FitIndia />
                </MapContainer>
              </div>

              <div className="block-map-note">
                <strong>Geospatial linkage status</strong>
                <span>
                  Railway infrastructure is shown from OSM/OpenRailwayMap.
                  Current synthetic assets and tasks do not contain
                  latitude/longitude, so task markers are intentionally
                  not fabricated.
                </span>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
'''
, encoding="utf-8"
)

# ---------------------------------------------------------------------
# 4. App.jsx imports/state/button/modal
# ---------------------------------------------------------------------

app_path = SRC / "App.jsx"
app = app_path.read_text(encoding="utf-8")

if 'import BlockPlanningModal from "./components/BlockPlanningModal";' not in app:
    anchor = 'import LivePrediction from "./components/LivePrediction";'
    if anchor not in app:
        raise SystemExit(
            "Could not find LivePrediction import in App.jsx"
        )

    app = app.replace(
        anchor,
        anchor
        + '\nimport BlockPlanningModal from "./components/BlockPlanningModal";',
        1,
    )

if "const [blockPlanningOpen" not in app:
    anchor = '  const [predictionOpen, setPredictionOpen] = useState(false);\n'
    if anchor not in app:
        raise SystemExit(
            "Could not find predictionOpen state in App.jsx"
        )

    app = app.replace(
        anchor,
        anchor
        + '  const [blockPlanningOpen, setBlockPlanningOpen] = useState(false);\n',
        1,
    )

# Add Block Planning button beside New risk check.
if '>Block planning</button>' not in app:
    anchor = '''          <button
            className="button primary"
            onClick={() =>
              setPredictionOpen(true)
            }
          >
            New risk check
          </button>
'''

    button = '''          <button
            className="button secondary"
            onClick={() => setBlockPlanningOpen(true)}
          >
            Block planning
          </button>

'''

    if anchor not in app:
        raise SystemExit(
            "Could not find New risk check button."
        )

    app = app.replace(
        anchor,
        button + anchor,
        1,
    )

# Insert block modal before the prediction modal.
if "{blockPlanningOpen && (" not in app:
    marker = '''      {predictionOpen && (
'''

    modal = '''      {blockPlanningOpen && (
        <BlockPlanningModal
          onClose={() => setBlockPlanningOpen(false)}
        />
      )}

'''

    if marker not in app:
        raise SystemExit(
            "Could not find prediction modal anchor."
        )

    app = app.replace(
        marker,
        modal + marker,
        1,
    )

# ---------------------------------------------------------------------
# 5. Live report action controls
# ---------------------------------------------------------------------

if "function nextReportStatus" not in app:
    anchor = '''  function openReport(report) {
'''
    idx = app.find(anchor)

    if idx == -1:
        raise SystemExit(
            "Could not find openReport helper."
        )

    helper = r'''  function nextReportStatus(status) {
    return {
      NEW: "TRIAGED",
      TRIAGED: "VERIFIED",
      VERIFIED: "ASSIGNED",
      ASSIGNED: "IN_PROGRESS",
      IN_PROGRESS: "RESOLVED",
      RESOLVED: "CLOSED",
    }[status] || null;
  }

  async function advanceReport(report) {
    const next = nextReportStatus(report.status);

    if (!next) return;

    try {
      await axios.patch(
        `${API}/reports/${encodeURIComponent(
          report.report_id,
        )}/status`,
        {
          status: next,
          actor: "operator",
          note: `Advanced from ${report.status} to ${next}.`,
        },
      );

      loadLiveReports(setLiveReports);
    } catch (error) {
      console.error(error);
      setError(
        error?.response?.data?.detail ||
          `Could not update ${report.report_id}.`,
      );
    }
  }

'''
    app = app[:idx] + helper + app[idx:]

# Replace the invalid nested-button live row with a div/action layout.
pattern = re.compile(
    r'''liveReports\.slice\(0, 12\)\.map\(\(report\) => \{.*?\n\s*\}\)'''
    r'''\)\}''',
    re.S,
)

match = pattern.search(app)

if match:
    new_map = r'''liveReports.slice(0, 12).map((report) => {
                  const unread = !seenReportIds.includes(
                    report.report_id,
                  );

                  const nextStatus = nextReportStatus(
                    report.status,
                  );

                  return (
                    <div
                      key={report.report_id}
                      className={`live-report-row ${
                        unread ? "unread" : ""
                      }`}
                    >
                      <span className="live-report-dot" />

                      <button
                        className="live-report-main-hit"
                        onClick={() => openReport(report)}
                      >
                        <strong>{report.report_id}</strong>
                        <span>
                          {report.problem_type} · {report.asset_id}
                        </span>
                        <small>
                          {report.status} ·{" "}
                          {new Date(
                            report.created_at,
                          ).toLocaleString()}
                        </small>
                      </button>

                      <div className="live-report-actions">
                        <span
                          className={`report-severity ${String(
                            report.severity || "",
                          ).toLowerCase()}`}
                        >
                          {report.severity}
                        </span>

                        {nextStatus && (
                          <button
                            className="report-action-button"
                            onClick={() =>
                              advanceReport(report)
                            }
                            title={`Move to ${nextStatus}`}
                          >
                            {nextStatus === "IN_PROGRESS"
                              ? "Start"
                              : nextStatus === "TRIAGED"
                                ? "Triage"
                                : nextStatus === "VERIFIED"
                                  ? "Verify"
                                  : nextStatus === "ASSIGNED"
                                    ? "Assign"
                                    : nextStatus === "RESOLVED"
                                      ? "Resolve"
                                      : "Close"}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })'''
    app = app[:match.start()] + new_map + app[match.end():]
else:
    raise SystemExit(
        "Could not find live report list block. "
        "Open App.jsx and inspect the liveReports.slice block."
    )

app_path.write_text(app, encoding="utf-8")

# ---------------------------------------------------------------------
# 6. CSS
# ---------------------------------------------------------------------

css_path = SRC / "App.css"
css = css_path.read_text(encoding="utf-8")

css += r'''

/* ================================================================
   PHASE 11E — BLOCK PLANNING + LIVE REPORT ACTIONS
   ================================================================ */

.block-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 120;
  display: grid;
  place-items: center;
  padding: 14px;
  background: rgba(16, 30, 41, .55);
}

.block-modal {
  width: min(1450px, 97vw);
  height: min(880px, 94vh);
  display: grid;
  grid-template-rows: 70px minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid #d5e0e7;
  border-radius: 13px;
  background: #f5f8fa;
  box-shadow: 0 30px 90px rgba(0, 0, 0, .24);
}

.block-modal-header {
  padding: 12px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #dfe7eb;
  background: #fff;
}

.block-modal-header h2 {
  margin: 2px 0 0;
  color: #17365d;
  font-size: 18px;
}

.block-modal-header p {
  margin: 3px 0 0;
  color: #83909a;
  font-size: 8px;
}

.block-layout {
  min-height: 0;
  display: grid;
  grid-template-columns: 1.08fr .92fr;
  gap: 10px;
  padding: 10px;
}

.block-left,
.block-map-panel {
  min-height: 0;
  min-width: 0;
  overflow: hidden;
  border: 1px solid #dce4e8;
  border-radius: 10px;
  background: #fff;
}

.block-left {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
}

.block-summary-grid {
  padding: 10px;
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 7px;
}

.block-summary-grid > div {
  padding: 8px;
  border: 1px solid #e3eaee;
  border-radius: 7px;
  background: #fbfcfd;
}

.block-summary-grid span,
.block-summary-grid strong {
  display: block;
}

.block-summary-grid span {
  color: #80909b;
  font-size: 7px;
  text-transform: uppercase;
}

.block-summary-grid strong {
  margin-top: 3px;
  color: #2e4350;
  font-size: 15px;
}

.block-summary-grid > .warning {
  background: #fff8ed;
  border-color: #f0ddb9;
}

.block-summary-grid > .warning strong {
  color: #a26621;
}

.block-toolbar {
  padding: 0 10px 9px;
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 8px;
  border-bottom: 1px solid #e7edf0;
}

.block-toolbar label {
  min-width: 220px;
}

.block-toolbar label span {
  display: block;
  margin-bottom: 3px;
  color: #7d8992;
  font-size: 7px;
  font-weight: 750;
}

.block-toolbar select {
  width: 100%;
  height: 30px;
  padding: 0 8px;
  border: 1px solid #d4dfe5;
  border-radius: 6px;
  background: #fff;
  color: #354650;
  font-size: 8px;
}

.block-table-wrap {
  min-height: 0;
  overflow: auto;
}

.block-day-group {
  border-bottom: 1px solid #edf0f2;
}

.block-day-heading {
  padding: 7px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #f7fafb;
  border-bottom: 1px solid #e8edf0;
}

.block-day-heading strong {
  color: #355267;
  font-size: 9px;
}

.block-day-heading span {
  color: #89969f;
  font-size: 7px;
}

.block-day-group table {
  width: 100%;
  border-collapse: collapse;
  font-size: 7px;
}

.block-day-group th,
.block-day-group td {
  padding: 7px 8px;
  border-bottom: 1px solid #edf0f2;
  text-align: left;
  white-space: nowrap;
}

.block-day-group th {
  color: #7e8b95;
  background: #fff;
}

.block-day-group td {
  color: #4d5f6a;
}

.block-disclaimer {
  padding: 8px 10px;
  border-top: 1px solid #e6ecef;
  background: #fffaf1;
  color: #866d4c;
  font-size: 7px;
  line-height: 1.45;
}

.block-map-panel {
  display: grid;
  grid-template-rows: 55px minmax(0, 1fr) auto;
}

.block-map-header {
  padding: 9px 11px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e5ebee;
  background: #fff;
}

.block-map-header strong,
.block-map-header span {
  display: block;
}

.block-map-header strong {
  color: #314957;
  font-size: 10px;
}

.block-map-header span {
  margin-top: 2px;
  color: #89969e;
  font-size: 7px;
}

.network-live {
  padding: 4px 6px;
  border-radius: 999px;
  background: #edf5fb;
  color: #336187 !important;
  font-weight: 800;
}

.block-map {
  min-height: 0;
}

.block-map .leaflet-container {
  width: 100%;
  height: 100%;
  background: #e9eef1;
}

.block-map-note {
  padding: 8px 10px;
  display: grid;
  gap: 2px;
  border-top: 1px solid #e5ebee;
  background: #f8fafb;
}

.block-map-note strong {
  color: #526774;
  font-size: 7px;
}

.block-map-note span {
  color: #87949c;
  font-size: 7px;
  line-height: 1.4;
}

.block-loading {
  display: grid;
  place-items: center;
  height: 100%;
  color: #7f8c95;
  font-size: 9px;
}

.live-report-main-hit {
  min-width: 0;
  padding: 0;
  display: block;
  border: 0;
  background: transparent;
  text-align: left;
}

.live-report-main-hit strong,
.live-report-main-hit span,
.live-report-main-hit small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.live-report-main-hit strong {
  color: #314957;
  font-size: 9px;
}

.live-report-main-hit span {
  margin-top: 2px;
  color: #6f7e89;
  font-size: 8px;
}

.live-report-main-hit small {
  margin-top: 2px;
  color: #9aa5ad;
  font-size: 6px;
}

.live-report-actions {
  display: flex;
  align-items: center;
  gap: 5px;
}

.report-action-button {
  height: 22px;
  padding: 0 7px;
  border: 1px solid #cbdce7;
  border-radius: 5px;
  background: #edf5fb;
  color: #315c7f;
  font-size: 6px;
  font-weight: 850;
}

.report-action-button:hover {
  background: #dfeef7;
}

@media (max-width: 1200px) {
  .block-layout {
    grid-template-columns: 1fr;
    overflow: auto;
  }

  .block-map-panel {
    min-height: 420px;
  }

  .block-summary-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
'''

css_path.write_text(css, encoding="utf-8")

print("Phase 11E installed.")
print("Added:")
print(" - /api/v1/planning/blocks")
print(" - Control Room Block planning modal")
print(" - OSM + OpenRailwayMap layers")
print(" - Block workload / schedule overlap view")
print(" - Live report workflow actions")
