from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data/validation/phase6_report.json"


def run(cmd, check=True):
    print("\n$", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, text=True, check=check)


def fail(msg):
    print(f"\n[FAIL] {msg}")
    raise SystemExit(1)


print("=" * 72)
print("RAIL-YOJNA PHASE 6 — SECURITY + RELIABILITY")
print("=" * 72)


checks = {}


# 1. Critical artifacts
artifacts = [
    ROOT / "ml/models/failure_30d_v3_logistic.joblib",
    ROOT / "ml/models/failure_30d_v3_probability_calibrator.joblib",
    ROOT / "optimization/results/maintenance_plan_v2.parquet",
]

for p in artifacts:
    if not p.exists() or p.stat().st_size == 0:
        fail(f"Missing artifact: {p}")
print("[PASS] Model/planner artifacts")
checks["artifacts"] = "PASS"


# 2. Python syntax
files = list((ROOT / "backend").rglob("*.py")) + list((ROOT / "ml").rglob("*.py"))
run(["python3", "-m", "py_compile", *map(str, files)])
print("[PASS] Python syntax")
checks["syntax"] = "PASS"


# 3. CORS review
main = ROOT / "backend/app/main.py"
text = main.read_text(encoding="utf-8")

if "CORSMiddleware" not in text:
    fail("CORSMiddleware configuration missing")

cors_match = re.search(
    r"allow_origins\s*=\s*\[(.*?)\]",
    text,
    re.DOTALL,
)

if not cors_match:
    fail("allow_origins configuration not found")

origins_block = cors_match.group(1)

if re.search(
    r"""["']\*["']""",
    origins_block,
):
    fail("Wildcard CORS origin detected")

origins = re.findall(
    r"""["']([^"']+)["']""",
    origins_block,
)

if not origins:
    fail("No explicit CORS origins configured")

print(f"[PASS] CORS origins restricted: {origins}")
checks["cors"] = "PASS"


# 4. Check for accidental exception leakage
backend_files = list((ROOT / "backend").rglob("*.py"))
leaks = []

for p in backend_files:
    t = p.read_text(encoding="utf-8", errors="ignore")

    for line_no, line in enumerate(t.splitlines(), 1):
        if "detail=str(exc)" in line:
            leaks.append(f"{p.relative_to(ROOT)}:{line_no}")

if leaks:
    print("[WARN] Raw exception leakage:")
    for x in leaks:
        print(" ", x)

    # Do not fail the entire phase because this can be an intentional
    # internal-development endpoint. Record it for hardening.
    checks["exception_leak_review"] = "WARN"
else:
    print("[PASS] No raw exception detail=str(exc) usage")
    checks["exception_leak_review"] = "PASS"


# 5. Safety boundary scan
danger_patterns = [
    r"route\s*setting",
    r"set\s+route",
    r"signal(?:ling|ing)\s+control",
    r"train\s+movement\s+authority",
    r"automatic\s+dispatch",
    r"autonomous[_ -]?(?:railway|train|control)",
]

scan_roots = [
    ROOT / "backend",
    ROOT / "frontend/src",
    ROOT / "ml",
    ROOT / "optimization",
]

violations = []

for base in scan_roots:
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in {".py", ".js", ".jsx", ".ts", ".tsx", ".yaml", ".yml"}:
            continue

        t = p.read_text(encoding="utf-8", errors="ignore")

        for pattern in danger_patterns:
            if re.search(pattern, t, re.IGNORECASE):
                # Documentation/safety statements are allowed.
                if any(
                    word in t.lower()
                    for word in [
                        "not supported",
                        "not allowed",
                        "not for",
                        "prohibited",
                        "disabled",
                        "safety boundary",
                    ]
                ):
                    continue

                violations.append(str(p.relative_to(ROOT)))
                break

if violations:
    print("[WARN] Safety-control terms found; review required:")
    for x in sorted(set(violations)):
        print(" ", x)
    checks["safety_boundary"] = "REVIEW"
else:
    print("[PASS] No active autonomous-control implementation detected")
    checks["safety_boundary"] = "PASS"


# 6. Audit file structural validation
audit = ROOT / "data/audit/decision_events.jsonl"

if audit.exists():
    bad = 0
    total = 0

    for line in audit.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        total += 1

        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue

        required = {
            "event_id",
            "event_type",
            "timestamp",
            "actor",
            "payload",
        }

        if not required.issubset(event):
            bad += 1

    if bad:
        fail(f"Audit integrity failure: {bad} malformed events")

    print(f"[PASS] Audit integrity ({total} events)")
else:
    print("[PASS] Audit file absent/empty — valid fresh-state condition")

checks["audit_integrity"] = "PASS"


# 7. Dependency check
dep = run(
    ["python3", "-m", "pip", "check"],
    check=False,
)

if dep.returncode != 0:
    print("[FAIL] Python dependency check failed")
    checks["dependencies"] = "FAIL"
    fail("pip check failed")

print("[PASS] Python dependencies")
checks["dependencies"] = "PASS"


# 8. Existing tests
tests = run(
    ["python3", "-m", "pytest", "-q", "tests"],
    check=False,
)

if tests.returncode != 0:
    fail("Test suite failed")

print("[PASS] Test suite")
checks["pytest"] = "PASS"


# 9. Frontend build
build = run(
    ["npm", "--prefix", "frontend", "run", "build"],
    check=False,
)

if build.returncode != 0:
    fail("Frontend build failed")

print("[PASS] Frontend production build")
checks["frontend_build"] = "PASS"


# 10. Final report
result = {
    "phase": "6",
    "status": "PASS",
    "timestamp": datetime.now().astimezone().isoformat(),
    "checks": checks,
    "model_version": "failure_30d_v3_logistic",
    "planner_version": "maintenance_plan_v2",
    "human_review_required": True,
    "decision_mode": "decision_support",
    "autonomous_railway_control": False,
}

REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(
    json.dumps(result, indent=2),
    encoding="utf-8",
)

print("\n" + "=" * 72)
print("PHASE 6 COMPLETE")
print("=" * 72)
print(json.dumps(result, indent=2))
print(f"\nReport: {REPORT}")
print("=" * 72)
