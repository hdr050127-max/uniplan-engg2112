"""Extract linked class options and generate schedules satisfying hard rules."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from hashlib import sha1
import re
from typing import Any, Callable, Iterator

from .locations import building_location
from .wording import clock


class ScheduleDataError(Exception):
    """Required activity groups cannot be assembled from this snapshot."""


class SearchLimitError(Exception):
    """The complete search would exceed the prototype's resource limit."""


@dataclass(frozen=True)
class Meeting:
    date: date
    start_min: int
    end_min: int
    building_code: str
    is_online: bool
    option_id: str
    unit_code: str = ""
    group_id: str = ""
    activity_type: str = ""
    class_code: str = ""
    location_raw: str = ""
    is_fixed_assessment: bool = False
    available_seats: str = ""


@dataclass(frozen=True)
class ClassOption:
    option_id: str
    group_id: str
    meetings: tuple[Meeting, ...]
    is_full: bool
    # Fixed by the student (already enrolled, a friend's class...): skips seat/online filters.
    pinned: bool = False


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    option_ids: tuple[str, ...]
    meetings: tuple[Meeting, ...]
    # Schedules this one stands for: interchangeable classes are searched once.
    multiplicity: int = 1


@dataclass
class SearchStats:
    """Counters from a complete search, including rejected options and branches."""

    required_groups: int = 0
    total_options: int = 0
    eligible_options: int = 0
    full_options: int = 0
    unavailable_options: int = 0
    conflicting_options: int = 0
    rejected_branches: int = 0
    visited_nodes: int = 0
    feasible_count: int = 0
    preference_filtered: int = 0
    groups_without_options: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


ASSESSMENT_RE = re.compile(
    r"(?<![a-z])(?:assessments?|tests?|quizzes|quiz|exams?|examinations?)(?![a-z])",
    re.IGNORECASE,
)
PART_RE = re.compile(r"(.+)-P[1-9][0-9]*")


def is_fixed_assessment(row: dict[str, Any]) -> bool:
    """Recognize assessments by source labels, never by their duration alone."""
    labels = f"{row.get('activity_group', '')} {row.get('activity_type', '')}"
    return bool(ASSESSMENT_RE.search(labels))


def linked_option_id(row: dict[str, Any]) -> str:
    """Keep -P1/-P2 parts of the same class together across their dates."""
    option_id = row["option_id"]
    class_code = row.get("class_code", "")
    match = PART_RE.fullmatch(class_code)
    prefix, separator, suffix = option_id.rpartition("|")
    if match and separator and suffix == class_code:
        return f"{prefix}|{match.group(1)}"
    return option_id


