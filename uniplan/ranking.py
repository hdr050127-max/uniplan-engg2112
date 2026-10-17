"""Explainable rule-based timetable ranking and its sensitivity checks.

The learned ranking lives in ``preference.py``; both share these features.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from hashlib import sha1
from typing import Any, Callable, Iterable

from .schedule import Candidate, FastSearch, Meeting, overlaps_unavailable
from .locations import building_location


SCALES = {"gap": 300.0, "campus_days": 5.0, "outside_hours": 120.0}
EQUAL_WEIGHTS = {key: 1 / 3 for key in SCALES}


def common_teaching_weeks(meetings: list[dict[str, Any]]) -> tuple[date, ...]:
    """Use one week set for all candidates, including their empty weeks."""
    dates = (date.fromisoformat(row["date"]) for row in meetings)
    return tuple(sorted({day - timedelta(days=day.weekday()) for day in dates}))


def extract_schedule_features(
    candidate: Candidate, profile: dict[str, Any], teaching_weeks: tuple[date, ...],
) -> dict[str, float]:
    """Return weekly mean G, D and O on identical teaching weeks."""
    if not teaching_weeks:
        raise ValueError("At least one teaching week is required")
    by_date: dict[date, list[Meeting]] = defaultdict(list)
    for meeting in candidate.meetings:
        by_date[meeting.date].append(meeting)

    gap_total = 0
    outside_total = 0
    attendance_dates: set[date] = set()
    preferred = profile["preferred_hours"]
    for day, daily in by_date.items():
        daily.sort(key=lambda item: (item.start_min, item.end_min))
        gap_total += sum(max(0, next_item.start_min - item.end_min)
                         for item, next_item in zip(daily, daily[1:]))
        if any(not meeting.is_online for meeting in daily):
            attendance_dates.add(day)
        for meeting in daily:
            inside = max(0, min(meeting.end_min, preferred["end_min"]) -
                         max(meeting.start_min, preferred["start_min"]))
            outside_total += meeting.end_min - meeting.start_min - inside

    weeks = len(teaching_weeks)
    return {
        "gap_min": gap_total / weeks,
        "campus_days": len(attendance_dates) / weeks,
        "outside_min": outside_total / weeks,
    }


FEATURE_KEYS = ("gap_min", "campus_days", "outside_min")
POOL_LIMIT = 200_000


def scaled_features(features: dict[str, float],
                    scales: dict[str, float] = SCALES) -> dict[str, float]:
    """x = (G/300, D/5, O/120): the unitless inputs shared by every ranker."""
    return {
        "gap": features["gap_min"] / scales["gap"],
        "campus_days": features["campus_days"] / scales["campus_days"],
        "outside_hours": features["outside_min"] / scales["outside_hours"],
    }


def feature_key(features: dict[str, float]) -> tuple[float, float, float]:
    """Schedules with the same key are indistinguishable to every ranker."""
    return tuple(round(features[key], 6) for key in FEATURE_KEYS)  # type: ignore[return-value]


def _score(features: dict[str, float], weights: dict[str, float],
           scales: dict[str, float] = SCALES) -> tuple[float, dict[str, float]]:
    scaled = scaled_features(features, scales)
    contributions = {key: weights[key] * value for key, value in scaled.items()}
    return sum(contributions.values()), contributions


def _order(score: float, features: dict[str, float], candidate_id: str) -> tuple[float, float, str]:
    """Sort key for rule rankings.

    Equal scores (e.g. a zero weight) fall back to the total scaled cost, so a
    tie never prefers a schedule that is worse on an ignored feature.
    """
    return (round(score, 12), round(sum(scaled_features(features).values()), 12), candidate_id)


def top_profiles(pool: list[dict[str, Any]], weights: dict[str, float], limit: int = 3,
                 scales: dict[str, float] = SCALES) -> list[tuple[float, float, float]]:
    """Feature keys of the best distinct profiles under one weight/scale setting."""
    ordered = sorted(pool, key=lambda entry: _order(
        _score(entry["features"], weights, scales)[0], entry["features"], entry["candidate_id"]))
    return [entry["key"] for entry in ordered[:limit]]


AXIS_FEATURE = {"gap": "gap_min", "campus_days": "campus_days", "outside_hours": "outside_min"}
AXIS_SETS = tuple(tuple(axis for index, axis in enumerate(SCALES) if mask >> index & 1)
                  for mask in range(7, 0, -1))
WEEKDAY_MIN_WEEKS = 3


def axes_name(axes: tuple[str, ...]) -> str:
    return ",".join(axes)


def weekday_pattern(candidate: Candidate, min_weeks: int = WEEKDAY_MIN_WEEKS) -> str:
    """Weekdays with in-person classes in at least ``min_weeks`` teaching weeks, e.g. "235".

    One-off assessments or a single practical do not define the weekly routine.
    """
    weeks: dict[int, set[date]] = defaultdict(set)
    for meeting in candidate.meetings:
        if not meeting.is_online:
            weeks[meeting.date.isoweekday()].add(meeting.date - timedelta(days=meeting.date.weekday()))
    return "".join(str(day) for day in sorted(weeks) if len(weeks[day]) >= min_weeks)


def _axis_values(entry: dict[str, Any], axes: tuple[str, ...]) -> tuple[float, ...]:
    return tuple(round(entry["features"][AXIS_FEATURE[axis]], 6) for axis in axes)


def pareto_front(pool: list[dict[str, Any]],
                 axes: tuple[str, ...] = tuple(SCALES)) -> list[dict[str, Any]]:
    """Profiles that no other profile matches or beats on every chosen axis.

    These are the only schedules worth comparing for anyone who wants less of
    each chosen feature; the rest are worse on every count than one of them.
    Profiles tied on the chosen axes collapse to the one best on the others.
    Sorting first means each profile only needs checking against the front.
    """
    if not axes or any(axis not in SCALES for axis in axes):
        raise ValueError("choose at least one known axis")
    others = tuple(axis for axis in SCALES if axis not in axes)
    best: dict[tuple[float, ...], dict[str, Any]] = {}
    for entry in pool:
        key = _axis_values(entry, axes)
        current = best.get(key)
        if current is None or ((_axis_values(entry, others), entry["candidate_id"]) <
                               (_axis_values(current, others), current["candidate_id"])):
            best[key] = entry
    front: list[dict[str, Any]] = []
    for entry in sorted(best.values(), key=lambda item: _axis_values(item, axes)):
        values = _axis_values(entry, axes)
        if not any(all(a <= b for a, b in zip(_axis_values(kept, axes), values)) for kept in front):
            front.append(entry)
    return front


def scale_sensitivity(pool: list[dict[str, Any]], weights: dict[str, float],
                      limit: int = 3, factor: float = 0.25) -> dict[str, Any]:
    """Proposal check: how many top-three profiles change when one scale moves ±25%."""
    base = set(top_profiles(pool, weights, limit))
    changes = []
    for key in SCALES:
        for direction in (-1, 1):
            scales = {**SCALES, key: SCALES[key] * (1 + direction * factor)}
            moved = set(top_profiles(pool, weights, limit, scales))
            changes.append({"scale": key, "factor": 1 + direction * factor,
                            "replaced": len(base - moved)})
    worst = max((item["replaced"] for item in changes), default=0)
    return {"factor": factor, "max_replaced": worst, "stable": worst == 0,
            "changes": changes, "compared": min(limit, len(pool))}


def dated_meetings(candidate: Candidate, profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Preserve the actual teaching dates; a weekly template would hide changes."""
    return [{
        "date": meeting.date.isoformat(),
        "weekday": meeting.date.isoweekday(),
        "start_min": meeting.start_min,
        "end_min": meeting.end_min,
        "unit_code": meeting.unit_code,
        "group_id": meeting.group_id,
        "option_id": meeting.option_id,
        "activity_type": meeting.activity_type,
        "class_code": meeting.class_code,
        "building_code": meeting.building_code,
        "building_location": (building_location(meeting.building_code)
                              if meeting.building_code and not meeting.is_online else None),
        "location_raw": meeting.location_raw,
        "is_online": meeting.is_online,
        "is_fixed_assessment": meeting.is_fixed_assessment,
        "available_seats": meeting.available_seats,
        "unavailable_exception": meeting.is_fixed_assessment and overlaps_unavailable(meeting, profile),
    } for meeting in candidate.meetings]


