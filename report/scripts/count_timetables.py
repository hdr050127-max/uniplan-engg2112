"""Recount feasible timetables for the report (no conditions, default activity groups).

Run from the repository root: python3 report/scripts/count_timetables.py
Writes report/data/timetable_counts.json.
"""
import sys, time, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from uniplan.arrangement import arrange_timetables
from uniplan.catalog import SnapshotCatalog
from uniplan.profile import prepare_student_profile
from uniplan.timetable_data import load_timetable_data
from uniplan.ranking import pareto_front

cat = SnapshotCatalog(ROOT / "data/processed", ROOT / "data/requirements")
out = []
for units in (["ENGG2112", "AMME2301"], ["AMME2262", "AMME2301", "CIVL3206", "ENGG2112"],
              ["AMME2262", "AMME2301", "CIVL3206", "ENGG2112", "AMME1362"]):
    prepared = prepare_student_profile({"year": 2026, "session_code": "S2C", "unit_codes": units}, cat)
    profile = prepared["profile"]
    data = load_timetable_data(profile, prepared["snapshot_ref"], cat)
    groups = {u["unit_code"]: [g["group_id"] for g in u["groups"] if g["default_selected"]] for u in data.summary["units"]}
    t0 = time.perf_counter()
    r = arrange_timetables(data.meetings, groups, profile)
    secs = time.perf_counter() - t0
    pool = r["_pool"]
    front = pareto_front(pool) if pool else []
    out.append({"units": units, "snapshot": prepared["snapshot_ref"], "feasible_count": r["feasible_count"],
                "distinct_GDO": len(pool), "non_dominated": len(front), "seconds_full_flow": round(secs, 2),
                "search": r.get("search")})
    print(json.dumps(out[-1], default=str))
(ROOT / "report/data/timetable_counts.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