def extract_class_options(
    rows: list[dict[str, Any]], required_groups: dict[str, list[str]],
) -> list[tuple[str, tuple[ClassOption, ...]]]:
    """Keep every dated meeting linked to one option in each required group."""
    by_option: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_option.setdefault(linked_option_id(row), []).append(row)

    by_group: dict[str, list[ClassOption]] = {}
    for option_id, option_rows in by_option.items():
        group_ids = {row["group_id"] for row in option_rows}
        unit_codes = {row["unit_code"] for row in option_rows}
        if len(group_ids) != 1 or len(unit_codes) != 1:
            raise ScheduleDataError(f"Option {option_id} spans more than one unit or activity.")
        meetings = tuple(sorted((Meeting(
            date=date.fromisoformat(row["date"]),
            start_min=int(row["start_min"]),
            end_min=int(row["end_min"]),
            building_code=row.get("building_code", ""),
            is_online="online" in (row.get("activity_type", "") + " " +
                                   row.get("location_raw", "")).lower(),
            option_id=row["option_id"],
            unit_code=row["unit_code"],
            group_id=row["group_id"],
            activity_type=row.get("activity_type", ""),
            class_code=row.get("class_code", ""),
            location_raw=row.get("location_raw", ""),
            is_fixed_assessment=is_fixed_assessment(row),
            available_seats=str(row.get("available_seats") or ""),
        ) for row in option_rows), key=lambda item: (item.date, item.start_min, item.end_min)))
        group_id = next(iter(group_ids))
        by_group.setdefault(group_id, []).append(ClassOption(
            option_id=option_id, group_id=group_id, meetings=meetings,
            is_full=any(row["status"] == "full" for row in option_rows),
        ))

    extracted = []
    seen_groups: set[str] = set()
    for unit_code, group_ids in required_groups.items():
        if not group_ids:
            raise ScheduleDataError(f"{unit_code} has no checked list of required activities.")
        for group_id in group_ids:
            if group_id in seen_groups:
                raise ScheduleDataError(f"Activity {group_id} is listed as required twice.")
            seen_groups.add(group_id)
            matching_rows = [row for row in rows if row["group_id"] == group_id]
            if not matching_rows or {row["unit_code"] for row in matching_rows} != {unit_code}:
                raise ScheduleDataError(f"Required activity {group_id} of {unit_code} is not in the timetable.")
            extracted.append((group_id, tuple(sorted(
                by_group.get(group_id, []), key=lambda item: item.option_id,
            ))))
    return extracted


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def overlaps_unavailable(meeting: Meeting, profile: dict[str, Any]) -> bool:
    return any(
        window["weekday"] == meeting.date.isoweekday() and
        _overlap(meeting.start_min, meeting.end_min,
                 window["start_min"], window["end_min"])
        for window in profile["unavailable_windows"]
    )


# Footpaths are longer than straight lines between building points.
DETOUR = 1.3


@lru_cache(maxsize=8192)
def walk_minutes(a: str, b: str, speed: int) -> int | None:
    """Estimated walk between two buildings at ``speed`` metres per minute."""
    first, second = building_location(a), building_location(b)
    if not first or not second or first["latitude"] is None or second["latitude"] is None:
        return None
    rad = math.pi / 180
    d_lat = (second["latitude"] - first["latitude"]) * rad
    d_lon = (second["longitude"] - first["longitude"]) * rad
    h = (math.sin(d_lat / 2) ** 2 + math.cos(first["latitude"] * rad) *
         math.cos(second["latitude"] * rad) * math.sin(d_lon / 2) ** 2)
    return math.ceil(2 * 6371000 * math.asin(math.sqrt(h)) * DETOUR / speed)


def required_gap(a: str, b: str, profile: dict[str, Any]) -> int:
    """Minutes needed between classes in two different known buildings."""
    need = profile.get("transition_min") or 0
    speed = profile.get("walk_speed")
    if speed:
        need = max(need, walk_minutes(a, b, speed) or 0)
    return need


def _fits(meetings: tuple[Meeting, ...], placed: tuple[Meeting, ...], profile: dict[str, Any]) -> bool:
    check_transfer = bool(profile.get("transition_min") or profile.get("walk_speed"))
    for meeting in meetings:
        if not meeting.is_fixed_assessment and overlaps_unavailable(meeting, profile):
            return False
        for other in placed:
            if meeting.date != other.date:
                continue
            if _overlap(meeting.start_min, meeting.end_min, other.start_min, other.end_min):
                return False
            if (check_transfer and not meeting.is_online and not other.is_online and
                    meeting.building_code and other.building_code and
                    meeting.building_code != other.building_code):
                gap = (other.start_min - meeting.end_min if meeting.end_min <= other.start_min
                       else meeting.start_min - other.end_min)
                if gap < required_gap(meeting.building_code, other.building_code, profile):
                    return False
    return True


def has_lifestyle_limits(profile: dict[str, Any]) -> bool:
    return any(profile.get(key) for key in (
        "max_days_per_week", "max_daily_minutes", "max_daily_span", "lunch"))


def lunch_free(intervals: list[tuple[int, int]], lunch: dict[str, int]) -> bool:
    """Whether some free stretch inside the lunch window is at least ``minutes`` long."""
    cursor, end, need = lunch["start_min"], lunch["end_min"], lunch["minutes"]
    for start, finish in sorted(intervals):
        if finish <= cursor:
            continue
        if start >= end:
            break
        if start - cursor >= need:
            return True
        cursor = max(cursor, finish)
    return end - cursor >= need


