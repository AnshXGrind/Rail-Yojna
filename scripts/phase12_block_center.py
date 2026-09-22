from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend/src/App.jsx"
CSS = ROOT / "frontend/src/App.css"

app = APP.read_text()

# ------------------------------------------------------------
# Import block planner
# ------------------------------------------------------------

if 'import BlockPlanningModal from "./components/BlockPlanningModal";' not in app:
    anchor = 'import LivePrediction from "./components/LivePrediction";'
    if anchor not in app:
        raise SystemExit("LivePrediction import not found")
    app = app.replace(
        anchor,
        anchor + '\nimport BlockPlanningModal from "./components/BlockPlanningModal";',
        1,
    )

# ------------------------------------------------------------
# State
# ------------------------------------------------------------

if "const [blockPlanningOpen" not in app:
    anchor = '  const [predictionOpen, setPredictionOpen] = useState(false);'
    if anchor not in app:
        raise SystemExit("predictionOpen state not found")
    app = app.replace(
        anchor,
        anchor + '\n  const [blockPlanningOpen, setBlockPlanningOpen] = useState(false);',
        1,
    )

# ------------------------------------------------------------
# Main header button
# ------------------------------------------------------------

if "setBlockPlanningOpen(true)" not in app:
    anchor = '''          <button
            className="button primary"
            onClick={() =>
              setPredictionOpen(true)
            }
          >
            New risk check
          </button>
'''

    if anchor not in app:
        raise SystemExit("New risk check button not found")

    block_button = '''          <button
            className="button block-primary"
            onClick={() => setBlockPlanningOpen(true)}
          >
            Block Planning
          </button>

'''

    app = app.replace(
        anchor,
        block_button + anchor,
        1,
    )

# ------------------------------------------------------------
# Block planning modal mount
# ------------------------------------------------------------

if "{blockPlanningOpen && (" not in app:
    anchor = "      {predictionOpen && ("
    if anchor not in app:
        raise SystemExit("Prediction modal anchor not found")

    modal = '''      {blockPlanningOpen && (
        <BlockPlanningModal
          onClose={() => setBlockPlanningOpen(false)}
        />
      )}

'''

    app = app.replace(
        anchor,
        modal + anchor,
        1,
    )

APP.write_text(app)

# ------------------------------------------------------------
# CSS — make the Control Room block-first
# ------------------------------------------------------------

css = CSS.read_text()

css += r'''

/* ================================================================
   PHASE 12 — BLOCK PLANNING CENTER VISUAL HIERARCHY
   ================================================================ */

.block-primary {
  border: 1px solid #d48a2b !important;
  background: #fff4df !important;
  color: #8a5a18 !important;
  font-weight: 850 !important;
}

.block-primary:hover {
  background: #ffe9c2 !important;
  border-color: #c77b21 !important;
}

.dashboard .workspace {
  position: relative;
}

.dashboard .risk-panel {
  border-top: 3px solid #2f7dc5;
}

.dashboard .plan-panel {
  border-top: 3px solid #2da56b;
}

.dashboard .detail-panel {
  border-top: 3px solid #e8922f;
}

.dashboard .decision-panel {
  border-top: 3px solid #17365d;
}

.dashboard .toolbar h2 {
  color: #17365d;
}

.dashboard .section-kicker {
  color: #2f7dc5;
}

.dashboard .metric-blue .metric-accent {
  background: #75acd6;
}

.dashboard .metric-green .metric-accent {
  background: #39a878;
}

.dashboard .metric-orange .metric-accent {
  background: #e8922f;
}

.dashboard .metric-red .metric-accent {
  background: #d85b54;
}

/* Block-planning emphasis */
.dashboard::before {
  content: "BLOCK PLANNING • RISK → MAINTENANCE → HUMAN REVIEW";
  display: block;
  position: absolute;
  pointer-events: none;
}

/* stronger task selection */
.plan-panel tbody tr.selected {
  background: #eef8f2;
  box-shadow: inset 3px 0 0 #2da56b;
}

/* high-risk assets */
.risk-panel tbody tr.selected {
  background: #edf5fb;
  box-shadow: inset 3px 0 0 #2f7dc5;
}
'''

# Remove the pseudo-element rule because the dashboard itself is not
# positioned; keep the rest of the hierarchy.
css = css.replace(
    '''.dashboard::before {
  content: "BLOCK PLANNING • RISK → MAINTENANCE → HUMAN REVIEW";
  display: block;
  position: absolute;
  pointer-events: none;
}

/* Block-planning emphasis */
''',
    '''/* Block-planning emphasis */

''',
)

CSS.write_text(css)

print("Phase 12 Block Planning Center shell installed.")
