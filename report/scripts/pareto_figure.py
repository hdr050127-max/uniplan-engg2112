"""Data for the report's Pareto figures: one exam student's valid timetables, and front sizes for every student.

Run from the repository root: python3 report/scripts/pareto_figure.py
Writes report/data/pareto_example.json, read by report/scripts/make_numbers.py (the figure captions)
and report/scripts/figure_data.py (Figures 2 and 5).
The sentences are final-exam items written by a Claude agent (synthetic, not real students).
Each is planned with the exam writer's intended conditions on the same courses as
scripts/evaluate_pipeline.py, with the deployed ranker (llm/rank/model.json); no Ollama call is made.
"""
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

os.environ["UNIPLAN_OLLAMA_URL"] = "http://127.0.0.1:11434"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import uniplan.arrangement as arrangement  # noqa: E402
from evaluate_explain import UNIT_SETS, base_profile, conditions_from, sentences, tracked_catalog  # noqa: E402
from uniplan.advisor import CANDIDATE_MIN, merge_conditions  # noqa: E402
from uniplan.main import main  # noqa: E402
from uniplan.ranking import SCALES, axes_name, pareto_front  # noqa: E402

SENTENCE_ID = "e187"

# main() keeps the pool of distinct G/D/O profiles private; keep a copy as the search returns it.
captured = {}
search_pool = arrangement.pool_from_search


def keep_pool(search, **kwargs):
    captured["pool"], truncated = search_pool(search, **kwargs)
    return captured["pool"], truncated


arrangement.pool_from_search = keep_pool


def planned(text: str, rows: list[dict], units: list[str], catalog, groups: dict) -> dict | None:
    """The shown menu and the full pool for the intended conditions, or None if nothing is feasible."""
    gold = conditions_from(rows)
    result = main(merge_conditions(base_profile(units), gold), catalog, selected_groups=groups,
                  student_text=text, cares=gold.get("cares") or [])
    if result["status"] != "ready":
        return None
    ranking = result["ranking_result"]
    cares = gold.get("cares") or list(SCALES)
    menu = ranking["recommendation"]["menus"][axes_name(tuple(a for a in SCALES if a in cares))]
    return {"conditions": gold, "feasible_count": ranking["feasible_count"], "pool": captured["pool"],
            "front": [e["candidate_id"] for e in pareto_front(captured["pool"])], "menu": menu}


def main_cli() -> None:
    exam = sentences(ROOT / "llm/parse/exam/exam.csv")
    example, students = None, []
    with tempfile.TemporaryDirectory() as temp:
        catalog = tracked_catalog(Path(temp))
        groups = {}
        for units in UNIT_SETS:
            data = main(base_profile(units), catalog)["module_two_result"]
            groups[tuple(units)] = {u["unit_code"]: [g["group_id"] for g in u["groups"] if g["default_selected"]]
                                    for u in data["units"]}
        for index, (sid, text, rows) in enumerate(exam):
            units = UNIT_SETS[index % len(UNIT_SETS)]
            plan = planned(text, rows, units, catalog, groups[tuple(units)])
            if plan is None:
                continue
            students.append({"sentence_id": sid, "units": len(units), "feasible_count": plan["feasible_count"],
                             "profiles": len(plan["pool"]), "front": len(plan["front"]),
                             "candidates": len(plan["menu"]["candidates"])})
            if sid == SENTENCE_ID:
                example = {"sentence_id": sid, "sentence": text, "units": units, **plan}
    pool = example.pop("pool")
    menu = example.pop("menu")
    example.update({
        "profiles": len(pool),
        "axes": {"G": "waiting time, hours a week", "D": "campus days a week (mean over teaching weeks)",
                 "O": "early or late class time, hours a week"},
        "points": {e["candidate_id"]: [round(e["features"]["gap_min"] / 60, 3), round(e["features"]["campus_days"], 3),
                                       round(e["features"]["outside_min"] / 60, 3)] for e in pool},
        "candidates": menu["candidates"], "picks": menu["picks"], "reasons": menu["reasons"],
    })
    out = {
        "note": "Final-exam sentences written by a Claude agent (synthetic, not real students), planned with their "
                "intended conditions by report/scripts/pareto_figure.py",
        "example": example,
        "students": students,
        "front_sizes": dict(sorted(Counter(s["front"] for s in students).items())),
        "candidate_min": CANDIDATE_MIN,
    }
    (ROOT / "report/data/pareto_example.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(len(exam), "sentences,", len(students), "with a timetable; front sizes", out["front_sizes"])


if __name__ == "__main__":
    main_cli()
