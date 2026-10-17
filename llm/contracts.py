"""The interfaces between the three work blocks. Owned by the coordinator window.

The pipeline is:

    student sentence --parse()--> conditions --(uniplan scheduler)--> candidates
        --rank()--> ordered candidates --explain()--> one reason per pick

Blocks may change what happens inside their functions, but not these shapes.
A change here goes through the coordinator so every block moves together.
"""
from __future__ import annotations

from typing import Literal, TypedDict

# The 9 condition types a clause can be mapped to (see llm/parse/labels.py for definitions).
Label = Literal["blocked_time", "max_days", "max_daily_hours", "lunch", "in_person_only",
                "prefer_fewer_days", "prefer_less_waiting", "prefer_no_early_late", "other"]

# The three things a student may care about when choosing between valid timetables.
# Same names as the existing UI's "我在意" switches.
Care = Literal["campus_days", "gap", "outside_hours"]


class Window(TypedDict):
    weekday: int        # 1 = Monday ... 7 = Sunday
    start_min: int      # minutes after midnight
    end_min: int


class Lunch(TypedDict):
    start_min: int
    end_min: int
    minutes: int        # free minutes needed inside the window


class Conditions(TypedDict, total=False):
    """What the parser extracts. Hard fields use the scheduler's profile field names,
    so they can be merged into a profile as they are; anything missing means "no limit"."""
    # Hard: the scheduler never breaks these.
    unavailable_windows: list[Window]
    max_days_per_week: int | None
    max_daily_minutes: int | None
    max_daily_span: int | None
    lunch: Lunch | None
    in_person_only: bool
    # Soft: used only to order valid timetables.
    preferred_hours: Window          # weekday is ignored; the student's comfortable day
    cares: list[Care]                # most important first: cares[0] is what the student cares
                                     # about most (the parser keeps the order the sentence states them)


class Clause(TypedDict):
    text: str
    label: Label
    fields: Conditions               # what this clause contributed


class ParseResult(TypedDict):
    clauses: list[Clause]
    conditions: Conditions           # all clauses merged
    unrecognised: list[str]          # clauses labelled "other", shown to the student


class Candidate(TypedDict, total=False):
    """One valid timetable, as produced by uniplan.arrangement (shortlist items)."""
    candidate_id: str
    option_ids: list[str]
    features: dict[str, float]       # gap_min, campus_days, outside_min (weekly averages)
    pattern: str                     # weekdays with classes, e.g. "1235"
    meetings: list[dict]             # dated meetings: date, weekday, start_min, end_min, unit_code,
                                     # group_id, class_code, building_code, is_online, ...


class Preferences(TypedDict, total=False):
    student_text: str
    cares: list[Care]                # same order as Conditions.cares; never re-sort it
    preferred_hours: Window


class Ranked(TypedDict):
    candidate_id: str
    score: float                     # higher is better for this student


# What llm.rank.contributions(candidate, preferences) returns: how much each feature (names as in
# llm/rank/model.json "features") adds to that candidate's score; the values sum to its score up to
# a constant. explain() may use the difference between two candidates' contributions to say why the
# first pick beats the second; the reason text is still fact-checked against the timetable.
Contributions = dict[str, float]


HARD_FIELDS = ("unavailable_windows", "max_days_per_week", "max_daily_minutes",
               "max_daily_span", "lunch", "in_person_only")
SOFT_FIELDS = ("preferred_hours", "cares")


def to_profile_fields(conditions: Conditions) -> dict:
    """The hard conditions plus preferred hours, in the scheduler's profile format."""
    fields = {key: conditions[key] for key in HARD_FIELDS if conditions.get(key) not in (None, False, [])}
    if conditions.get("preferred_hours"):
        hours = conditions["preferred_hours"]
        fields["preferred_hours"] = {"start_min": hours["start_min"], "end_min": hours["end_min"]}
    return fields


def preferences_of(conditions: Conditions, student_text: str = "") -> Preferences:
    prefs: Preferences = {"student_text": student_text, "cares": list(conditions.get("cares") or [])}
    if conditions.get("preferred_hours"):
        prefs["preferred_hours"] = conditions["preferred_hours"]
    return prefs
