"""Timetable features for ranking, computed from a candidate's dated meetings.

Standard library only: rank() calls this at run time. Every feature is "less is better"
except ``friday_free`` and ``online_share``, which the model learns a sign for.
Weekly figures are averages over the teaching weeks of the whole candidate list, so
every candidate of one student shares the same denominator (as uniplan.ranking does).

The student's own comfortable hours (``preferred_hours``) decide what counts as an
early or late class; without them it is 09:00-18:00, the scheduler's default.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

DEFAULT_HOURS = {"start_min": 540, "end_min": 1080}
ROUTINE_WEEKS = 3        # a slot repeating in at least 3 weeks is part of the weekly routine

NAMES = ("campus_days", "gap_h", "outside_h", "early_h", "late_h", "earliest_start",
         "latest_end", "longest_day_h", "heaviest_day_h", "friday_free", "building_changes",
         "single_class_days", "online_share")

LABELS = {  # for tables and reports
    "campus_days": "到校天数（天/周）", "gap_h": "课间空等（小时/周）",
    "outside_h": "早晚课（小时/周，按个人时段）", "early_h": "早课（小时/周）", "late_h": "晚课（小时/周）",
    "earliest_start": "最早上课（点）", "latest_end": "最晚下课（点）",
    "longest_day_h": "最长的一天（在校小时）", "heaviest_day_h": "上课最多的一天（小时）",
    "friday_free": "周五不用到校（周的比例）", "building_changes": "换楼次数（次/周）",
    "single_class_days": "只为一节课到校（天/周）", "online_share": "线上课比例",
}


def week_of(day: str) -> date:
    value = date.fromisoformat(day)
    return value - timedelta(days=value.weekday())


def teaching_weeks(candidates: list[dict]) -> int:
    """Number of distinct teaching weeks across every candidate's meetings."""
    weeks = {week_of(m["date"]) for c in candidates for m in c.get("meetings") or ()}
    return max(len(weeks), 1)


def hours_of(prefs: dict | None) -> dict[str, int]:
    hours = (prefs or {}).get("preferred_hours") or DEFAULT_HOURS
    return {"start_min": int(hours["start_min"]), "end_min": int(hours["end_min"])}


def routine_bounds(meetings: list[dict]) -> tuple[int, int] | None:
    """Earliest start and latest end of in-person classes that repeat every week."""
    slots = Counter((m["weekday"], m["start_min"], m["end_min"]) for m in meetings if not m["is_online"])
    routine = [slot for slot, count in slots.items() if count >= ROUTINE_WEEKS] or list(slots)
    if not routine:
        return None
    return min(s[1] for s in routine), max(s[2] for s in routine)


def timetable_features(meetings: list[dict], weeks: int, hours: dict[str, int]) -> dict[str, float]:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for meeting in meetings:
        by_date[meeting["date"]].append(meeting)

    gap = early = late = online = total = 0
    campus_dates = set()
    single = changes = 0
    longest: dict[date, int] = defaultdict(int)     # week -> longest in-person span that week
    heaviest: dict[date, int] = defaultdict(int)    # week -> most class minutes in one day
    busy_fridays = set()
    for day, daily in by_date.items():
        daily.sort(key=lambda m: (m["start_min"], m["end_min"]))
        gap += sum(max(0, b["start_min"] - a["end_min"]) for a, b in zip(daily, daily[1:]))
        week = week_of(day)
        minutes = 0
        for m in daily:
            length = m["end_min"] - m["start_min"]
            minutes += length
            total += length
            online += length if m["is_online"] else 0
            early += max(0, min(m["end_min"], hours["start_min"]) - m["start_min"])
            late += max(0, m["end_min"] - max(m["start_min"], hours["end_min"]))
        heaviest[week] = max(heaviest[week], minutes)
        here = [m for m in daily if not m["is_online"]]
        if not here:
            continue
        campus_dates.add(day)
        if here[0]["weekday"] == 5:
            busy_fridays.add(week)
        longest[week] = max(longest[week], max(m["end_min"] for m in here) - here[0]["start_min"])
        if len({(m["unit_code"], m["group_id"]) for m in here}) == 1:
            single += 1
        buildings = [m.get("building_code") for m in here]
        changes += sum(1 for a, b in zip(buildings, buildings[1:]) if a and b and a != b)

    bounds = routine_bounds(meetings) or (hours["start_min"], hours["end_min"])
    return {
        "campus_days": len(campus_dates) / weeks,
        "gap_h": gap / 60 / weeks,
        "outside_h": (early + late) / 60 / weeks,
        "early_h": early / 60 / weeks,
        "late_h": late / 60 / weeks,
        "earliest_start": bounds[0] / 60,
        "latest_end": bounds[1] / 60,
        "longest_day_h": sum(longest.values()) / 60 / weeks,
        "heaviest_day_h": sum(heaviest.values()) / 60 / weeks,
        "friday_free": 1 - len(busy_fridays) / weeks,
        "building_changes": changes / weeks,
        "single_class_days": single / weeks,
        "online_share": online / total if total else 0.0,
    }


def candidate_features(candidates: list[dict], prefs: dict | None) -> list[dict[str, float]]:
    """Features for every candidate of one student, in the same order.

    A candidate without meetings (an older caller) falls back to the three scheduler
    features it carries; the rest take neutral values.
    """
    weeks, hours = teaching_weeks(candidates), hours_of(prefs)
    result = []
    for candidate in candidates:
        if candidate.get("meetings"):
            result.append(timetable_features(candidate["meetings"], weeks, hours))
            continue
        given = candidate.get("features") or {}
        outside = given.get("outside_min", 0.0) / 60
        result.append({**{name: 0.0 for name in NAMES},
                       "campus_days": given.get("campus_days", 0.0), "gap_h": given.get("gap_min", 0.0) / 60,
                       "outside_h": outside, "early_h": outside / 2, "late_h": outside / 2,
                       "earliest_start": hours["start_min"] / 60, "latest_end": hours["end_min"] / 60})
    return result
