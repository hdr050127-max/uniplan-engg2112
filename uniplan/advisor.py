"""The AI steps around the scheduler: sentence -> conditions -> candidates -> top 3 -> reasons.

Only the scheduler decides what is feasible. ``llm.parse`` turns the sentence into
conditions the student confirms; ``llm.rank`` and ``llm.explain`` only ever see
timetables that already passed every hard check. Interfaces: ``llm/contracts.py``.
"""

from __future__ import annotations

import secrets
from collections import OrderedDict
from threading import Lock
from typing import Any, Callable

from llm.contracts import Conditions, preferences_of, to_profile_fields
from llm.explain import explain
from llm.parse import parse
from llm.rank import rank

from .profile import check_condition_fields
from .ranking import AXIS_FEATURE, AXIS_SETS, SCALES, _order, _score, axes_name, pareto_front

CANDIDATE_MIN = 10
CANDIDATE_MAX = 20
PICKS = 3
CARES = tuple(SCALES)  # "gap", "campus_days", "outside_hours": the contract's Care names


def preference_order(entries: list[dict[str, Any]], axes: tuple[str, ...]) -> list[dict[str, Any]]:
    """Best first by equal weight on the features the student cares about."""
    weights = {axis: (1 / len(axes) if axis in axes else 0.0) for axis in SCALES}
    return sorted(entries, key=lambda entry: _order(_score(entry["features"], weights)[0],
                                                    entry["features"], entry["candidate_id"]))


# Differences a student would not notice in a weekly routine.
NOTICEABLE = {"gap": 30.0, "campus_days": 0.2, "outside_hours": 30.0}


def similar(a: dict[str, Any], b: dict[str, Any], axes: tuple[str, ...]) -> bool:
    """No noticeable difference on any feature the student cares about."""
    return all(abs(a["features"][AXIS_FEATURE[axis]] - b["features"][AXIS_FEATURE[axis]]) < NOTICEABLE[axis]
               for axis in axes)


def distinct_first(entries: list[dict[str, Any]], count: int, axes: tuple[str, ...], *,
                   copies: bool = True) -> list[dict[str, Any]]:
    """Up to ``count`` entries in order, skipping near-copies (on ``axes``) of ones already taken.

    If that leaves too few, skipped entries come back: first those that differ on
    some other feature, then (only with ``copies``) the rest.
    """
    taken, skipped = [], []
    for entry in entries:
        if len(taken) == count:
            break
        (skipped if any(similar(entry, other, axes) for other in taken) else taken).append(entry)
    for entry in skipped:
        if len(taken) < count and not any(similar(entry, other, CARES) for other in taken):
            taken.append(entry)
    if copies:
        taken += [entry for entry in skipped if entry not in taken][:count - len(taken)]
    return taken


def select_candidates(pool: list[dict[str, Any]], axes: tuple[str, ...]) -> tuple[list[dict[str, Any]], int]:
    """10–20 candidates for the ranker, and how many of them are on the Pareto front.

    The front (no other timetable is at least as good on all three features) comes
    first. A small front is topped up with the next best timetables by the student's
    preference; a large one keeps the best on each cared-about feature, then the
    preference order. Near-copies on the cared-about features are skipped while there are
    other choices. A pool smaller than 10 is used whole.
    """
    front = pareto_front(pool)
    if len(front) > CANDIDATE_MAX:
        anchors = [pareto_front(pool, (axis,))[0] for axis in axes]
        ordered = list({entry["candidate_id"]: entry for entry in anchors + preference_order(front, axes)}.values())
        return distinct_first(ordered, CANDIDATE_MAX, axes), CANDIDATE_MAX
    on_front = {entry["candidate_id"] for entry in front}
    rest = preference_order([entry for entry in pool if entry["candidate_id"] not in on_front], axes)
    chosen = distinct_first(preference_order(front, axes) + rest, max(CANDIDATE_MIN, len(front)), axes)
    return chosen, sum(entry["candidate_id"] in on_front for entry in chosen)


def rank_candidates(candidates: list[dict[str, Any]], prefs: dict[str, Any]) -> tuple[list[str], dict[str, float], str]:
    """Candidate ids best first, their scores, and who ordered them.

    The ranker may be replaced at any time, so its answer is checked: unknown ids are
    ignored, and anything it leaves out keeps the preference order at the end. If it
    fails outright the preference order is used and the reason is reported.
    """
    ids = [candidate["candidate_id"] for candidate in candidates]
    try:
        ranked = rank(candidates, prefs)
        scores: dict[str, float] = {}
        for item in ranked:
            if item["candidate_id"] in ids and item["candidate_id"] not in scores:
                scores[item["candidate_id"]] = float(item["score"])
        source = "llm.rank"
    except Exception as exc:  # noqa: BLE001 - any ranker failure falls back, visibly
        scores, source = {}, f"preference order ({type(exc).__name__})"
    return list(scores) + [cid for cid in ids if cid not in scores], scores, source


