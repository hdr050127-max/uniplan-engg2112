"""The closest timetables when nothing meets every limit (docs/DESIGN.md, section 10.1).

Only used after the strict search finds nothing. The student's own limits (times they can't
make, days on campus, hours a day, lunch, in-person only, seats) become soft: every timetable
without a real clash is measured by how many limits it breaks and by how much, and the
closest ones are ranked with ``llm.rank`` among equals. A real clash (two required classes at
the same time) and the time needed to change buildings stay hard.

If the units clash even without the student's limits, one lecture is watched as a recording
instead (the one that misses the least class time), and the same search runs without it.
"""

from __future__ import annotations

import heapq
import re
from datetime import date, timedelta
from typing import Any

from llm.contracts import preferences_of
from llm.explain import explain

from .advisor import CANDIDATE_MAX, PICKS, conditions_of, distinct_first, rank_candidates
from .arrangement import (_apply_pins, add_item, build_shortlist, candidate_dict, candidate_from_ids,
                          group_label)
from .ranking import AXIS_SETS, axes_name, candidate_hash, common_teaching_weeks, dated_meetings, feature_key, rank_pool
from .schedule import (ClassOption, FastSearch, Meeting, SearchStats, _has_schedule, extract_class_options,
                       lunch_free)
from .wording import days_text, span_text

# Limits the student set; the rest of the profile (clashes, building changes) stays hard.
LIMITS = ("unavailable_windows", "max_days_per_week", "max_daily_minutes", "max_daily_span",
          "lunch", "in_person_only", "min_seats")
DAY_MINUTES = 180   # one extra campus day weighs like 3 hours of class when amounts are compared
SEAT_MINUTES = 60   # one class with too few seats weighs like an hour
STEP = 15           # amounts closer than this count as equal, and the ranking model decides
KEEP = 60           # closest timetables kept from the search
LECTURE = re.compile(r"lecture", re.I)


def soften(profile: dict[str, Any]) -> dict[str, Any]:
    """The profile without the student's limits."""
    return {**profile, "unavailable_windows": [], "max_days_per_week": None, "max_daily_minutes": None,
            "max_daily_span": None, "lunch": None, "in_person_only": False, "min_seats": 0}


def has_limits(profile: dict[str, Any]) -> bool:
    return any(profile.get(key) for key in LIMITS)


def _duration(minutes: float) -> str:
    hours, rest = divmod(round(minutes), 60)
    return (f"{hours} h" + (f" {rest} min" if rest else "")) if hours else f"{rest} min"


def _classes(count: int) -> str:
    return f"{count} class{'' if count == 1 else 'es'}"


MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def _dates_text(dates: list[date]) -> str:
    """"15 October", "15 and 22 October", "30 September and 7 October", or "4 dates"."""
    dates = sorted(set(dates))
    if len(dates) > 3:
        return f"{len(dates)} dates"
    if len({day.month for day in dates}) == 1:
        days = [str(day.day) for day in dates]
        head = days[0] if len(days) == 1 else f"{', '.join(days[:-1])} and {days[-1]}"
        return f"{head} {MONTHS[dates[0].month - 1]}"
    words = [f"{day.day} {MONTHS[day.month - 1]}" for day in dates]
    return f"{', '.join(words[:-1])} and {words[-1]}"


def _recurs(dates: set[date]) -> bool:
    """Three weeks or more: part of the weekly routine."""
    return len({day - timedelta(days=day.weekday()) for day in dates}) >= 3


def _when(slots: dict[tuple, set[date]], noun, suffix: str = "") -> str:
    """Slots that recur (3 weeks or more) by weekday, the rest by date: "2 classes on Mon and Wed
    before 9 am and 1 class on 15 October before 9 am". A weekday is only named for a weekly
    routine, so the words never suggest a class every week that is there once."""
    routine = {key: dates for key, dates in slots.items() if _recurs(dates)}
    parts = []
    if routine:
        days = sorted({day.isoweekday() for dates in routine.values() for day in dates})
        parts.append(f"{noun(len(routine))} on {days_text(days)}{suffix}")
    once = [day for key, dates in slots.items() if key not in routine for day in dates]
    if once:
        parts.append(f"{noun(len(slots) - len(routine))} on {_dates_text(once)}{suffix}")
    return " and ".join(parts)


