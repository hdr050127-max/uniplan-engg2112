"""Restate what parse() understood, and ask a few questions back. Rules only, standard library.

All text is English, following the copy rules in docs/DESIGN.md section 7, and built from the
fields by fixed phrases (no free model text): describe_clause() is the margin note written next to
each clause, and the summary ("Read as: ...") joins those notes. Questions come in this order, at
most MAX_QUESTIONS per sentence:
  low_confidence  a second opinion (the plain-Python linear model) disagrees with the label; when
                  the label came from the linear model itself, its top two are closer than MARGIN;
                  Wording the boundary rules read differently from the label is asked about too
                  ("early classes are fine" labelled as a preference).
  hard_or_soft    a time without a weekday, said in a tone between "can't" and "would rather", or
                  labelled against rule 5 / the part-of-day rule;
  missing_value   the label needs a time or a number the clause does not give;
  offer           at most MAX_OFFERS things the scheduler can do that the student did not mention.
The first option of every question is what parse() already assumed. Thresholds and triggers were
chosen on the validation set, test v1 and test v2 only (llm/parse/clarify_eval.py).
"""
from __future__ import annotations

import re
from typing import Callable

from llm.contracts import Conditions, Option, ParseResult, Question
from llm.parse.extract import fields
from llm.parse.labels import HEDGES
from llm.parse.text import DAY_NAMES, find_times, named_days, normalize

MAX_QUESTIONS = 3
MAX_OFFERS = 2
# Both chosen on the validation split (clarify_eval.py grids them):
DISAGREE_MIN = 0.3    # model run time: ask when the linear model gives its other label at least this; the
                      # highest value that still catches as many wrong validation clauses as no threshold
MARGIN = 0.1          # linear run time: ask when its top two probabilities are closer than this; the value
                      # that interrupts about as often on validation as the model run time does

NOT_USABLE = "Not something a timetable can use"
# What a label means for a clause that gives no number or time (an option's text).
_OPTION = {"blocked_time": "Not available at that time", "max_days": "A limit on days a week",
           "max_daily_hours": "A limit on hours a day", "lunch": "Time for lunch",
           "in_person_only": "Only in-person classes", "prefer_fewer_days": "As few days on campus as possible",
           "prefer_less_waiting": "As little waiting between classes as possible",
           "prefer_no_early_late": "Fewer early or late classes, if possible", "other": NOT_USABLE}
# The margin note when the label needs a number or time the clause does not give.
_MISSING = {"blocked_time": "Busy, but no day or time given",
            "max_days": "A limit on days a week, but no number given",
            "max_daily_hours": "A limit on hours a day, but no number given"}
_EARLY = re.compile(r"early|morning|8\s?am|早|上午")
_LATE = re.compile(r"late|evening|night|晚")
# Soft wording that is not one of the hedge words of rule 5 ("would be nice", "hoping", ...).
_SOFT = re.compile(r"would be (?:nice|great|good|ideal|amazing|lovely)|if (?:that'?s|that is|it'?s) (?:doable|possible|ok)|"
                   r"if that works|\bhoping\b|\bi hope\b|\bhopefully\b|i'?d love|would love|nice to have|"
                   r"if you can manage|best if|\bideal\b|preferabl|最好能|如果方便|方便的话|要是能|就好了|的话就好|能.{0,6}就好")
# A reason or outside commitment next to a hedge word makes "can't" and "would rather" both plausible.
_REASON = re.compile(r"because|\bcos\b|'cos|\bcause\b|\bsince\b|因为|由于|要去|得去|"
                     r"打工|上班|兼职|实习|送|接|照顾|孩子|训练|比赛|教会|家教|通勤|"
                     r"\b(?:work\w*|job|shift|intern\w*|pick\w* up|drop\w* off|kids?|son|daughter|child\w*|"
                     r"training|practice|game|church|mosque|pray\w*|tutor\w*|commut\w*|appointment|volunteer\w*|"
                     r"gym|club|rehearsal|bus|train|carer|caring|grandma|grandpa|mum|mom|dad)\b")
# Saying a time, day or gap is fine is not a request ("early classes are fine", "gaps don't bother me").
_FINE = re.compile(r"\b(?:fine|ok|okay|perfect|no problem|happy with|good with)\b|don'?t mind|doesn'?t matter|"
                   r"don'?t (?:bother|worry)|doesn'?t (?:bother|worry)|would actually be nice|\b(?:want|like|love)\b[^.]{0,12}"
                   r"\b(?:big|long) gaps?|没问题|都可以|无所谓|没事|没有冲突|不介意|可以接受")
