"""Block 4: order valid timetables for one student. Owned by the ranking window.

Placeholder with the final shape (llm.contracts.Ranked): an equal-weight score over the
criteria the student cares about. The ranking window replaces it with the trained model.
"""
from __future__ import annotations

from statistics import mean, pstdev

from llm.contracts import Candidate, Preferences, Ranked

_FEATURE = {"campus_days": "campus_days", "gap": "gap_min", "outside_hours": "outside_min"}


def rank(candidates: list[Candidate], prefs: Preferences) -> list[Ranked]:
    """Best first. Lower is better for every feature, so the score is minus their z-scores."""
    keys = [_FEATURE[care] for care in (prefs.get("cares") or list(_FEATURE))]
    stats = {}
    for key in keys:
        values = [c["features"][key] for c in candidates]
        stats[key] = (mean(values), pstdev(values) or 1.0)
    scored = [{"candidate_id": c["candidate_id"],
               "score": -sum((c["features"][key] - stats[key][0]) / stats[key][1] for key in keys)}
              for c in candidates]
    return sorted(scored, key=lambda item: -item["score"])