def lifestyle_allows(meetings: tuple[Meeting, ...] | list[Meeting], profile: dict[str, Any]) -> bool:
    """Daily and weekly limits for a whole schedule; fixed assessments are exempt.

    Every limit is monotone (adding a class can only break it), which lets the
    fast search prune partial schedules with exactly the same result.
    """
    if not has_lifestyle_limits(profile):
        return True
    regular = [meeting for meeting in meetings if not meeting.is_fixed_assessment]
    by_date: dict[date, list[Meeting]] = {}
    for meeting in regular:
        by_date.setdefault(meeting.date, []).append(meeting)
    if profile.get("max_days_per_week"):
        weeks: dict[date, set[date]] = {}
        for day, daily in by_date.items():
            if any(not meeting.is_online for meeting in daily):
                weeks.setdefault(day - timedelta(days=day.weekday()), set()).add(day)
        if any(len(days) > profile["max_days_per_week"] for days in weeks.values()):
            return False
    for daily in by_date.values():
        if (profile.get("max_daily_minutes") and
                sum(meeting.end_min - meeting.start_min for meeting in daily) > profile["max_daily_minutes"]):
            return False
        on_campus = [meeting for meeting in daily if not meeting.is_online]
        if (profile.get("max_daily_span") and on_campus and
                max(meeting.end_min for meeting in on_campus) -
                min(meeting.start_min for meeting in on_campus) > profile["max_daily_span"]):
            return False
        if profile.get("lunch") and not lunch_free(
                [(meeting.start_min, meeting.end_min) for meeting in daily], profile["lunch"]):
            return False
    return True


def eligible_options(
    groups: list[tuple[str, tuple[ClassOption, ...]]], profile: dict[str, Any],
    stats: SearchStats | None = None,
) -> list[tuple[str, tuple[ClassOption, ...]]]:
    """Drop options that fail on their own: full, avoided time, or self-conflict."""
    if stats is None:
        stats = SearchStats()
    eligible = []
    for group_id, options in groups:
        kept = []
        has_in_person = any(not any(meeting.is_online for meeting in option.meetings) for option in options)
        for option in options:
            stats.total_options += 1
            if option.is_full:
                stats.full_options += 1
                continue
            if not option.pinned and (
                    (profile.get("min_seats") and any(
                        meeting.available_seats.isdigit() and int(meeting.available_seats) < profile["min_seats"]
                        for meeting in option.meetings)) or
                    (profile.get("in_person_only") and has_in_person and
                     any(meeting.is_online for meeting in option.meetings))):
                stats.preference_filtered += 1
                continue
            if not lifestyle_allows(option.meetings, profile):
                stats.unavailable_options += 1
                continue
            if any(not _fits((meeting,), (), profile) for meeting in option.meetings):
                stats.unavailable_options += 1
                continue
            if any(not _fits((meeting,), option.meetings[:offset], profile)
                   for offset, meeting in enumerate(option.meetings)):
                stats.conflicting_options += 1
                continue
            kept.append(option)
            stats.eligible_options += 1
        eligible.append((group_id, tuple(kept)))
    stats.groups_without_options = tuple(
        group_id for group_id, options in eligible if not options
    )
    return eligible


def option_fits_with(option: ClassOption, others: tuple[Meeting, ...],
                     profile: dict[str, Any]) -> bool:
    """Whether an already eligible option can join these placed meetings."""
    return _fits(option.meetings, others, profile)


def option_signature(option: ClassOption, profile: dict[str, Any]) -> tuple:
    """Everything the hard checks and G/D/O read from an option.

    Options with equal signatures are interchangeable for feasibility and
    ranking (they differ only in room, or in building when no transfer
    buffer is set), so the search needs to try just one of them.
    """
    use_building = bool(profile.get("transition_min") or profile.get("walk_speed"))
    return tuple((meeting.date, meeting.start_min, meeting.end_min, meeting.is_online,
                  meeting.is_fixed_assessment, meeting.building_code if use_building else "")
                 for meeting in option.meetings)


