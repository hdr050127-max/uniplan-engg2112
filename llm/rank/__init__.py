"""Block 4: order valid timetables for one student. Owned by the ranking window.

rank() scores each candidate with the trained pairwise logistic regression (llm/rank/model.py,
weights in llm/rank/model.json, trained on synthetic teacher labels by llm/rank/train.py).
Features come from the candidates' dated meetings and the student's own comfortable hours
(llm/rank/features.py). Everything here is standard library only.

Without model.json it falls back to the rule it replaced: minus the sum of z-scores of the
features the student cares about (all three when no cares are given).
"""
from __future__ import annotations

from statistics import mean, pstdev

from llm.contracts import Candidate, Preferences, Ranked
from llm.rank import model
from llm.rank.features import candidate_features

_FEATURE = {"campus_days": "campus_days", "gap": "gap_min", "outside_hours": "outside_min"}


def rank(candidates: list[Candidate], prefs: Preferences, spec: dict | None = None) -> list[Ranked]:
    """Best first; equal scores keep a stable order by candidate id. ``spec`` overrides model.json."""
    if not candidates:
        return []
    spec = spec if spec is not None else model.load()
    if spec is None:
        scored = rule_scores(candidates, prefs)
    else:
        s = model.student_terms(prefs)
        scored = [{"candidate_id": c["candidate_id"], "score": model.utility(x, s, spec)}
                  for c, x in zip(candidates, candidate_features(candidates, prefs))]
    return sorted(scored, key=lambda item: (-item["score"], item["candidate_id"]))


def rule_scores(candidates: list[Candidate], prefs: Preferences) -> list[Ranked]:
    """The rule baseline: lower is better for every feature, so the score is minus their z-scores."""
    keys = [_FEATURE[care] for care in (prefs.get("cares") or list(_FEATURE))]
    stats = {}
    for key in keys:
        values = [c["features"][key] for c in candidates]
        stats[key] = (mean(values), pstdev(values) or 1.0)
    return [{"candidate_id": c["candidate_id"],
             "score": -sum((c["features"][key] - stats[key][0]) / stats[key][1] for key in keys)}
            for c in candidates]