def window_groups(profile: dict[str, Any]) -> list[tuple[int, int, set[int]]]:
    """Avoided times as the student set them: one limit per time range, over its days."""
    groups: dict[tuple[int, int], set[int]] = {}
    for window in profile.get("unavailable_windows") or []:
        groups.setdefault((window["start_min"], window["end_min"]), set()).add(window["weekday"])
    return [(start, end, days) for (start, end), days in groups.items()]


def measure(options: list[ClassOption], profile: dict[str, Any], weeks: int,
            in_person_groups: frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """Every limit these classes break: kind, amount (minutes a week) and the words for it.

    Fixed assessments are exempt, as in the strict search. ``in_person_groups``: activities
    that have an in-person class, so choosing an online one breaks "in-person only".
    """
    weeks = max(1, weeks)
    regular = [meeting for option in options for meeting in option.meetings if not meeting.is_fixed_assessment]
    found: list[dict[str, Any]] = []
    for start, end, days in window_groups(profile):
        minutes, slots = 0, {}
        for meeting in regular:
            if meeting.date.isoweekday() in days and meeting.start_min < end and start < meeting.end_min:
                minutes += min(end, meeting.end_min) - max(start, meeting.start_min)
                key = (meeting.group_id, meeting.date.isoweekday(), meeting.start_min, meeting.end_min)
                slots.setdefault(key, set()).add(meeting.date)
        if minutes:
            span = span_text(start, end)
            found.append({"kind": "unavailable_windows", "amount": minutes / weeks,
                          "text": _when(slots, _classes, f" {span}" if span else "")})
    by_date: dict[date, list[Meeting]] = {}
    for meeting in regular:
        by_date.setdefault(meeting.date, []).append(meeting)
    limit = profile.get("max_days_per_week")
    if limit:
        per_week: dict[date, set[date]] = {}
        for day, daily in by_date.items():
            if any(not meeting.is_online for meeting in daily):
                per_week.setdefault(day - timedelta(days=day.weekday()), set()).add(day)
        excess = sum(max(0, len(days) - limit) for days in per_week.values())
        if excess:
            most = max(len(days) for days in per_week.values())
            found.append({"kind": "max_days_per_week", "amount": excess / weeks * DAY_MINUTES,
                          "text": f"{most} days on campus a week, over the limit of {limit}"})
    for key, words in (("max_daily_minutes", "of class"), ("max_daily_span", "on campus")):
        limit = profile.get(key)
        if not limit:
            continue
        lengths = []
        for daily in by_date.values():
            if key == "max_daily_minutes":
                lengths.append(sum(meeting.end_min - meeting.start_min for meeting in daily))
            elif on_campus := [meeting for meeting in daily if not meeting.is_online]:
                lengths.append(max(m.end_min for m in on_campus) - min(m.start_min for m in on_campus))
        excess = sum(max(0, length - limit) for length in lengths)
        if excess:
            found.append({"kind": key, "amount": excess / weeks,
                          "text": f"Up to {_duration(max(lengths))} {words} a day, over the {_duration(limit)} limit"})
    lunch = profile.get("lunch")
    if lunch:
        missed = [day for day, daily in by_date.items()
                  if not lunch_free([(meeting.start_min, meeting.end_min) for meeting in daily], lunch)]
        if missed:
            by_weekday: dict[int, set[date]] = {}
            for day in missed:
                by_weekday.setdefault(day.isoweekday(), set()).add(day)
            usual = sorted(weekday for weekday, dates in by_weekday.items() if _recurs(dates))
            once = [day for weekday, dates in by_weekday.items() if weekday not in usual for day in dates]
            where = " and on ".join(([days_text(usual)] if usual else []) + ([_dates_text(once)] if once else []))
            found.append({"kind": "lunch", "amount": len(missed) / weeks * lunch["minutes"],
                          "text": f"No {lunch['minutes']} min lunch break on {where}"})
    if profile.get("in_person_only"):
        online = [meeting for meeting in regular if meeting.is_online and meeting.group_id in in_person_groups]
        if online:
            slots = {(m.group_id, m.date.isoweekday(), m.start_min) for m in online}
            found.append({"kind": "in_person_only", "amount": sum(m.end_min - m.start_min for m in online) / weeks,
                          "text": f"{len(slots)} online class{'' if len(slots) == 1 else 'es'}"})
    seats = profile.get("min_seats")
    if seats:
        low = [option for option in options if not option.pinned and any(
            meeting.available_seats.isdigit() and int(meeting.available_seats) < seats for meeting in option.meetings)]
        if low:
            found.append({"kind": "min_seats", "amount": len(low) * SEAT_MINUTES,
                          "text": f"{_classes(len(low))} with under {seats} seats left"})
    return found


def closeness(found: list[dict[str, Any]]) -> tuple[int, int]:
    """How far a timetable is from the limits: limits broken, then the amount in steps of STEP."""
    return len(found), int(sum(item["amount"] for item in found) // STEP)


def broken_line(found: list[dict[str, Any]]) -> str:
    """"Breaks one limit: 1 class on Wed before 9:30 am"."""
    if not found:
        return ""
    head = "Breaks one limit" if len(found) == 1 else f"Breaks {len(found)} limits"
    return f"{head}: " + "; ".join(item["text"] for item in found)


def _search(groups: list[tuple[str, tuple[ClassOption, ...]]], profile: dict[str, Any], weeks: tuple[date, ...],
            max_nodes: int) -> tuple[list[dict[str, Any]], FastSearch, SearchStats]:
    """The KEEP timetables closest to the limits, among all without a real clash."""
    stats = SearchStats()
    search = FastSearch(groups, soften(profile), len(weeks), stats)
    in_person = frozenset(group_id for group_id, options in groups
                          if any(not any(m.is_online for m in option.meetings) for option in options))
    # A heap of the KEEP closest so far, worst on top: (negated key, negated visit order, entry).
    kept: list[tuple[tuple, int, dict[str, Any]]] = []
    order = 0

    def sink(chosen: list[int], copies: int, span: int, duration: int, outside: int, attend: int) -> None:
        nonlocal order
        order += 1
        found = measure([search.flat[index][1] for index in chosen], profile, len(weeks), in_person)
        key = (*closeness(found), sum(item["amount"] for item in found))
        rank = (tuple(-value for value in key), -order)
        if len(kept) == KEEP and rank <= kept[0][:2]:
            return  # no closer than the farthest one kept (ties keep the first found)
        option_ids = search.schedule_of(chosen)
        candidate_id = candidate_hash(option_ids)
        features = search.features_of(span, duration, outside, attend)
        entry = {"key": feature_key(features), "features": features, "count": copies, "option_ids": option_ids,
                 "candidate_id": candidate_id, "found": found, "closeness": key[:2],
                 "patterns": {search.pattern_of(attend): {"option_ids": option_ids, "count": copies,
                                                          "candidate_id": candidate_id}}}
        heapq.heappush(kept, (*rank, entry))
        if len(kept) > KEEP:
            heapq.heappop(kept)

    search.run(sink, max_nodes)
    entries = [entry for *_, entry in sorted(kept, key=lambda item: item[:2], reverse=True)]
    return entries, search, stats


def _recording(groups: list[tuple[str, tuple[ClassOption, ...]]], profile: dict[str, Any], weeks: int,
               max_nodes: int) -> str | None:
    """The lecture to watch as a recording so the rest fits, missing the least class time."""
    best: tuple[float, str] | None = None
    for group_id, options in groups:
        if not LECTURE.search(group_id.rpartition("|")[2]) or not options:
            continue
        rest = [group for group in groups if group[0] != group_id]
        if rest and _has_schedule(rest, soften(profile), max_nodes):
            missed = min(sum(m.end_min - m.start_min for m in option.meetings) for option in options) / max(1, weeks)
            if best is None or (missed, group_id) < best:
                best = (missed, group_id)
    return best[1] if best else None


def nearest_timetables(meetings: list[dict[str, Any]], required_groups: dict[str, list[str]],
                       profile: dict[str, Any], *, pins: dict[str, list[str]] | None = None,
                       excluded: list[str] | None = None, student_text: str = "",
                       cares: list[str] | tuple[str, ...] = (), max_nodes: int = 5_000_000) -> dict[str, Any] | None:
    """A ranking result shaped like ``arrange_timetables``' for the closest timetables, or None.

    Each recommended pick carries ``broken`` (the line naming what it breaks) and, when a
    lecture is dropped, ``watch``; ``nearest`` says how the result was reached.
    """
    all_groups = extract_class_options(meetings, required_groups)
    groups = _apply_pins(all_groups, pins or {}, excluded or ())
    weeks = common_teaching_weeks(meetings)
    entries, search, stats = _search(groups, profile, weeks, max_nodes)
    watch = None
    if not entries:
        watch = _recording(groups, profile, len(weeks), max_nodes)
        if watch is None:
            return None
        groups = [group for group in groups if group[0] != watch]
        entries, search, stats = _search(groups, profile, weeks, max_nodes)
        if not entries:
            return None
    relaxed = soften(profile)
    options = {option.option_id: option for _, group in all_groups for option in group}
    ranking = rank_pool(entries, stats.feasible_count, relaxed, weeks,
                        meetings_for=lambda entry: dated_meetings(
                            candidate_from_ids(entry["candidate_id"], entry["option_ids"], options), profile))
    ranking.pop("_pool")
    ranking["search"] = stats.as_dict()
    eligible = dict(search.eligible)
    ranking["shortlist"] = build_shortlist(entries, options, eligible, relaxed, weeks)
    items = ranking["shortlist"]["items"]
    watch_text = f"Watch the recording of {group_label(watch)}" if watch else ""
    for entry in entries:
        for cid in [entry["candidate_id"], *(variant["candidate_id"] for variant in entry["patterns"].values())]:
            if cid in items:
                items[cid].update(broken=broken_line(entry["found"]), watch=watch_text, breaks=entry["found"])
    ranking["recommendation"] = _recommend(entries, profile, student_text, cares, items, options, eligible,
                                           relaxed, weeks, watch_text)
    ranking["nearest"] = {"watch": watch, "watch_text": watch_text,
                          "closest": {"limits": entries[0]["closeness"][0],
                                      "amount": round(sum(item["amount"] for item in entries[0]["found"]), 1)}}
    return ranking


def _recommend(entries: list[dict[str, Any]], profile: dict[str, Any], student_text: str,
               cares: list[str] | tuple[str, ...], items: dict[str, dict[str, Any]], options: dict[str, ClassOption],
               eligible: dict[str, tuple[ClassOption, ...]], relaxed: dict[str, Any], weeks: tuple[date, ...],
               watch_text: str) -> dict[str, Any]:
    """Like ``advisor.recommend``, but closest first: limits broken, then amount, then the ranking model."""
    built: dict[str, dict[str, Any]] = {}
    menus, sources, pools = {}, set(), {}
    for axes in AXIS_SETS:
        conditions = conditions_of(profile, axes, cares)
        ordered = tuple(conditions["cares"])
        closest = sorted(entries, key=lambda entry: entry["closeness"])
        chosen = distinct_first(closest, CANDIDATE_MAX, ordered)
        for entry in chosen:
            if entry["candidate_id"] not in built:
                built[entry["candidate_id"]] = candidate_dict(entry, options, profile)
        candidates = [built[entry["candidate_id"]] for entry in chosen]
        order, scores, source = rank_candidates(candidates, preferences_of(conditions, student_text))
        sources.add(source)
        position = {cid: index for index, cid in enumerate(order)}
        ranked = sorted(chosen, key=lambda entry: (entry["closeness"], position[entry["candidate_id"]]))
        picks = []
        # distinct_first may bring a skipped near-copy back at the end; keep the closest first.
        for entry in sorted(distinct_first(ranked, PICKS, ordered, copies=False), key=ranked.index):
            pick = add_item(items, entry, options, eligible, relaxed, weeks)
            pick.update(broken=broken_line(entry["found"]), watch=watch_text, breaks=entry["found"])
            picks.append(pick)
        menus[axes_name(axes)] = {
            "cares": list(ordered), "candidates": [entry["candidate_id"] for entry in chosen], "from_front": 0,
            "picks": [pick["candidate_id"] for pick in picks],
            "scores": [scores.get(pick["candidate_id"]) for pick in picks],
            "reasons": explain(student_text, conditions, picks, model=None, candidates=candidates),
        }
        pools[axes_name(axes)] = candidates
    return {"menus": menus, "ranker": " / ".join(sorted(sources)), "reasons_by": "template",
            "candidate_range": [1, CANDIDATE_MAX], "nearest": True, "_candidates": pools}