_EXCEPT_DAY = re.compile(r"\bexcept\b|\bbut not\b|除了|除开")
_DAY_COUNT = re.compile(r"\d+\s*-?\s*(?:[a-z]+\s+)?(?:天|days?\b)|\b(?:once|twice)\b")      # "4 campus days"
_PERIOD = re.compile(r"(?<!early )(?<!late )\b(?:mornings?|afternoons?|arvos?|evenings?|nights?)\b|早上|上午|中午|下午|晚上")
_REQUEST = re.compile(r"\b(?:no|not|don'?t|can'?t|cannot|won'?t|avoid|keep|clear|off|out|never|skip)\b|n't\b|"
                      r"别|不要|不想|不选|不能|不行|拒绝|空出|空着|免")
_ONLINE = re.compile(r"线上|网课|在线|录播|zoom|\bonline\b|\brecorded\b|\bremote\b")
_LIKES = re.compile(r"可以|没问题|喜欢|想|好|\b(?:fine|ok|okay|good|great|prefer\w*|want|like|love|happy|works?)\b")


def _clock(minutes: int) -> str:
    """6 pm, 9:30 am."""
    if minutes == 1440:
        return "midnight"
    hour, minute = divmod(minutes, 60)
    return f"{hour % 12 or 12}{f':{minute:02d}' if minute else ''} {'am' if hour < 12 else 'pm'}"


def _days(days: list[int]) -> str:
    """Tue and Thu, Mon to Thu, on weekends."""
    days = sorted(days)
    if days == [6, 7]:
        return "on weekends"
    if len(days) >= 3 and days == list(range(days[0], days[-1] + 1)):
        return f"{DAY_NAMES[days[0]]} to {DAY_NAMES[days[-1]]}"
    names = [DAY_NAMES[day] for day in days]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _span(start: int, end: int) -> str:
    if (start, end) == (0, 1440):
        return ""
    if start == 0:
        return f"before {_clock(end)}"
    if end == 1440:
        return f"after {_clock(start)}"
    return f"from {_clock(start)} to {_clock(end)}"


def _not_available(windows: list[dict]) -> str:
    by_time: dict[tuple[int, int], list[int]] = {}
    for window in windows:
        by_time.setdefault((window["start_min"], window["end_min"]), []).append(window["weekday"])
    groups = []
    for (start, end), days in sorted(by_time.items(), key=lambda item: (min(item[1]), item[0])):
        day_text = "" if sorted(days) == [1, 2, 3, 4, 5] else _days(days)
        groups.append(" ".join(part for part in (day_text, _span(start, end)) if part) or "Mon to Fri")
    return "Not available " + "; ".join(groups)


def _hours(minutes: int) -> str:
    hours = minutes / 60
    return f"{hours:g} hour{'' if hours == 1 else 's'}"


def _soft_hours(start: int, end: int) -> str:
    if start == 540 and end != 1080:
        return f"Done by {_clock(end)}, if possible"
    if end == 1080 and start != 540:
        return f"No classes before {_clock(start)}, if possible"
    return f"Classes between {_clock(start)} and {_clock(end)}, if possible"


def _early_late(text: str) -> str:
    norm = normalize(text)
    early, late = bool(_EARLY.search(norm)), bool(_LATE.search(norm))
    return f"Fewer {'early' if early and not late else 'late' if late and not early else 'early or late'} classes, if possible"


def _phrases(found: Conditions, text: str) -> list[str]:
    """English phrases for the fields one clause gives, in sentence case."""
    parts = []
    if found.get("unavailable_windows"):
        parts.append(_not_available(found["unavailable_windows"]))
    if found.get("max_days_per_week"):
        days = found["max_days_per_week"]
        parts.append(f"At most {days} day{'' if days == 1 else 's'} a week")
    if found.get("max_daily_minutes"):
        parts.append(f"At most {_hours(found['max_daily_minutes'])} of class a day")
    if found.get("max_daily_span"):
        parts.append(f"At most {_hours(found['max_daily_span'])} on campus a day")
    if found.get("lunch"):
        lunch = found["lunch"]
        parts.append(f"{lunch['minutes']} min for lunch between {_clock(lunch['start_min'])} and {_clock(lunch['end_min'])}")
    if found.get("in_person_only"):
        parts.append("Only in-person classes")
    cares = found.get("cares") or []
    if found.get("preferred_hours"):
        parts.append(_soft_hours(found["preferred_hours"]["start_min"], found["preferred_hours"]["end_min"]))
    elif "outside_hours" in cares:
        parts.append(_early_late(text))
    if "campus_days" in cares:
        parts.append("As few days on campus as possible")
    if "gap" in cares:
        parts.append("As little waiting between classes as possible")
    return parts


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text[:1].isalpha() else text


def _join(parts: list[str]) -> str:
    return "; ".join([parts[0]] + [_lower_first(part) for part in parts[1:]])


