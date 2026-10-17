"""Turn one labelled clause into Conditions fields, and merge clauses. Rules only.

The label (from the classifier) decides which field a clause fills; these rules
read the numbers: weekdays, clock times, parts of the day, counts of days and hours.
"""
from __future__ import annotations

import re

from llm.contracts import Clause, Conditions, Window
from llm.parse.text import WEEKDAYS, find_days, find_parts, find_times, normalize

DEFAULT_HOURS = (540, 1080)          # the scheduler's default comfortable day, 9:00-18:00
DEFAULT_LUNCH = (690, 840, 30)       # 30 free minutes between 11:30 and 14:00

_COMMITMENT = re.compile(
    r"打工|上班|兼职|工作|实习|送|接|照顾|带孩子|带娃|孩子|训练|比赛|练习|排练|教会|礼拜|祷告|开会|家教|补习|辅导|通勤|"
    r"\b(?:work|job|shift|intern\w*|pick\s?up|drop\s?off|kids?|child\w*|daughter|son|training|practice|game|"
    r"church|mosque|temple|pray\w*|tutor(?:ing|s)?|commut\w*|appointment|volunteer\w*|gym|club|rehearsal)\b")
_NEGATION = re.compile(r"不|没|别|无法|忙|有事|\b(?:can'?t|cannot|can not|not|no|nothing|don'?t|won'?t|busy|"
                       r"unavailable|avoid|hate|never|unable)\b")
_ONLY = re.compile(r"只|仅|才|\b(?:only|not until|no earlier)\b")
_AVAILABLE = re.compile(r"有空|可以|能来|能上|空闲|\b(?:free|available|ok|okay|fine)\b")
_FINISH = re.compile(r"结束|下课|走|离开|回家|离校|放学|\b(?:leave|finish\w*|done|home|out by|wrap up)\b")
_START = re.compile(r"再|开始|上课|来学校|到学校|\b(?:start\w*|begin\w*|come in|arrive|class(?:es)? (?:after|from))\b")
_EXCEPT_ONLY = re.compile(r"除了.*都(?:不|没)|(?:其他|其余|别的).*(?:不|没)|\bexcept\b.*\b(?:no|not|can'?t)\b"
                          r"|(?:other days|the rest).*\b(?:no|not|can'?t|busy)\b")
_SPAN = re.compile(r"在校|在学校|待|呆|留在|\b(?:on campus|at uni|at school|at campus|stay\w*|spend\w*|be there)\b")
_OFF = re.compile(r"休息|空出|\b(?:off|free days?)\b")
_HOURS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:个)?\s*(半)?\s*(?:小时|钟头|hours?\b|hrs?\b|h\b)")
_HALF_HOUR = re.compile(r"半(?:个)?小时|half an? hour|half hour")
_AN_HOUR = re.compile(r"\ban hour\b")
_MINUTES = re.compile(r"(\d+)\s*(?:分钟|mins?\b|minutes?\b)")
_DAYS = re.compile(r"(\d+)\s*(?:天|days?\b|次|times\b)")


def _complement(windows: list[tuple[int, int]]) -> list[tuple[int, int]]:
    gaps, cursor = [], 0
    for start, end in sorted(windows):
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    return gaps + ([(cursor, 1440)] if cursor < 1440 else [])


def _avoid(kind: str, a: int, b: int, text: str, available: bool) -> list[tuple[int, int]]:
    """The minutes to keep free for one time expression."""
    negative = bool(_NEGATION.search(text) or _COMMITMENT.search(text))
    if kind == "before":
        flip = (_FINISH.search(text) or _ONLY.search(text) or available
                or _COMMITMENT.search(text) and a > 720 and not _NEGATION.search(text))
        return [(a, 1440)] if flip else [(0, a)]
    if kind == "after":
        flip = _ONLY.search(text) or available or _START.search(text) and not negative
        return [(0, a)] if flip else [(a, 1440)]
    window = (a, b) if kind == "range" else (0, min(a + 60, 1440)) if a < 720 else (a, 1440)
    return _complement([window]) if available else [window]