def candidate_hash(option_ids: Iterable[str]) -> str:
    return sha1("|".join(sorted(option_ids)).encode("utf-8")).hexdigest()[:16]


def pool_from_search(search: FastSearch, *, max_nodes: int = 5_000_000) -> tuple[list[dict[str, Any]], bool]:
    """One entry per distinct G/D/O profile, with one schedule per weekday pattern.

    Each profile's representative is the first schedule the search reaches
    (deterministic: groups and classes are visited in a fixed order).
    """
    pool: dict[tuple[float, float, float], dict[str, Any]] = {}
    truncated = False

    def sink(chosen: list[int], copies: int, span: int, duration: int, outside: int, attend: int) -> None:
        nonlocal truncated
        features = search.features_of(span, duration, outside, attend)
        key = feature_key(features)
        entry = pool.get(key)
        if entry is None:
            if len(pool) >= POOL_LIMIT:
                truncated = True
                return
            entry = pool[key] = {"key": key, "features": features, "count": 0,
                                 "option_ids": search.schedule_of(chosen), "patterns": {}}
        entry["count"] += copies
        pattern = search.pattern_of(attend)
        variant = entry["patterns"].get(pattern)
        if variant is None:
            variant = entry["patterns"][pattern] = {"option_ids": search.schedule_of(chosen), "count": 0}
        variant["count"] += copies

    search.run(sink, max_nodes)
    for entry in pool.values():
        entry["candidate_id"] = candidate_hash(entry["option_ids"])
        for variant in entry["patterns"].values():
            variant["candidate_id"] = candidate_hash(variant["option_ids"])
    return list(pool.values()), truncated