def describe_clause(clause: dict) -> str:
    """One margin note for a clause, written next to the student's words: "Not available Tue and Thu
    after 6 pm", "At most 5 hours of class a day", "Not something a timetable can use"."""
    if clause["label"] == "other":
        return NOT_USABLE
    parts = _phrases(clause["fields"], clause["text"])
    return _join(parts) if parts else _MISSING.get(clause["label"], _OPTION[clause["label"]])


def summary(result: ParseResult) -> str:
    """"Read as: ..." from the margin notes of the clauses, then the ones a timetable cannot use."""
    notes = list(dict.fromkeys(describe_clause(c) for c in result["clauses"] if c["label"] != "other"))
    unread = ", ".join(f"“{clause}”" for clause in result["unrecognised"])
    if not notes:
        return f"{NOT_USABLE}: {unread}." if unread else "Read as: nothing a timetable can use."
    return "Read as: " + "; ".join(_lower_first(note) for note in notes) + "." + (
        f" {NOT_USABLE}: {unread}." if unread else "")


def _reading(label: str, clause: str) -> str:
    """What choosing this label would mean for this clause, as an option's text."""
    if label == "other":
        return NOT_USABLE
    parts = _phrases(fields(label, clause), clause)
    return _join(parts) if parts else _OPTION[label]


def _relabel(label: str, clause: str) -> Option:
    return {"text": _reading(label, clause), "label": label, "fields": {}}


def ambiguous_tone(clause: str) -> bool:
    text = normalize(clause)
    hedged = any(word in text for word in HEDGES)
    return bool(hedged and _REASON.search(text) or _SOFT.search(text))


def rule_check(clause: dict) -> str | None:
    """A label the boundary rules point to when the clause's wording contradicts its current label."""
    label, text = clause["label"], normalize(clause["text"])
    if label not in ("other", "lunch") and _FINE.search(text) and not _REQUEST.search(re.sub(_FINE, "", text)):
        return "other"                                    # "early morning classes are fine"
    if label == "other" and named_days(text) and _EXCEPT_DAY.search(text):
        return "blocked_time"                             # "fine with any day except Friday" (rule 4)
    if label == "prefer_fewer_days" and _DAY_COUNT.search(text):
        return "max_days"                                 # "four campus days or fewer" (rule 3)
    return None


def _which(index: int, clause: dict, other: str) -> Question:
    """Current label or `other`; between hard and soft for a time without a weekday, ask it that way."""
    text = normalize(clause["text"])
    if ({clause["label"], other} == {"blocked_time", "prefer_no_early_late"} and not named_days(text)
            and (find_times(text) or _PERIOD.search(text))):
        return _hard_soft_question(index, clause)
    return {"kind": "low_confidence", "clause_index": index, "text": "Which did you mean?",
            "options": [_relabel(clause["label"], clause["text"]), _relabel(other, clause["text"])]}


def _low_confidence(index: int, clause: dict, from_model: bool, opinion) -> Question | None:
    if (by_rule := rule_check(clause)) is not None:
        return _which(index, clause, by_rule)
    if opinion is None:
        return None
    probabilities = opinion(clause["text"])
    ranked = sorted(probabilities, key=probabilities.get, reverse=True)
    if from_model:
        other = ranked[0]
        if probabilities[other] < DISAGREE_MIN:
            return None
    else:
        other = ranked[1] if ranked[0] == clause["label"] else ranked[0]
        if probabilities[ranked[0]] - probabilities[ranked[1]] >= MARGIN:
            return None
    if other == clause["label"]:
        return None
    return _which(index, clause, other)


def between_hard_and_soft(clause: dict) -> bool:
    """A time without a weekday whose tone or label leaves "can't" and "would rather" both open: a hedge
    with a reason or a soft phrase outside the hedge words; or a label that rule 5 (hedged clock time
    is soft) or the part-of-day rule (time-of-day word + request is hard) would turn the other way."""
    label, text = clause["label"], normalize(clause["text"])
    if label not in ("blocked_time", "prefer_no_early_late") or named_days(text):
        return False
    hedged = any(word in text for word in HEDGES)
    if find_times(text):
        return (ambiguous_tone(clause["text"]) or label == "blocked_time" and hedged and not _REASON.search(text)
                or label == "prefer_no_early_late" and not hedged)
    return label == "prefer_no_early_late" and bool(_PERIOD.search(text) and _REQUEST.search(text))


def _hard_or_soft(index: int, clause: dict) -> Question | None:
    return _hard_soft_question(index, clause) if between_hard_and_soft(clause) else None