def collapse_equivalent(
    eligible: list[tuple[str, tuple[ClassOption, ...]]], profile: dict[str, Any],
) -> list[tuple[str, tuple[tuple[ClassOption, int], ...]]]:
    """One representative (lowest option id) per interchangeable bucket, with its size."""
    collapsed = []
    for group_id, options in eligible:
        buckets: dict[tuple, list[ClassOption]] = {}
        for option in options:
            buckets.setdefault(option_signature(option, profile), []).append(option)
        collapsed.append((group_id, tuple(sorted(
            ((min(bucket, key=lambda item: item.option_id), len(bucket)) for bucket in buckets.values()),
            key=lambda pair: pair[0].option_id,
        ))))
    return collapsed


def generate_feasible_schedules(
    groups: list[tuple[str, tuple[ClassOption, ...]]], profile: dict[str, Any],
    *, max_nodes: int = 1_000_000, stats: SearchStats | None = None,
) -> Iterator[Candidate]:
    """Choose exactly one option per required group using dated hard checks.

    Interchangeable options are searched once and reported through
    ``Candidate.multiplicity``, so counts stay exact while large course loads
    stay within the node budget. The search is lazy. If its node limit is
    exceeded, it raises instead of returning a misleading partial ranking.
    """
    if max_nodes < 1:
        raise ValueError("max_nodes must be positive")
    if not groups:
        raise ScheduleDataError("Required activities are missing, so no timetable can be built.")
    if stats is None:
        stats = SearchStats()
    stats.required_groups = len(groups)
    eligible = eligible_options(groups, profile, stats)
    ordered = sorted(collapse_equivalent(eligible, profile), key=lambda item: (len(item[1]), item[0]))

    def search(index: int, selected: tuple[ClassOption, ...], placed: tuple[Meeting, ...],
               multiplicity: int) -> Iterator[Candidate]:
        stats.visited_nodes += 1
        if stats.visited_nodes > max_nodes:
            busiest = max(eligible, key=lambda item: len(item[1]))[0]
            raise SearchLimitError(
                "There are too many combinations to check them all. "
                f"{busiest.split('|')[0].split('-')[0]} {busiest.rpartition('|')[2]} has the most classes to choose from. "
                "Add times you can't make, or drop a unit, and try again.")
        if index == len(ordered):
            if not lifestyle_allows(placed, profile):
                stats.rejected_branches += 1
                return
            option_ids = tuple(sorted(option.option_id for option in selected))
            candidate_id = sha1("|".join(option_ids).encode("utf-8")).hexdigest()[:16]
            stats.feasible_count += multiplicity
            yield Candidate(candidate_id, option_ids, tuple(sorted(
                placed, key=lambda item: (item.date, item.start_min, item.end_min),
            )), multiplicity)
            return
        _, options = ordered[index]
        for option, copies in options:
            if _fits(option.meetings, placed, profile):
                yield from search(index + 1, selected + (option,),
                                  placed + option.meetings, multiplicity * copies)
            else:
                stats.rejected_branches += 1

    yield from search(0, (), (), 1)


WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def option_slots(options: tuple[ClassOption, ...], limit: int = 4) -> list[str]:
    """Readable weekly slots of each option's first meeting, for explanations."""
    slots: list[str] = []
    for option in options:
        if not option.meetings:
            continue
        first = option.meetings[0]
        label = f"{WEEKDAY_NAMES[first.date.isoweekday() - 1]} {clock(first.start_min)} to {clock(first.end_min)}"
        if label not in slots:
            slots.append(label)
    return slots[:limit] + ([f"{len(slots)} times in all"] if len(slots) > limit else [])


class _Found(Exception):
    pass


