"""The trained ranking model at run time: standard library only.

A pairwise logistic regression, P(A better than B) = sigmoid(w . (phi(A) - phi(B))), where
phi joins the timetable's scaled features with their products with the student's terms
(main concern, the other cares, own comfortable hours). Because the student terms are the
same for every candidate, this is one weight per feature for that student:

    utility(c) = sum_i z_i(c) * (w_i + sum_j w_ij * s_j)

and rank() simply sorts by utility. The weights come from llm/rank/train.py and live in
llm/rank/model.json.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).with_name("model.json")
CARES = ("campus_days", "gap", "outside_hours")
STUDENT_TERMS = ("focus_campus_days", "focus_gap", "focus_outside_hours",
                 "cares_campus_days", "cares_gap", "cares_outside_hours", "hours_start", "hours_end")


def student_terms(prefs: dict | None) -> list[float]:
    """Main concern (cares[0]), every care, and the comfortable day relative to 09:00-18:00
    (in units of 3 hours). Missing preferences give zeros: the population-average student."""
    prefs = prefs or {}
    cares = [care for care in prefs.get("cares") or () if care in CARES]
    focus = cares[0] if cares else None
    hours = prefs.get("preferred_hours") or {}
    start = (hours.get("start_min", 540) - 540) / 180
    end = (hours.get("end_min", 1080) - 1080) / 180
    return ([1.0 if focus == care else 0.0 for care in CARES] +
            [1.0 if care in cares else 0.0 for care in CARES] + [start, end])


def phi(x: dict[str, float], s: list[float], spec: dict) -> list[float]:
    z = [(x[name] - spec["center"][name]) / spec["scale"][name] for name in spec["features"]]
    return z + [zi * sj for sj in s for zi in z]


def personal_weights(s: list[float], spec: dict) -> dict[str, float]:
    """The weight each feature gets for this student (negative: the student wants less of it)."""
    names, w = spec["features"], spec["weights"]
    n = len(names)
    return {name: w[i] + sum(w[n * (j + 1) + i] * sj for j, sj in enumerate(s)) for i, name in enumerate(names)}


def utility(x: dict[str, float], s: list[float], spec: dict) -> float:
    return sum(wi * pi for wi, pi in zip(spec["weights"], phi(x, s, spec)))


def prefer(xa: dict[str, float], xb: dict[str, float], s: list[float], spec: dict) -> float:
    """P(A better than B) for this student."""
    margin = utility(xa, s, spec) - utility(xb, s, spec)
    return 1 / (1 + math.exp(-max(-60.0, min(60.0, margin))))


@lru_cache(maxsize=1)
def load(path: str = str(PATH)) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