def _hard_soft_question(index: int, clause: dict) -> Question:
    hard = {"unavailable_windows": fields("blocked_time", clause["text"]).get("unavailable_windows", [])}
    soft = fields("prefer_no_early_late", clause["text"])
    options = {"blocked_time": {"text": "Can't", "label": "blocked_time", "fields": hard},
               "prefer_no_early_late": {"text": "Would rather not", "label": "prefer_no_early_late", "fields": soft}}
    first, second = clause["label"], ({"blocked_time", "prefer_no_early_late"} - {clause["label"]}).pop()
    return {"kind": "hard_or_soft", "clause_index": index, "text": "Can't, or would rather not?",
            "options": [options[first], options[second]]}


def _missing_value(index: int, clause: dict) -> Question | None:
    label, text = clause["label"], clause["text"]
    keep = {"text": "Leave as is", "label": label, "fields": {}}
    if label == "blocked_time" and not clause["fields"].get("unavailable_windows"):
        return {"kind": "missing_value", "clause_index": index, "text": "Which days and times? Add them to the sentence.",
                "options": [keep, {"text": "Not a timetable request", "label": "other", "fields": {}}]}
    if label == "max_days" and not clause["fields"].get("max_days_per_week"):
        return {"kind": "missing_value", "clause_index": index, "text": "How many days a week, at most?",
                "options": [keep] + [{"text": str(n), "label": "max_days", "fields": {"max_days_per_week": n}}
                                     for n in (2, 3, 4)]
                + [{"text": "No limit, just fewer days", "label": "prefer_fewer_days", "fields": {}}]}
    if label == "max_daily_hours" and not (clause["fields"].get("max_daily_minutes") or clause["fields"].get("max_daily_span")):
        return {"kind": "missing_value", "clause_index": index, "text": "How many hours of class a day, at most?",
                "options": [keep] + [{"text": f"{n} h", "label": "max_daily_hours",
                                      "fields": {"max_daily_minutes": n * 60}} for n in (4, 5, 6)]
                + [{"text": "No limit", "label": "other", "fields": {}}]}
    return None


def _offers(result: ParseResult) -> list[Question]:
    conditions, offers = result["conditions"], []
    cares = conditions.get("cares") or []
    if "campus_days" in cares and not conditions.get("max_days_per_week"):
        offers.append({"kind": "offer", "clause_index": None, "text": "Most days on campus?",
                       "options": [{"text": "No limit", "label": None, "fields": {}}]
                       + [{"text": str(n), "label": None, "fields": {"max_days_per_week": n}} for n in (2, 3, 4)]})
    if not conditions.get("lunch") and ("gap" in cares or conditions.get("max_daily_minutes")
                                        or conditions.get("max_daily_span")):
        lunch = {"start_min": 690, "end_min": 840, "minutes": 30}
        offers.append({"kind": "offer", "clause_index": None, "text": "Lunch break?",
                       "options": [{"text": "No", "label": None, "fields": {}},
                                   {"text": "30 min between 11:30 am and 2 pm", "label": None, "fields": {"lunch": lunch}}]})
    if not conditions.get("in_person_only") and any(_ONLINE.search(normalize(c)) and not _LIKES.search(normalize(c))
                                                    for c in result["unrecognised"]):     # "online is confusing"
        offers.append({"kind": "offer", "clause_index": None, "text": "Only in-person classes?",
                       "options": [{"text": "No, online is fine", "label": None, "fields": {}},
                                   {"text": "Yes", "label": None, "fields": {"in_person_only": True}}]})
    return offers[:MAX_OFFERS]


def questions(result: ParseResult, from_model: list[bool] | None = None,
              opinion: Callable[[str], dict[str, float]] | None = None,
              confirmed: set[int] = frozenset()) -> list[Question]:
    """from_model[i]: clause i was labelled by the main model (else by the linear model itself).
    opinion: label probabilities from the linear model. confirmed: clauses the student already chose."""
    clauses = result["clauses"]
    from_model = from_model if from_model is not None else [True] * len(clauses)
    asked: set[int] = set(confirmed)
    found: list[Question] = []
    for make in (lambda i, c: _low_confidence(i, c, from_model[i], opinion), _hard_or_soft, _missing_value):
        for index, clause in enumerate(clauses):
            if index not in asked and (question := make(index, clause)):
                found.append(question)
                asked.add(index)
    found += _offers(result)
    return found[:MAX_QUESTIONS]


def default_opinion() -> Callable[[str], dict[str, float]] | None:
    from llm.parse import linear
    try:
        return linear.load().probabilities
    except (OSError, ValueError, KeyError):
        return None


def clarify(result: ParseResult, from_model: list[bool] | None = None,
            opinion: Callable[[str], dict[str, float]] | None = None, confirmed: set[int] = frozenset()) -> ParseResult:
    """The result with summary and questions added (empty input stays as it is)."""
    if not result["clauses"]:
        return result
    opinion = opinion if opinion is not None else default_opinion()
    return {**result, "summary": summary(result), "questions": questions(result, from_model, opinion, confirmed)}