def _has_schedule(groups: list[tuple[str, tuple[ClassOption, ...]]],
                  profile: dict[str, Any], max_nodes: int) -> bool:
    """Stop at the first feasible schedule (FastSearch is defined later in this module)."""
    def stop(*_: Any) -> None:
        raise _Found

    try:
        FastSearch(groups, profile, 1).run(stop, max_nodes)
    except _Found:
        return True
    return False


def find_conflict_core(
    groups: list[tuple[str, tuple[ClassOption, ...]]], profile: dict[str, Any],
    *, max_nodes: int = 200_000,
) -> dict[str, Any] | None:
    """Name a minimal set of required groups that cannot be scheduled together.

    A deletion filter drops each group in turn and keeps it dropped while the
    rest stays infeasible, so every group left is necessary for the conflict.
    The result explains an empty search; it never relaxes a constraint. Returns
    None when the groups are feasible, a group is already empty, or a check
    exceeds its search budget.
    """
    eligible = eligible_options(groups, profile)
    if not eligible or any(not options for _, options in eligible):
        return None
    try:
        if _has_schedule(groups, profile, max_nodes):
            return None
        core = list(groups)
        for item in list(core):
            trial = [group for group in core if group is not item]
            if trial and not _has_schedule(trial, profile, max_nodes):
                core = trial
        # Name the cause: add the student's own rules back one family at a time.
        plain = {**profile, "transition_min": 0, "walk_speed": None, "max_days_per_week": None,
                 "max_daily_minutes": None, "max_daily_span": None, "lunch": None,
                 "in_person_only": False, "min_seats": 0}
        limits = {key: profile.get(key) for key in (
            "max_days_per_week", "max_daily_minutes", "max_daily_span", "lunch")}
        filters = {"in_person_only": profile.get("in_person_only", False),
                   "min_seats": profile.get("min_seats", 0)}
        if not _has_schedule(core, plain, max_nodes):
            reason = "time_overlap"
        elif not _has_schedule(core, {**plain, **limits}, max_nodes):
            reason = "limits"
        elif not _has_schedule(core, {**plain, **filters}, max_nodes):
            reason = "filters"
        else:
            reason = "transition_buffer"
    except SearchLimitError:
        return None
    by_id = dict(eligible)
    return {
        "group_ids": [group_id for group_id, _ in core],
        "reason": reason,
        "slots": {group_id: option_slots(by_id[group_id]) for group_id, _ in core},
    }


