"""Paired 95% bootstrap interval for the ranking exam: trained logistic regression minus equal weights.

Run from the repository root: python3 report/scripts/rank_exam_paired.py
Writes report/data/rank_exam_paired.json. No model is called: both methods are the frozen
offline scorers in llm/rank/exam.py, and the exam answers are read from llm/rank/exam/.

Personas are resampled (pairs within one persona are not independent), 10,000 times, seed 2112;
each resample scores both methods on the same pairs, so the interval is for the difference.
"""
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llm.rank import exam, model as runtime  # noqa: E402

LR, EQUAL = "定稿模型（model.json，逻辑回归）", "等权打分"
REPS, SEED = 10_000, 2112


def hits_by_persona() -> dict[str, dict[str, list[float]]]:
    """{method: {persona: [hit per scored pair]}}, scored exactly as llm.rank.exam.score does."""
    folder = exam.EXAM
    spec = json.loads(runtime.PATH.read_bytes())
    key = json.loads((folder / "key.json").read_text(encoding="utf-8"))
    bundle = json.loads((folder / "candidates.json").read_text(encoding="utf-8"))
    answers = exam.answers_as_ab(folder, key)
    hits = {LR: defaultdict(list), EQUAL: defaultdict(list)}
    for pid, cs in bundle["candidates"].items():
        ids = [c["candidate_id"] for c in cs]
        scores = exam.method_scores(bundle["personas"][pid], cs, spec)
        for pair_id, info in key.items():
            truth = answers[pair_id]
            if info["persona"] != pid or truth == "tie":
                continue
            for name in hits:
                chosen = exam.choice(scores[name], ids, info["a_id"], info["b_id"])
                hits[name][pid].append(0.5 if chosen == "tie" else float(chosen == truth))
    return hits


def accuracy(per_persona: dict[str, list[float]], personas: list[str]) -> float:
    return mean(h for p in personas for h in per_persona[p])


def main() -> None:
    hits = hits_by_persona()
    personas = sorted(hits[LR])
    rng = random.Random(SEED)
    diffs = []
    for _ in range(REPS):
        sample = [rng.choice(personas) for _ in personas]
        diffs.append(accuracy(hits[LR], sample) - accuracy(hits[EQUAL], sample))
    diffs.sort()
    out = {"note": "Ranking final exam, trained LR minus equal weights; synthetic AI-written personas and answers",
           "personas": len(personas), "pairs_scored": sum(len(v) for v in hits[LR].values()),
           "reps": REPS, "seed": SEED,
           "lr_accuracy": accuracy(hits[LR], personas), "equal_accuracy": accuracy(hits[EQUAL], personas),
           "difference": accuracy(hits[LR], personas) - accuracy(hits[EQUAL], personas),
           "difference_ci95": [diffs[int(0.025 * REPS)], diffs[int(0.975 * REPS) - 1]]}
    (ROOT / "report/data/rank_exam_paired.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
