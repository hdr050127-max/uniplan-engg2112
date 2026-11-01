"""Ranking-exam accuracy on like-for-like subsets of pairs, for the comparison in Section 7.2.

The teacher labels in llm/rank/output/model_comparison.json ("pairs Qwen judged") are pairs whose two timetables
differ clearly on the persona's main concern; near-ties were decided by code or dropped. This script scores the
exam's 485 answered pairs the same way, by the TIE thresholds of llm/rank/label.py, so the held-out and exam
comparisons of the cares-only rule and equal weights use the same kind of pair.

Run from the repository root: python3 report/scripts/rank_exam_subsets.py
Writes report/data/rank_exam_subsets.json. Uses the exam's own scoring (llm.rank.exam); no model is called.
The exam personas and answers are AI-written (synthetic), not real students.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llm.rank import exam, model as runtime  # noqa: E402
from llm.rank.label import LESS_IS_BETTER, TIE  # noqa: E402

METHODS = {"logistic_regression": "定稿模型（model.json，逻辑回归）", "equal_weights": "等权打分", "cares_only": "按 cares 打分（原占位版）"}


def dominates(p: dict, q: dict) -> bool:
    return all(p[k] <= q[k] for k in LESS_IS_BETTER) and any(q[k] - p[k] >= t for k, t in LESS_IS_BETTER.items())


def main() -> None:
    folder = exam.EXAM
    spec = json.loads(runtime.PATH.read_bytes())
    key = json.loads((folder / "key.json").read_text(encoding="utf-8"))
    bundle = json.loads((folder / "candidates.json").read_text(encoding="utf-8"))
    answers = exam.answers_as_ab(folder, key)
    groups = {"focus_clear": {}, "near_tie_dominated": {}, "near_tie_undominated": {}}
    for g in groups:
        groups[g] = {m: [] for m in METHODS}
    for pid, candidates in bundle["candidates"].items():
        ids = [c["candidate_id"] for c in candidates]
        x = {c["candidate_id"]: c["x"] for c in candidates}
        persona = bundle["personas"][pid]
        scores = exam.method_scores(persona, candidates, spec)
        feature, threshold = TIE[persona["focus"]]
        for pair, info in key.items():
            if info["persona"] != pid or answers[pair] == "tie":
                continue
            a, b = x[info["a_id"]], x[info["b_id"]]
            if abs(a[feature] - b[feature]) >= threshold:
                group = "focus_clear"
            elif dominates(a, b) or dominates(b, a):
                group = "near_tie_dominated"
            else:
                group = "near_tie_undominated"
            for m, name in METHODS.items():
                choice = exam.choice(scores[name], ids, info["a_id"], info["b_id"])
                groups[group][m].append(0.5 if choice == "tie" else float(choice == answers[pair]))
    out = {"note": "Exam pairs with a clear answer, split by whether the two timetables differ on the persona's main "
                   "concern by at least the TIE threshold of llm/rank/label.py; a method's tie scores 0.5. "
                   "Synthetic personas and answers; by report/scripts/rank_exam_subsets.py",
           "groups": {g: {"pairs": len(next(iter(d.values()))), **{m: sum(v) / len(v) for m, v in d.items()}}
                      for g, d in groups.items()}}
    assert sum(v["pairs"] for v in out["groups"].values()) == 485, out["groups"]
    (ROOT / "report/data/rank_exam_subsets.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    for g, v in out["groups"].items():
        print(g, v["pairs"], {m: round(v[m] * 100, 1) for m in METHODS})


if __name__ == "__main__":
    main()