class FastSearch:
    """Bitset search that keeps G, D and O up to date as classes are added.

    Feasibility between two classes is pairwise (same-date overlap or a short
    building transfer), so it is precomputed once as bitsets; forward
    checking drops a branch as soon as any remaining group has no compatible
    class. Features never need a full meeting list:

    * O (minutes outside preferred hours) adds up class by class;
    * D is the number of in-person dates in a bitmask;
    * G = sum over dates of (latest end - earliest start) - total class time,
      because placed classes never overlap.

    ``run`` calls ``sink`` once per representative schedule; ``schedule_of``
    turns its class indices back into option ids when the sink needs them.
    """

    def __init__(self, groups: list[tuple[str, tuple[ClassOption, ...]]], profile: dict[str, Any],
                 weeks: int, stats: SearchStats | None = None):
        if not groups:
            raise ScheduleDataError("Required activities are missing, so no timetable can be built.")
        self.stats = stats if stats is not None else SearchStats()
        self.stats.required_groups = len(groups)
        self.weeks = weeks
        self.eligible = eligible_options(groups, profile, self.stats)
        collapsed = sorted(collapse_equivalent(self.eligible, profile),
                           key=lambda item: (len(item[1]), item[0]))
        self.group_ids = [group_id for group_id, _ in collapsed]
        self.flat = [(index, option, copies) for index, (_, options) in enumerate(collapsed)
                     for option, copies in options]
        dates = sorted({meeting.date for _, option, _ in self.flat for meeting in option.meetings})
        date_index = {day: index for index, day in enumerate(dates)}
        self.weekday_masks = [0] * 8
        for day, index in date_index.items():
            self.weekday_masks[day.isoweekday()] |= 1 << index
        preferred = profile["preferred_hours"]
        self.meetings, self.duration, self.outside, self.attend = [], [], [], []
        for _, option, _ in self.flat:
            rows, duration, outside, attend = [], 0, 0, 0
            for meeting in option.meetings:
                length = meeting.end_min - meeting.start_min
                inside = max(0, min(meeting.end_min, preferred["end_min"]) -
                             max(meeting.start_min, preferred["start_min"]))
                rows.append((date_index[meeting.date], meeting.start_min, meeting.end_min))
                duration += length
                outside += length - inside
                if not meeting.is_online:
                    attend |= 1 << date_index[meeting.date]
            self.meetings.append(rows)
            self.duration.append(duration)
            self.outside.append(outside)
            self.attend.append(attend)
        self.group_mask = [0] * len(collapsed)
        for position, (group, _, _) in enumerate(self.flat):
            self.group_mask[group] |= 1 << position
        self.compatible = [0] * len(self.flat)
        for a, (group_a, option_a, _) in enumerate(self.flat):
            for b in range(a + 1, len(self.flat)):
                group_b, option_b, _ = self.flat[b]
                if group_a != group_b and _fits(option_a.meetings, option_b.meetings, profile):
                    self.compatible[a] |= 1 << b
                    self.compatible[b] |= 1 << a
        self.stats.groups_without_options = tuple(
            group_id for group_id, options in self.eligible if not options)
        self._dates = len(dates)
        # Lifestyle limits: per-date bookkeeping for regular (non-assessment) classes.
        self.limits = {key: profile.get(key) for key in (
            "max_days_per_week", "max_daily_minutes", "max_daily_span", "lunch")}
        self.limits_on = has_lifestyle_limits(profile)
        mondays = sorted({day - timedelta(days=day.weekday()) for day in dates})
        week_of = {index: mondays.index(day - timedelta(days=day.weekday())) for day, index in date_index.items()}
        self.week_masks = [0] * len(mondays)
        for index, week in week_of.items():
            self.week_masks[week] |= 1 << index
        self.regular, self.regular_attend, self.option_weeks = [], [], []
        for _, option, _ in self.flat:
            rows = [(date_index[meeting.date], meeting.start_min, meeting.end_min, meeting.is_online)
                    for meeting in option.meetings if not meeting.is_fixed_assessment]
            attend = 0
            for date_position, _, _, online in rows:
                if not online:
                    attend |= 1 << date_position
            self.regular.append(rows)
            self.regular_attend.append(attend)
            self.option_weeks.append(sorted({week_of[row[0]] for row in rows if not row[3]}))

    def schedule_of(self, chosen: list[int]) -> tuple[str, ...]:
        return tuple(sorted(self.flat[index][1].option_id for index in chosen))

    def features_of(self, span: int, duration: int, outside: int, attend: int) -> dict[str, float]:
        return {"gap_min": (span - duration) / self.weeks,
                "campus_days": attend.bit_count() / self.weeks,
                "outside_min": outside / self.weeks}

    def pattern_of(self, attend: int, min_weeks: int = 3) -> str:
        return "".join(str(day) for day in range(1, 8)
                       if (attend & self.weekday_masks[day]).bit_count() >= min_weeks)

    def run(self, sink: Callable[[list[int], int, int, int, int, int], None],
            max_nodes: int = 1_000_000) -> None:
        """Visit every feasible representative schedule: sink(chosen, copies, span, duration, outside, attend)."""
        stats, groups = self.stats, len(self.group_mask)
        if not all(self.group_mask):
            return
        low, high, used = [0] * self._dates, [0] * self._dates, [0] * self._dates
        chosen: list[int] = []
        state = [0, 0, 0, 0]  # span, duration, outside, attend
        limit_days = self.limits["max_days_per_week"]
        limit_minutes = self.limits["max_daily_minutes"]
        limit_span = self.limits["max_daily_span"]
        lunch = self.limits["lunch"]
        class_minutes = [0] * self._dates
        campus_low, campus_high, campus_used = [0] * self._dates, [0] * self._dates, [0] * self._dates
        intervals: list[list[tuple[int, int]]] = [[] for _ in range(self._dates)]
        regular_attend = [0]

        def apply_limits(position: int) -> tuple[bool, tuple]:
            """Add one class to the limit bookkeeping; report whether every limit still holds."""
            log = []
            for date, start, end, online in self.regular[position]:
                log.append((date, campus_low[date], campus_high[date], online, end - start))
                class_minutes[date] += end - start
                intervals[date].append((start, end))
                if not online:
                    if campus_used[date]:
                        campus_low[date] = min(campus_low[date], start)
                        campus_high[date] = max(campus_high[date], end)
                    else:
                        campus_low[date], campus_high[date] = start, end
                    campus_used[date] += 1
            before = regular_attend[0]
            regular_attend[0] |= self.regular_attend[position]
            ok = True
            for date in {entry[0] for entry in log}:
                if ((limit_minutes and class_minutes[date] > limit_minutes) or
                        (limit_span and campus_used[date] and
                         campus_high[date] - campus_low[date] > limit_span) or
                        (lunch and not lunch_free(intervals[date], lunch))):
                    ok = False
                    break
            if ok and limit_days:
                ok = all((regular_attend[0] & self.week_masks[week]).bit_count() <= limit_days
                         for week in self.option_weeks[position])
            return ok, (log, before)

        def undo_limits(token: tuple) -> None:
            log, before = token
            regular_attend[0] = before
            for date, old_low, old_high, online, length in reversed(log):
                class_minutes[date] -= length
                intervals[date].pop()
                if not online:
                    campus_used[date] -= 1
                    campus_low[date], campus_high[date] = old_low, old_high

        def visit(group: int, allowed: int, copies: int) -> None:
            stats.visited_nodes += 1
            if stats.visited_nodes > max_nodes:
                busiest = max(self.eligible, key=lambda item: len(item[1]))[0]
                raise SearchLimitError(
                    "There are too many combinations to check them all. "
                    f"{busiest.split('|')[0].split('-')[0]} {busiest.rpartition('|')[2]} has the most classes to choose from. "
                    "Add times you can't make, pin a class, or drop a unit, and try again.")
            if group == groups:
                stats.feasible_count += copies
                sink(chosen, copies, state[0], state[1], state[2], state[3])
                return
            options = allowed & self.group_mask[group]
            # Classes ruled out by earlier choices count as rejected branches, as in the plain search.
            stats.rejected_branches += (self.group_mask[group] & ~allowed).bit_count()
            while options:
                lowest = options & -options
                position = lowest.bit_length() - 1
                options ^= lowest
                narrowed = allowed & self.compatible[position]
                if not all(narrowed & self.group_mask[later] for later in range(group + 1, groups)):
                    stats.rejected_branches += 1
                    continue
                token = None
                if self.limits_on:
                    ok, token = apply_limits(position)
                    if not ok:
                        undo_limits(token)
                        stats.rejected_branches += 1
                        continue
                undo = []
                for date, start, end in self.meetings[position]:
                    undo.append((date, low[date], high[date]))
                    if used[date]:
                        before = high[date] - low[date]
                        low[date] = min(low[date], start)
                        high[date] = max(high[date], end)
                        state[0] += high[date] - low[date] - before
                    else:
                        low[date], high[date] = start, end
                        state[0] += end - start
                    used[date] += 1
                saved = (state[1], state[2], state[3])
                state[1] += self.duration[position]
                state[2] += self.outside[position]
                state[3] |= self.attend[position]
                chosen.append(position)
                visit(group + 1, narrowed, copies * self.flat[position][2])
                chosen.pop()
                if token is not None:
                    undo_limits(token)
                state[1], state[2], state[3] = saved
                for date, old_low, old_high in reversed(undo):
                    used[date] -= 1
                    restored = (old_high - old_low) if used[date] else 0
                    state[0] += restored - (high[date] - low[date])
                    low[date], high[date] = old_low, old_high

        visit(0, (1 << len(self.flat)) - 1, 1)
