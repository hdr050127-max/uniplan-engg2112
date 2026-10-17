"""Does the ranker trade waiting time away for gap-focused students, and does the teacher agree?

For every test persona whose main concern is waiting (focus "gap"), look at
1. the model's first and second pick among the persona's 8 test candidates: how often the first
   waits noticeably longer (>= 0.5 h a week), and what the teacher said about that pair;
2. every test pair where the model prefers the timetable that waits noticeably longer: how often
   the teacher (14B, or the program's rule) prefers it too.
The teacher's labels are the round robin from labelling (SYNTHETIC). Standard library only.

    python3 -m llm.rank.gap_check --labels llm/rank/output/labels_v3d_qwen2.5_14b_corrected.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llm.rank import model as runtime  # noqa: E402
from llm.rank.personas import load  # noqa: E402

OUT = ROOT / "llm" / "rank" / "output"
NOTICEABLE = 0.5      # hours of waiting a week, the labelling tie threshold


def teacher_says(labels: dict, persona: str, first: str, second: str) -> str:
    """'first', 'second', 'tie' or 'flip' for the pair, whichever order it was labelled in."""
    row = labels.get((persona, first, second)) or labels.get((persona, second, first))
    if row is None:
        return "missing"
    if row["label"] in ("tie", "flip"):
        return row["label"]
    winner = row["a_id"] if row["label"] == "A" else row["b_id"]
    return "first" if winner == first else "second"


def check(labels_path: Path, spec: dict | None = None) -> dict:
    spec = spec or runtime.load()
    labels = {(r["persona"], r["a_id"], r["b_id"]): r
              for r in map(json.loads, labels_path.read_text(encoding="utf-8").splitlines())}
    sets = json.loads((OUT / "candidate_sets.json").read_text(encoding="utf-8"))["sets"]
    personas = [p for p in load() if p["split"] == "test" and p["focus"] == "gap"]
    top_pairs, longer = [], Counter()
    for persona in personas:
        prefs = {"cares": persona["conditions"]["cares"], "preferred_hours": persona["conditions"].get("preferred_hours")}
        s = runtime.student_terms(prefs)
        candidates = sets[persona["id"]]
        scored = sorted(candidates, key=lambda c: -runtime.utility(c["x"], s, spec))
        first, second = scored[0], scored[1]
        extra = first["x"]["gap_h"] - second["x"]["gap_h"]
        top_pairs.append({"persona": persona["id"], "extra_gap_h": round(extra, 2),
                          "first_waits_longer": extra >= NOTICEABLE,
                          "teacher": teacher_says(labels, persona["id"], first["candidate_id"], second["candidate_id"]),
                          "extra_single_class_days": round(first["x"]["single_class_days"] - second["x"]["single_class_days"], 2),
                          "extra_campus_days": round(first["x"]["campus_days"] - second["x"]["campus_days"], 2)})
        for i, a in enumerate(candidates):
            for b in candidates[i + 1:]:
                ua, ub = runtime.utility(a["x"], s, spec), runtime.utility(b["x"], s, spec)
                winner, loser = (a, b) if ua > ub else (b, a)
                if winner["x"]["gap_h"] - loser["x"]["gap_h"] >= NOTICEABLE:
                    longer[teacher_says(labels, persona["id"], winner["candidate_id"], loser["candidate_id"])] += 1
    decided = longer["first"] + longer["second"]
    return {
        "note": "合成数据：测试画像里最在意空等的人；老师 = 14B 或程序规则。",
        "gap_focused_test_personas": len(personas),
        "top_two": top_pairs,
        "first_waits_longer": sum(t["first_waits_longer"] for t in top_pairs),
        "teacher_on_those": dict(Counter(t["teacher"] for t in top_pairs if t["first_waits_longer"])),
        "pairs_where_model_prefers_longer_wait": sum(longer.values()),
        "teacher_on_those_pairs": dict(longer),
        "teacher_agrees_rate": round(longer["first"] / decided, 3) if decided else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", default="gap_check.json")
    args = parser.parse_args()
    result = check(args.labels)
    (OUT / args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "top_two"}, ensure_ascii=False, indent=1))
    for row in result["top_two"]:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