def recommend(pool: list[dict[str, Any]], profile: dict[str, Any], student_text: str, *,
              candidate: Callable[[dict[str, Any]], dict[str, Any]],
              item: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    """Top 3 for every choice of cared-about features, like the shortlist menus.

    ``candidate`` turns a pool entry into an ``llm.contracts.Candidate``; ``item``
    adds a pick to the shortlist items (meetings, backups, weekday variants), so the
    page can show a pick exactly like any other plan.
    """
    by_id = {entry["candidate_id"]: entry for entry in pool}
    built: dict[str, dict[str, Any]] = {}
    menus, sources = {}, set()
    for axes in AXIS_SETS:
        chosen, from_front = select_candidates(pool, axes)
        candidates = [built.setdefault(entry["candidate_id"], candidate(entry)) for entry in chosen]
        conditions = conditions_of(profile, axes)
        order, scores, source = rank_candidates(candidates, preferences_of(conditions, student_text))
        sources.add(source)
        # Near-identical timetables help nobody: keep the ranker's order, minus near-copies,
        # even if that leaves fewer than three.
        picks = [item(entry) for entry in distinct_first([by_id[cid] for cid in order], PICKS, axes, copies=False)]
        menus[axes_name(axes)] = {
            "candidates": [entry["candidate_id"] for entry in chosen], "from_front": from_front,
            "picks": [pick["candidate_id"] for pick in picks],
            "scores": [scores.get(pick["candidate_id"]) for pick in picks],
            "reasons": explain(student_text, conditions, picks, model=None),
        }
    return {"menus": menus, "ranker": " / ".join(sorted(sources)), "reasons_by": "template",
            "candidate_range": [CANDIDATE_MIN, CANDIDATE_MAX]}


def conditions_of(profile: dict[str, Any], cares: tuple[str, ...] | list[str]) -> Conditions:
    """The confirmed conditions as the scheduler holds them, in the contract's shape."""
    conditions: Conditions = {key: profile[key] for key in (
        "unavailable_windows", "max_days_per_week", "max_daily_minutes", "max_daily_span", "lunch",
        "in_person_only") if profile.get(key) not in (None, False, [])}
    conditions["preferred_hours"] = {"weekday": 1, **profile["preferred_hours"]}
    conditions["cares"] = [care for care in CARES if care in cares]
    return conditions


def merge_conditions(raw_profile: dict[str, Any], conditions: Conditions) -> dict[str, Any]:
    """Add parsed conditions to a form profile; avoided times are added to the student's own."""
    fields = to_profile_fields(conditions)
    windows = [*raw_profile.get("unavailable_windows", []), *fields.pop("unavailable_windows", [])]
    return {**raw_profile, **fields, "unavailable_windows": windows}


def read_sentence(text: str) -> dict[str, Any]:
    """``llm.parse`` plus, for each clause, the profile fields the page can apply.

    Anything the scheduler would reject (a window ending before it starts, a lunch
    longer than its window...) is dropped here and listed under ``problems``.
    """
    result = parse(text)
    clauses = []
    for clause in result["clauses"]:
        fields, problems = check_condition_fields(to_profile_fields(clause["fields"]))
        cares = [care for care in CARES if care in (clause["fields"].get("cares") or [])]
        clauses.append({**clause, "profile_fields": fields, "cares": cares, "problems": problems})
    return {**result, "clauses": clauses}


def plan_from_sentence(text: str, raw_profile: dict[str, Any], snapshot_catalog: Any, **options: Any) -> dict[str, Any]:
    """The whole pipeline without the page: every recognised condition is taken as confirmed."""
    from .main import main  # main imports arrangement, which imports this module

    conditions = parse(text)["conditions"]
    fields, _ = check_condition_fields(to_profile_fields(conditions))
    profile = merge_conditions(raw_profile, {**fields, "cares": conditions.get("cares", [])})
    result = main(profile, snapshot_catalog, student_text=text, **options)
    result["conditions"] = conditions
    result["cares"] = [care for care in CARES if care in (conditions.get("cares") or CARES)]
    return result


class ExplainRegistry:
    """Recent recommendations, so the page can ask the local model for reasons afterwards.

    Holds references only (student sentence, profile, picks); nothing is written to disk.
    """

    def __init__(self, limit: int = 32):
        self._items: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._limit = limit
        self._lock = Lock()

    def add(self, student_text: str, profile: dict[str, Any], recommendation: dict[str, Any],
            items: dict[str, dict[str, Any]]) -> str:
        token = secrets.token_hex(12)
        picks = {axes: [items[cid] for cid in menu["picks"]] for axes, menu in recommendation["menus"].items()}
        with self._lock:
            self._items[token] = {"student_text": student_text, "profile": profile, "picks": picks, "done": {}}
            while len(self._items) > self._limit:
                self._items.popitem(last=False)
        return token

    def explain(self, token: str, axes: str) -> dict[str, Any] | None:
        from llm.explain import explain_detailed

        with self._lock:
            context = self._items.get(token)
        if context is None or axes not in context["picks"]:
            return None
        if axes not in context["done"]:
            context["done"][axes] = explain_detailed(
                context["student_text"], conditions_of(context["profile"], axes.split(",")),
                context["picks"][axes])
        return context["done"][axes]