def rank_pool(pool: list[dict[str, Any]], feasible_count: int, profile: dict[str, Any],
              teaching_weeks: tuple[date, ...], *, limit: int = 3, truncated: bool = False,
              meetings_for: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    """Both rule baselines over distinct profiles, plus the sensitivity check.

    Recommendations are distinct feature profiles: schedules that differ only
    in an interchangeable class are counted under one profile instead of
    filling all three places. ``_pool`` is private and must not be serialized.
    """
    if limit < 1:
        raise ValueError("limit must be positive")

    def top(weights: dict[str, float]) -> list[dict[str, Any]]:
        ordered = sorted(pool, key=lambda entry: _order(
            _score(entry["features"], weights)[0], entry["features"], entry["candidate_id"]))
        items = []
        for rank, entry in enumerate(ordered[:limit], start=1):
            score, contributions = _score(entry["features"], weights)
            item = {"candidate_id": entry["candidate_id"], "option_ids": list(entry["option_ids"]),
                    "features": entry["features"], "score": score, "contributions": contributions,
                    "rank": rank, "equivalent_count": entry["count"]}
            if meetings_for is not None:
                item["meetings"] = meetings_for(entry)
            items.append(item)
        return items

    return {
        "method": "student_weighted_baseline",
        "feasible_count": feasible_count,
        "distinct_profile_count": len(pool),
        "pool_truncated": truncated,
        "teaching_week_count": len(teaching_weeks),
        "teaching_weeks": [week.isoformat() for week in teaching_weeks],
        "scales": SCALES,
        "weights": profile["weights"],
        "top": top(profile["weights"]),
        "equal_weight_top": top(EQUAL_WEIGHTS),
        "sensitivity": scale_sensitivity(pool, profile["weights"], limit) if pool else None,
        "_pool": pool,
    }


def rank_schedules(
    candidates: Iterable[Candidate], profile: dict[str, Any],
    teaching_weeks: tuple[date, ...], *, limit: int = 3,
) -> dict[str, Any]:
    """Rank explicit candidates (small inputs and tests); the app uses ``FastSearch``.

    Each profile keeps its lowest candidate id and that schedule's meetings.
    """
    pool: dict[tuple[float, float, float], dict[str, Any]] = {}
    count = 0
    for candidate in candidates:
        count += candidate.multiplicity
        features = extract_schedule_features(candidate, profile, teaching_weeks)
        key = feature_key(features)
        entry = pool.setdefault(key, {"key": key, "features": features, "count": 0,
                                      "candidate_id": candidate.candidate_id,
                                      "option_ids": candidate.option_ids, "patterns": {},
                                      "_candidate": candidate})
        entry["count"] += candidate.multiplicity
        if candidate.candidate_id < entry["candidate_id"]:
            entry.update(candidate_id=candidate.candidate_id, option_ids=candidate.option_ids,
                         _candidate=candidate)
        variant = entry["patterns"].setdefault(weekday_pattern(candidate), {
            "candidate_id": candidate.candidate_id, "option_ids": candidate.option_ids, "count": 0})
        variant["count"] += candidate.multiplicity
        if candidate.candidate_id < variant["candidate_id"]:
            variant.update(candidate_id=candidate.candidate_id, option_ids=candidate.option_ids)
    return rank_pool(list(pool.values()), count, profile, teaching_weeks, limit=limit,
                     meetings_for=lambda entry: dated_meetings(entry["_candidate"], profile))
