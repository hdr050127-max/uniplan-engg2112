"""English notes beside the clauses of a sentence (docs/DESIGN.md, section 7), and the times,
days and windows the scheduler's messages name.

Notes come from ``llm.parse.clarify.describe_clause``; ``describe`` below stands in only if that
fails. Questions and their options are worded by ``llm.parse.clarify`` and shown as given.
"""

from __future__ import annotations

from typing import Any, Callable

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
CARE_NOTE = {"campus_days": "Fewer days on campus, if possible",
             "gap": "Less waiting between classes, if possible",
             "outside_hours": "Fewer early or late classes, if possible"}
# What each label means when the clause gives no usable time or number.
LABEL_NOTE = {
    "blocked_time": "Times you can't make, but no days or times were given",
    "max_days": "A cap on days a week, but no number was given",
    "max_daily_hours": "A cap on hours a day, but no number was given",
    "lunch": "A lunch break, but no time was given",
    "in_person_only": "In-person classes only",
    "prefer_fewer_days": CARE_NOTE["campus_days"],
    "prefer_less_waiting": CARE_NOTE["gap"],
    "prefer_no_early_late": CARE_NOTE["outside_hours"],
    "other": "Not something a timetable can use",
}
UNUSABLE = "The time or number here doesn't add up, so it is left out"


def clock(minute: int) -> str:
    """540 -> "9 am", 1110 -> "6:30 pm", 720 -> "12 pm"."""
    if minute >= 1440:
        return "midnight"
    hour, rest = divmod(minute, 60)
    return f"{hour % 12 or 12}{f':{rest:02d}' if rest else ''} {'am' if hour < 12 else 'pm'}"


def join(words: list[str]) -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def days_text(days: list[int]) -> str:
    days = sorted(set(days))
    if days == [1, 2, 3, 4, 5]:
        return "weekdays"
    if days == list(range(1, 8)):
        return "any day"
    if days == [6, 7]:
        return "weekends"
    if len(days) >= 3 and days == list(range(days[0], days[-1] + 1)):
        return f"{DAYS[days[0] - 1]} to {DAYS[days[-1] - 1]}"
    return join([DAYS[day - 1] for day in days])


def span_text(start: int, end: int) -> str:
    """"" for the whole day, else "before 10 am", "after 6 pm" or "2 pm to 6 pm"."""
    if start <= 0 and end >= 1439:
        return ""
    if start <= 0:
        return f"before {clock(end)}"
    if end >= 1439:
        return f"after {clock(start)}"
    return f"{clock(start)} to {clock(end)}"


def windows_text(windows: list[dict[str, int]]) -> str:
    """"Tue and Thu after 6 pm", "Fri", "weekdays before 10 am; Wed 2 pm to 6 pm"."""
    by_time: dict[tuple[int, int], list[int]] = {}
    for window in windows:
        by_time.setdefault((window["start_min"], window["end_min"]), []).append(window["weekday"])
    parts = [" ".join(filter(None, (days_text(days), span_text(start, end))))
             for (start, end), days in sorted(by_time.items(), key=lambda item: (min(item[1]), item[0]))]
    return "; ".join(parts)


def _hours(minutes: int) -> str:
    value = minutes / 60
    return f"{value:g} hour{'' if value == 1 else 's'}"


def describe(fields: dict[str, Any], cares: list[str] = ()) -> list[str]:
    """Short phrases for form fields and cares, hard conditions first."""
    phrases = []
    if fields.get("unavailable_windows"):
        phrases.append(f"Not available {windows_text(fields['unavailable_windows'])}")
    if fields.get("max_days_per_week"):
        count = fields["max_days_per_week"]
        phrases.append(f"At most {count} day{'' if count == 1 else 's'} on campus a week")
    if fields.get("max_daily_minutes"):
        phrases.append(f"At most {_hours(fields['max_daily_minutes'])} of class a day")
    if fields.get("max_daily_span"):
        phrases.append(f"At most {_hours(fields['max_daily_span'])} on campus a day")
    if fields.get("lunch"):
        lunch = fields["lunch"]
        phrases.append(f"{lunch['minutes']} min for lunch between {clock(lunch['start_min'])} and {clock(lunch['end_min'])}")
    if fields.get("in_person_only"):
        phrases.append("In-person classes only")
    hours = fields.get("preferred_hours")
    if hours and "outside_hours" in cares:
        phrases.append(f"Fewer classes before {clock(hours['start_min'])} or after {clock(hours['end_min'])}, if possible")
    elif hours:
        phrases.append(f"Classes between {clock(hours['start_min'])} and {clock(hours['end_min'])}, if possible")
    phrases += [CARE_NOTE[care] for care in cares if care in CARE_NOTE and not (hours and care == "outside_hours")]
    return phrases


def sentence(phrases: list[str]) -> str:
    """Phrases as one line: "Not available Fri; at most 3 days on campus a week"."""
    return "; ".join(phrase if index == 0 else phrase[0].lower() + phrase[1:]
                     for index, phrase in enumerate(phrases))


def fallback_note(label: str, applied: dict[str, Any]) -> str:
    """The note from the fields the page can apply (``uniplan.advisor._applicable``)."""
    if label == "other":
        return LABEL_NOTE["other"]
    if applied["problems"]:
        return UNUSABLE
    phrases = describe(applied["profile_fields"], applied["cares"])
    return sentence(phrases) if phrases else LABEL_NOTE.get(label, label)


def clause_describer() -> Callable[[dict[str, Any]], str] | None:
    """``llm.parse.clarify.describe_clause`` when the parsing window has provided it."""
    try:
        from llm.parse.clarify import describe_clause
    except ImportError:
        return None
    return describe_clause