def _windows(text: str) -> list[Window]:
    days = find_days(text)
    times = find_times(text)
    parts = [part for part in find_parts(text)
             if not any(part[0] < end and start < part[1] for start, end, *_ in times)]
    available = bool(_ONLY.search(text) or _AVAILABLE.search(text) and not _NEGATION.search(text))
    items: list[tuple[int, str, list]] = [(start, "day", value) for start, _, value in days]
    items += [(start, "time", _avoid(kind, a, b, text, available)) for start, _, kind, a, b in times]
    items += [(start, "time", _complement([window]) if available else [window]) for start, _, window in parts]
    # Pair weekdays with the times written next to them: "周一上午、周三下午", "before 10am on Mondays".
    groups: list[list] = []                    # [days, windows, times_came_first]
    for _, kind, value in sorted(items, key=lambda item: item[0]):
        if kind == "day":
            if groups and not groups[-1][0] and groups[-1][1]:
                groups[-1][0].extend(value)
            elif groups and not groups[-1][1]:
                groups[-1][0].extend(value)
            else:
                groups.append([list(value), [], False])
        elif groups:
            groups[-1][1].extend(value)
        else:
            groups.append([[], list(value), True])
    for index, group in enumerate(groups):
        if index and group[0] and not group[1] and groups[index - 1][2]:
            group[1] = list(groups[index - 1][1])
    named = sorted({day for _, _, value in days for day in value})
    # "只想周二周四来" frees the named days; "only after 10am on Tuesdays" frees a time on them.
    days_free = bool(days) and bool(_EXCEPT_ONLY.search(text) or any(
        min((item for item in items if item[0] > match.start()), key=lambda item: item[0])[1] == "day"
        for match in _ONLY.finditer(text) if match.start() < days[0][0]))
    result: list[tuple[int, int, int]] = []
    if days_free:
        result += [(day, 0, 1440) for day in WEEKDAYS if day not in named]
    for group_days, windows, _ in groups:
        for day in group_days or ([] if days_free else WEEKDAYS):
            if windows:
                result += [(day, start, end) for start, end in windows]
            elif not days_free:
                result.append((day, 0, 1440))
    return merge_windows(result)


def merge_windows(raw) -> list[Window]:
    merged: list[list[int]] = []
    for day, start, end in sorted({(w[0], w[1], w[2]) if isinstance(w, tuple) else
                                   (w["weekday"], w["start_min"], w["end_min"]) for w in raw}):
        if start >= end:
            continue
        if merged and merged[-1][0] == day and start <= merged[-1][2]:
            merged[-1][2] = max(merged[-1][2], end)
        else:
            merged.append([day, start, end])
    return [{"weekday": day, "start_min": start, "end_min": end} for day, start, end in merged]


def _minutes(text: str) -> int | None:
    if found := _HOURS.search(text):
        return round((float(found.group(1)) + (0.5 if found.group(2) else 0)) * 60)
    if _HALF_HOUR.search(text):
        return 30
    if _AN_HOUR.search(text):
        return 60
    if found := _MINUTES.search(text):
        return int(found.group(1))
    return None


def _preferred(text: str) -> tuple[int, int] | None:
    windows = [window for _, _, kind, a, b in find_times(text)
               for window in _avoid(kind, a, b, text, bool(_ONLY.search(text)))]
    if not windows:
        return None
    start = max([end for start, end in windows if start == 0], default=DEFAULT_HOURS[0])
    end = min([start for start, end in windows if end == 1440], default=DEFAULT_HOURS[1])
    return (start, end) if start < end else None


def _lunch(text: str):
    window = DEFAULT_LUNCH[:2]
    for _, _, kind, a, b in find_times(text):
        if kind == "range":
            window = (a, b)
        elif kind == "point":
            window = (a, min(a + 60, 1440))
    length = window[1] - window[0]
    minutes = _minutes(text) or (length if length <= 60 else DEFAULT_LUNCH[2])
    return {"start_min": window[0], "end_min": window[1], "minutes": max(10, min(minutes, length))}


def fields(label: str, clause: str) -> Conditions:
    """What one clause with this label contributes. Empty when the numbers are missing."""
    text = normalize(clause)
    if label == "blocked_time":
        windows = _windows(text)
        return {"unavailable_windows": windows} if windows else {}
    if label == "max_days":
        if found := _DAYS.search(text):
            count = int(found.group(1))
            count = 5 - count if _OFF.search(text) else count
            return {"max_days_per_week": max(1, min(count, 7))}
        return {}
    if label == "max_daily_hours":
        minutes = _minutes(text)
        if minutes is None:
            return {}
        if _SPAN.search(text):
            return {"max_daily_span": max(60, min(minutes, 900))}
        return {"max_daily_minutes": max(60, min(minutes, 720))}
    if label == "lunch":
        return {"lunch": _lunch(text)}
    if label == "in_person_only":
        return {"in_person_only": True}
    if label == "prefer_fewer_days":
        return {"cares": ["campus_days"]}
    if label == "prefer_less_waiting":
        return {"cares": ["gap"]}
    if label == "prefer_no_early_late":
        hours = _preferred(text)
        extra = {"preferred_hours": {"weekday": 1, "start_min": hours[0], "end_min": hours[1]}} if hours else {}
        return {"cares": ["outside_hours"], **extra}      # weekday is ignored for preferred_hours
    return {}


def merge(clauses: list[Clause]) -> Conditions:
    """All clauses together. Limits keep the strictest value; lists are joined without repeats."""
    merged: Conditions = {}
    for clause in clauses:
        for key, value in clause["fields"].items():
            if key == "unavailable_windows":
                merged[key] = merge_windows([*merged.get(key, []), *value])
            elif key == "cares":
                merged[key] = [*merged.get(key, []), *(care for care in value if care not in merged.get(key, []))]
            elif key in ("max_days_per_week", "max_daily_minutes", "max_daily_span") and merged.get(key):
                merged[key] = min(merged[key], value)
            elif key == "in_person_only":
                merged[key] = merged.get(key, False) or value
            else:
                merged[key] = value
    return merged
