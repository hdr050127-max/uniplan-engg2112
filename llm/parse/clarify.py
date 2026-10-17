"""Restate what parse() understood, and ask a few questions back. Rules only, standard library.

The summary is built from the conditions and the unrecognised clauses by fixed phrases (no free
model text). Questions come in this order, at most MAX_QUESTIONS per sentence:
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

_ZH_DAY = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}
_CARE = {"campus_days": "尽量少去学校几天", "gap": "课之间尽量少等", "outside_hours": "尽量少早晚课"}
_LABEL_TEXT = {
    "blocked_time": "这段时间不能上课", "max_days": "每周最多来几天", "max_daily_hours": "每天最多上几小时",
    "lunch": "要留午饭时间", "in_person_only": "只要线下课", "prefer_fewer_days": "尽量少去学校几天",
    "prefer_less_waiting": "课之间尽量少等", "prefer_no_early_late": "最好别太早或太晚（不是一定）",
    "other": "和排课无关，或排课管不了",
}
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
    return f"{minutes // 60}:{minutes % 60:02d}"


def _days(days: list[int]) -> str:
    days = sorted(days)
    if days == [1, 2, 3, 4, 5]:
        return "每天"
    if days == [6, 7]:
        return "周末"
    if len(days) >= 3 and days == list(range(days[0], days[-1] + 1)):
        return f"{_ZH_DAY[days[0]]}到{_ZH_DAY[days[-1]]}"
    return "、".join(_ZH_DAY[day] for day in days)


def _span(start: int, end: int) -> str:
    if (start, end) == (0, 1440):
        return "全天"
    if start == 0:
        return f" {_clock(end)} 以前"
    if end == 1440:
        return f" {_clock(start)} 以后"
    return f" {_clock(start)}–{_clock(end)}"


def _hours(minutes: int) -> str:
    return f"{minutes / 60:g}"


def describe(conditions: Conditions) -> list[str]:
    """Short Chinese phrases for conditions, hard ones first."""
    phrases = []
    by_time: dict[tuple[int, int], list[int]] = {}
    for window in conditions.get("unavailable_windows") or []:
        by_time.setdefault((window["start_min"], window["end_min"]), []).append(window["weekday"])
    for (start, end), days in sorted(by_time.items(), key=lambda item: (min(item[1]), item[0])):
        phrases.append(f"{_days(days)}{_span(start, end)}不能上课")
    if conditions.get("max_days_per_week"):
        phrases.append(f"每周最多来 {conditions['max_days_per_week']} 天")
    if conditions.get("max_daily_minutes"):
        phrases.append(f"每天最多上 {_hours(conditions['max_daily_minutes'])} 小时课")
    if conditions.get("max_daily_span"):
        phrases.append(f"每天在学校最多 {_hours(conditions['max_daily_span'])} 小时")
    if conditions.get("lunch"):
        lunch = conditions["lunch"]
        phrases.append(f"{_clock(lunch['start_min'])}–{_clock(lunch['end_min'])} 之间留 {lunch['minutes']} 分钟吃午饭")
    if conditions.get("in_person_only"):
        phrases.append("只要线下课")
    if conditions.get("preferred_hours"):
        hours = conditions["preferred_hours"]
        phrases.append(f"最好在 {_clock(hours['start_min'])}–{_clock(hours['end_min'])} 之间上课")
    phrases += [_CARE[care] for care in conditions.get("cares") or [] if care in _CARE]
    return phrases


def summary(result: ParseResult) -> str:
    phrases = describe(result["conditions"])
    unread = result["unrecognised"]
    text = "我理解为：" + "；".join(phrases) if phrases else "我没读出排课要求"
    if unread:
        quoted = "".join(f"“{clause}”" for clause in unread)
        text += ("；" if phrases else "。") + f"{quoted}{'这句' if len(unread) == 1 else '这几句'}排课管不了"
    return text + "。"


def _reading(label: str, clause: str) -> str:
    """What choosing this label would mean for this clause, in the page's words."""
    phrases = describe(fields(label, clause))
    if label == "prefer_no_early_late" and not any(p.startswith("最好在") for p in phrases):
        return _LABEL_TEXT[label]
    return "；".join(phrases) if phrases and label != "other" else _LABEL_TEXT[label]


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
    return {"kind": "low_confidence", "clause_index": index, "text": f"“{clause['text']}”是指？",
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
    options = {"blocked_time": {"text": "一定不能（" + "；".join(describe(hard) or ["这段时间不能上课"]) + "）",
                                "label": "blocked_time", "fields": hard},
               "prefer_no_early_late": {"text": "最好不要（" + "；".join(describe(soft) or ["尽量少早晚课"]) + "）",
                                        "label": "prefer_no_early_late", "fields": soft}}
    first, second = clause["label"], ({"blocked_time", "prefer_no_early_late"} - {clause["label"]}).pop()
    return {"kind": "hard_or_soft", "clause_index": index, "text": f"“{clause['text']}”：是一定不能，还是最好不要？",
            "options": [options[first], options[second]]}


def _missing_value(index: int, clause: dict) -> Question | None:
    label, text = clause["label"], clause["text"]
    keep = {"text": "先这样，我在句子里补上", "label": label, "fields": {}}
    if label == "blocked_time" and not clause["fields"].get("unavailable_windows"):
        return {"kind": "missing_value", "clause_index": index, "text": f"“{text}”：是哪几天、几点不能上课？请在句子里写上。",
                "options": [keep, {"text": "这句不是排课要求", "label": "other", "fields": {}}]}
    if label == "max_days" and not clause["fields"].get("max_days_per_week"):
        return {"kind": "missing_value", "clause_index": index, "text": f"“{text}”：每周最多来几天？",
                "options": [keep] + [{"text": f"最多 {n} 天", "label": "max_days", "fields": {"max_days_per_week": n}}
                                     for n in (2, 3, 4)]
                + [{"text": "不限天数，少去几天就行", "label": "prefer_fewer_days", "fields": {}}]}
    if label == "max_daily_hours" and not (clause["fields"].get("max_daily_minutes") or clause["fields"].get("max_daily_span")):
        return {"kind": "missing_value", "clause_index": index, "text": f"“{text}”：每天最多上几小时课？",
                "options": [keep] + [{"text": f"最多 {n} 小时", "label": "max_daily_hours",
                                      "fields": {"max_daily_minutes": n * 60}} for n in (4, 5, 6)]
                + [{"text": "不限", "label": "other", "fields": {}}]}
    return None


def _offers(result: ParseResult) -> list[Question]:
    conditions, offers = result["conditions"], []
    cares = conditions.get("cares") or []
    no = {"text": "不用", "label": None, "fields": {}}
    if "campus_days" in cares and not conditions.get("max_days_per_week"):
        offers.append({"kind": "offer", "clause_index": None, "text": "要不要定一个每周最多来几天？",
                       "options": [no] + [{"text": f"最多 {n} 天", "label": None, "fields": {"max_days_per_week": n}}
                                          for n in (2, 3, 4)]})
    if not conditions.get("lunch") and ("gap" in cares or conditions.get("max_daily_minutes")
                                        or conditions.get("max_daily_span")):
        offers.append({"kind": "offer", "clause_index": None, "text": "要不要留出午饭时间？",
                       "options": [no, {"text": "要，11:30–14:00 之间留 30 分钟", "label": None,
                                        "fields": {"lunch": {"start_min": 690, "end_min": 840, "minutes": 30}}}]})
    if not conditions.get("in_person_only") and any(_ONLINE.search(normalize(c)) and not _LIKES.search(normalize(c))
                                                    for c in result["unrecognised"]):     # "online is confusing"
        offers.append({"kind": "offer", "clause_index": None, "text": "要不要只排线下课？",
                       "options": [{"text": "不用，线上也行", "label": None, "fields": {}},
                                   {"text": "只要线下课", "label": None, "fields": {"in_person_only": True}}]})
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
