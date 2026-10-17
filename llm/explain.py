"""Block 4 (integration window): one plain-language reason per recommended timetable.

Both writers start from the same fact sheet, built from the actual dated meetings:
* a template, always available and true by construction;
* local Qwen (llm.ollama), asked to say the same facts in plain words.
Every model sentence is checked against that pick's facts (weekdays, times, numbers,
"best of the picks" claims, course codes). A sentence that fails keeps the template,
so a reason never says something the timetable does not show.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
from collections import OrderedDict
from datetime import date, timedelta
from threading import Lock

from llm import ollama
from llm.contracts import Candidate, Conditions, preferences_of
from llm.rank import contributions
from llm.rank.features import candidate_features
from llm.gpu_lock import LOCKS, target_of_ollama

DAY = "一二三四五六日"
FEATURE = {"campus_days": "campus_days", "gap": "gap_min", "outside_hours": "outside_min"}
CARE_NAME = {"campus_days": "少到校", "gap": "少空等", "outside_hours": "少早晚课"}
BEST_NAME = {"campus_days": "到校天数最少", "gap": "空等最少", "outside_hours": "早晚课最少"}
TIES = {"campus_days": 0.05, "gap_min": 1.0, "outside_min": 1.0}
DEFAULT_HOURS = {"start_min": 540, "end_min": 1080}
# Bigger is better when the Windows GPU machine answers; on this Mac the 3B is the
# best trade-off between speed and how often its sentences pass the fact check.
REMOTE_MODELS = ("qwen2.5:7b", "qwen2.5:3b", "qwen2.5:1.5b")
LOCAL_MODELS = ("qwen2.5:3b", "qwen2.5:1.5b", "qwen2.5:7b")
TIMEOUT = 60


def _clock(minute: int) -> str:
    return f"{minute // 60}:{minute % 60:02d}"


def _days(days: list[int]) -> str:
    return "、".join(f"周{DAY[day - 1]}" for day in days)


def _amount(minutes: float) -> str:
    return f"{minutes / 60:.1f} 小时" if minutes >= 60 else f"{round(minutes)} 分钟"


def _best(pick: Candidate, picks: list[Candidate]) -> list[str]:
    """Cares on which this pick is (jointly) best among the picks, when they differ at all."""
    best = []
    for care, key in FEATURE.items():
        values = [other["features"][key] for other in picks]
        if max(values) - min(values) > TIES[key] and pick["features"][key] - min(values) <= TIES[key]:
            best.append(care)
    return best


def _worst(pick: Candidate, picks: list[Candidate]) -> list[str]:
    best = []
    for care, key in FEATURE.items():
        values = [other["features"][key] for other in picks]
        if max(values) - min(values) > TIES[key] and max(values) - pick["features"][key] <= TIES[key]:
            best.append(care)
    return best


# Plain-word claims ("little waiting", "lots of early classes") need one of these to be true.
SMALL = {"gap_min": 60.0, "campus_days": 2.2, "outside_min": 30.0}
LARGE = {"gap_min": 300.0, "campus_days": 4.0, "outside_min": 120.0}


NOTICED = 0.05  # contribution differences smaller than this do not count as a reason


def _difference(name: str, pick: Candidate, rival: Candidate, x: dict, y: dict, rival_no: int,
                hours: str) -> str | None:
    """How ``pick`` differs from pick ``rival_no`` on one ranking feature, or None if a student
    would not notice. The three page figures come from the pick's own features (as on its card);
    the rest from llm.rank.features, the numbers the ranking model used."""
    def more_or_less(diff: float) -> str:
        return "多" if diff > 0 else "少"

    if name in ("campus_days", "gap_h", "outside_h"):
        key = {"campus_days": "campus_days", "gap_h": "gap_min", "outside_h": "outside_min"}[name]
        diff = pick["features"][key] - rival["features"][key]
        if name == "campus_days":
            return None if abs(diff) < 0.1 else f"每周{more_or_less(diff)}到校 {abs(diff):.1f} 天"
        if abs(diff) < 15:
            return None
        return (f"每周{more_or_less(diff)}等 {_amount(abs(diff))}" if name == "gap_h"
                else f"{hours} 以外的课每周{more_or_less(diff)} {_amount(abs(diff))}")
    if name not in x or name not in y:
        return None
    diff = x[name] - y[name]
    if name in ("early_h", "late_h"):
        minutes = abs(diff) * 60
        return None if minutes < 15 else f"{'早课' if name == 'early_h' else '晚课'}每周{more_or_less(diff)} {_amount(minutes)}"
    if name in ("earliest_start", "latest_end"):
        if abs(diff) < 0.25:
            return None
        word, verb = ("最早", "上课") if name == "earliest_start" else ("最晚", "下课")
        return f"平时{word} {_clock(round(x[name] * 60))} {verb}（第 {rival_no} 份 {_clock(round(y[name] * 60))}）"
    if name in ("longest_day_h", "heaviest_day_h"):
        what = "在校最久的那天平均" if name == "longest_day_h" else "课排得最满的那天平均"
        return None if abs(diff) < 0.25 else f"{what}{more_or_less(diff)} {abs(diff):.1f} 小时"
    if name == "friday_free":
        if diff > 0.05 and x[name] >= 1:
            return f"周五整天不用到校（第 {rival_no} 份要去）"
        if diff < -0.05 and y[name] >= 1 and "5" in pick.get("pattern", ""):
            return f"周五也要到校（第 {rival_no} 份不用）"
        return None
    if name == "building_changes":
        return None if abs(diff) < 0.2 else f"每周{more_or_less(diff)}换 {abs(diff):.1f} 次楼"
    if name == "single_class_days":
        return None if abs(diff) < 0.2 else f"只上单节课的日子每周{more_or_less(diff)} {abs(diff):.1f} 天"
    if name == "online_share":
        return None if abs(diff) < 0.05 else f"线上课{more_or_less(diff)}一些"
    return None


# Features where more is better for a student; for the rest (but online_share) less is better.
MORE_IS_BETTER = ("earliest_start", "friday_free")


def _feels_better(name: str, pick: Candidate, rival: Candidate, x: dict, y: dict) -> bool | None:
    """Whether this pick is better on the feature in plain terms (None: no plain direction)."""
    page = {"campus_days": "campus_days", "gap_h": "gap_min", "outside_h": "outside_min"}
    if name in page:
        return pick["features"][page[name]] < rival["features"][page[name]]
    if name == "online_share" or name not in x or name not in y:
        return None
    return x[name] > y[name] if name in MORE_IS_BETTER else x[name] < y[name]


def versus(index: int, picks: list[Candidate], conditions: Conditions,
           candidates: list[Candidate] | None = None) -> dict | None:
    """Why pick 1 beats pick 2, or why a lower pick sits below pick 1, from llm.rank.contributions.

    The ranking model's per-feature contributions are compared; the biggest positive
    differences are the strengths (1, or 2 when the second is at least a quarter of the
    first) and the most negative one is the cost. Only differences a student would notice
    are named, with numbers from the timetables themselves.
    """
    if len(picks) < 2:
        return None
    rival = 1 if index == 0 else 0
    pool = list(candidates or picks)
    known = {candidate["candidate_id"] for candidate in pool}
    pool += [pick for pick in picks if pick["candidate_id"] not in known]
    prefs = preferences_of(conditions)
    mine, theirs = (contributions(picks[i], prefs, pool) for i in (index, rival))
    features = {candidate["candidate_id"]: f for candidate, f in zip(pool, candidate_features(pool, prefs))}
    x, y = features[picks[index]["candidate_id"]], features[picks[rival]["candidate_id"]]
    hours = "–".join(_clock(value) for value in _hours(conditions))
    named = []
    for name in sorted(mine, key=lambda name: theirs.get(name, 0) - mine[name]):
        diff = mine[name] - theirs.get(name, 0)
        feels = _feels_better(name, picks[index], picks[rival], x, y)
        if abs(diff) < NOTICED or (feels is not None and feels != (diff > 0)):
            continue  # too small, or the model's view runs against what a student would expect
        phrase = _difference(name, picks[index], picks[rival], x, y, rival + 1, hours)
        if phrase:
            named.append((name, diff, phrase))
    plus = [item for item in named if item[1] > 0]
    minus = [item for item in reversed(named) if item[1] < 0]
    strengths = plus[:1] + [item for item in plus[1:2] if item[1] >= 0.25 * plus[0][1]]
    return {"rival": rival + 1, "strengths": [item[2] for item in strengths],
            "costs": [item[2] for item in minus[:1]],
            "main": strengths[0][0] if strengths else None}


def _hours(conditions: Conditions) -> tuple[int, int]:
    hours = conditions.get("preferred_hours") or DEFAULT_HOURS
    return hours["start_min"], hours["end_min"]


def facts_of(index: int, picks: list[Candidate], conditions: Conditions,
             candidates: list[Candidate] | None = None) -> dict:
    """What pick ``index`` shows, in the units the page uses (weekly averages, routine weekdays)."""
    pick = picks[index]
    meetings = pick.get("meetings") or []
    weeks: dict[int, set[date]] = {}
    for meeting in meetings:
        day = date.fromisoformat(meeting["date"])
        weeks.setdefault(meeting["weekday"], set()).add(day - timedelta(days=day.weekday()))
    ordinary = [meeting for meeting in meetings if not meeting.get("is_fixed_assessment")]
    compared = versus(index, picks, conditions, candidates) if meetings else None
    return {
        "has_meetings": bool(meetings),
        "index": index,
        "campus": sorted(int(day) for day in pick.get("pattern", "")),
        "class_days": sorted(day for day, seen in weeks.items() if len(seen) >= 3),
        "free": [day for day in range(1, 8) if day not in weeks],
        "earliest": min((meeting["start_min"] for meeting in ordinary), default=None),
        "latest": max((meeting["end_min"] for meeting in ordinary), default=None),
        "features": pick["features"],
        "hours": _hours(conditions),
        "best": _best(pick, picks) if len(picks) > 1 else [],
        "worst": _worst(pick, picks) if len(picks) > 1 else [],
        "versus": compared,
        "count": len(picks),
        "exceptions": len({meeting["date"] for meeting in meetings if meeting.get("unavailable_exception")}),
        "units": sorted({meeting["unit_code"] for meeting in meetings}),
        # A hard condition: the scheduler guarantees it on every ordinary class day.
        "lunch": conditions.get("lunch"),
    }


def _cares(conditions: Conditions) -> list[str]:
    """Most important first, as the contract orders them."""
    return [care for care in (conditions.get("cares") or FEATURE) if care in FEATURE]


def _compare_text(facts: dict) -> str:
    """Pick 1: why it beats pick 2 and what that costs. Others: what they offer and why they are lower."""
    compared = facts["versus"]
    if not compared:
        return ""
    rival, plus, minus = compared["rival"], "、".join(compared["strengths"]), "、".join(compared["costs"])
    if facts["index"] == 0:
        if not plus:
            return f"排第 1，和第 {rival} 份差别很小。"
        return f"排第 1 是因为比第 {rival} 份{plus}" + (f"；代价是{minus}。" if minus else "。")
    if plus:
        return f"和第 {rival} 份比，{plus}" + (f"，但{minus}。" if minus else "。")
    return f"可作第 {rival} 份的备选，{minus}。" if minus else f"和第 {rival} 份差别很小。"


def template_reason(facts: dict, cares: list[str]) -> str:
    """The comparison from the ranking model first, then the weekly routine."""
    f = facts["features"]
    text = _compare_text(facts)
    if not facts["has_meetings"]:
        days = [f"平均每周到校 {f['campus_days']:.1f} 天"]
    elif facts["campus"]:
        days = [f"每周固定{_days(facts['campus'])}到校"]
    else:
        days = ["平时不用到校，课都在线上"]
    weekday_off = [day for day in facts["free"] if day <= 5]
    if weekday_off:
        days.append(f"{_days(weekday_off)}没课")
    if facts["lunch"]:
        days.append(_lunch_text(facts["lunch"]))
    text += "，".join(days) + "。"
    if facts["exceptions"]:
        text += f"另有 {facts['exceptions']} 次考试或测验落在你不想上课的时间。"
    return text


def _lunch_text(lunch: dict) -> str:
    return f"每天 {_clock(lunch['start_min'])}–{_clock(lunch['end_min'])} 都能空出 {lunch['minutes']} 分钟吃饭"


def fact_lines(facts: dict) -> list[str]:
    """The same facts as the template, one per line, for the model to rephrase."""
    f, hours = facts["features"], "–".join(_clock(value) for value in facts["hours"])
    lines = [f"到校日：{_days(facts['campus'])}（每周 {len(facts['campus'])} 天）" if facts["campus"]
             else "到校日：无（课都在线上）"]
    weekday_off = [day for day in facts["free"] if day <= 5]
    if weekday_off:
        lines.append(f"整学期都没课的工作日：{_days(weekday_off)}")
    if facts["earliest"] is not None:
        lines.append(f"最早 {_clock(facts['earliest'])} 上课，最晚 {_clock(facts['latest'])} 下课")
    lines.append("课之间基本不用等" if f["gap_min"] < 10 else f"每周课间空等约 {_amount(f['gap_min'])}")
    lines.append(f"{hours} 以外的课：每周 {round(f['outside_min'])} 分钟")
    lines.extend(f"这 {facts['count']} 份里{BEST_NAME[care]}" for care in facts["best"])
    compared = facts["versus"]
    if compared and (compared["strengths"] or compared["costs"]):
        lines.append(f"和第 {compared['rival']} 份比：" + "，".join(compared["strengths"] + compared["costs"]))
    if facts["lunch"]:
        lines.append(_lunch_text(facts["lunch"]))
    if facts["exceptions"]:
        lines.append(f"有 {facts['exceptions']} 次考试或测验落在学生不想上课的时间")
    return lines


# ---------- checking a model sentence against the facts ----------

_CN_DIGIT = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_NUMBER = re.compile(r"([一二两三四五六七八九十]+)(?=个?(?:天|小时|分钟|节|次|份|门))")
_WEEKDAY = re.compile(r"(?:周|星期|礼拜)([一二三四五六日天])((?:[一二三四五六日天])*)"
                      r"(?:\s*(?:到|至|~|-|–|—)\s*(?:周|星期|礼拜)?([一二三四五六日天]))?")
_TIME = re.compile(r"(上午|早上|中午|下午|晚上)?\s*(\d{1,2})(?:[:：](\d{2})|\s*点(半)?)")
_AMOUNT = re.compile(r"(\d+(?:\.\d+)?)\s*(个?小时|分钟|天|份|次)")
_SENTENCE = re.compile(r"[。！？!?\n]")
_CLAUSE = re.compile(r"[，,。；;！!？?\n]")
_PART = re.compile(r"[，,。；;、！!？?\n]|但是|但|不过|虽然|而且|并且|同时")
# Words that say a day is free (not "不用等", which is about gaps).
_OFF = re.compile(r"没课|没有课|无课|不用上|不用到|不用去|不用来|不必|不去|不来|不上课|空出|空着|空闲|休息|自由|"
                  r"打工|上班|兼职|放假|整天有空")
_CAMPUS = re.compile(r"到校|学校|校园")
_SUPER = re.compile(r"最(少|短|省|低|小|多|好|佳|适合|理想|轻松|方便)")
_OPINION_WORDS = ("好", "佳", "适合", "理想", "轻松", "方便")
_AXIS = (("campus_days", re.compile(r"到校|来学校|天")), ("gap", re.compile(r"等|空档")),
         ("outside_hours", re.compile(r"早|晚")))
# Which feature a plain-word claim is about, and which way it points.
_TOPIC = (("gap", re.compile(r"等|空档|间隔|课间|空窗")),
          ("campus_days", re.compile(r"到校|去学校|来学校|跑学校|天数|校园|通勤")),
          ("outside_hours", re.compile(r"早晚课|早课|晚课|早上|晚上|太早|太晚|很早|很晚|早起|起早")))
_GOOD = re.compile(r"不多|不长|不早|不晚|不用|无需|不需|没有|少|短|省|低|集中|紧凑")
_BAD = re.compile(r"多|(?<!最)长|(?<!最)久|分散|散|高|早些|晚些")
_FIRST = re.compile(r"第\s*[1-3一二三](?:\s*[份名])?")  # a pick ("排第 1", "第 2 份"); not a claim
_COMPARATIVE = re.compile(r"更|比较|较为|相对|比")
_OPINION = re.compile(r"高效|灵活|方便|合适|适合|理想|舒服|划算|完美|很好|不错")
# "多等 37 分钟", "少到校 0.9 天", "少换 1.0 次楼": a difference between two picks.
_RELATIVE = re.compile(r"(?<![最至])(多|少)[^\d，。；、]{0,4}?\s*(\d+(?:\.\d+)?)\s*(个?小时|分钟|天|次)")
_EARLIEST_LATEST = re.compile(r"最[早晚]")
_WITHIN = re.compile(r"之内|之间|以内|内|里")
_OUTSIDE = re.compile(r"以外|之外|外")
# Things the fact sheet says nothing about; a sentence mentioning them cannot be checked.
_UNKNOWN = re.compile(r"老师|教授|教室|(?<![换次])楼|食堂|作业|成绩|难度|内容|同学|朋友|交通|天气|睡|课外|活动|时间一样|时间相同|上课少|上课多|(?<![早晚])课[多少]|多上|少上")
_LUNCH = re.compile(r"吃饭|午饭|午餐|午休|饭")
_LUNCH_BAD = re.compile(r"紧|不够|赶|没时间|来不及|不能")
_EXAM = re.compile(r"考试|测验|考")
_EVERY_DAY = re.compile(r"每天(?:都)?(?:要|得|需要)?(到校|去学校|来学校|在校园|在学校|在校|上课|有课)")
_ONLY = re.compile(r"固定|只|仅")
# Absolute "none at all" claims; being the best of the picks is not enough for these.
_NO_WAIT = re.compile(r"不用等|无需等|不需要等|没有空等|没空等|不用空等|零空等")
_NO_EARLY_LATE = re.compile(r"没有?早晚课|无早晚课|没有早课|没有晚课|没早课|没晚课")
_NO_CLASS_BY = re.compile(r"((?:上午|早上|中午|下午|晚上)?\s*\d{1,2}(?:[:：]\d{2}|\s*点半?))\s*(之前|以前|前|之后|以后|后)"
                          r"\s*(?:都)?(?:没课|没有课|不上课|无课|不用上课)")
_SAME = re.compile(r"一样|相同|差不多|持平|不变")
_UNIT = re.compile(r"[A-Z]{4}\d{4}")


def _cn_number(text: str) -> int:
    if text == "十":
        return 10
    if "十" in text:
        tens, _, ones = text.partition("十")
        return _CN_DIGIT.get(tens, 1) * 10 + _CN_DIGIT.get(ones, 0)
    return _CN_DIGIT.get(text, 0)


def _digits(text: str) -> str:
    """"三天" -> "3天", "半天" -> "0.5天", "1个半小时" -> "1.5小时"; "周三" is left alone."""
    text = _CN_NUMBER.sub(lambda match: str(_cn_number(match.group(1))), text)
    text = re.sub(r"(\d+)个半(?=小时)", r"\1.5个", text)
    return re.sub(r"(?<![\d.])半(?=个?(?:天|小时))", "0.5", text)


def _times(text: str) -> tuple[list[int], str]:
    """Clock times in the text (minutes after midnight) and the text with them removed."""
    found = []
    for match in _TIME.finditer(text):
        part, hour, minute, half = match.groups()
        value = int(hour) * 60 + (int(minute) if minute else 30 if half else 0)
        if part in ("下午", "晚上") and int(hour) < 12:
            value += 720
        found.append(value)
    return found, _TIME.sub(" ", text)


def _amounts(text: str) -> tuple[list[tuple[float, str]], str]:
    """(number, unit) pairs and the text with them removed; "个小时" counts as "小时"."""
    found = [(float(number), unit.lstrip("个")) for number, unit in _AMOUNT.findall(text)]
    return found, _AMOUNT.sub(" ", text)


def _numbers(text: str) -> list[float]:
    return [float(value) for value in re.findall(r"\d+(?:\.\d+)?", text)]


def _weekday(char: str) -> int:
    return 7 if char in "日天" else DAY.index(char) + 1


def _mentioned_days(clause: str) -> set[int]:
    days = set()
    for match in _WEEKDAY.finditer(clause):
        first, more, last = match.groups()
        start = _weekday(first)
        days.add(start)
        days.update(_weekday(char) for char in more)
        if last:
            days.update(range(start, _weekday(last) + 1))
    return days


def _relative_claims(text: str) -> set[tuple[str, float, str, str | None]]:
    """("多" or "少", number, unit, "day"/"week"/None) for each difference stated in the text."""
    claims = set()
    for match in _RELATIVE.finditer(text):
        before = re.split(r"[，,。；;、！!？?\n]", text[:match.start()])[-1]
        markers = [(found.start(), "week" if found.group() == "每周" else "day")
                   for found in re.finditer(r"每天|那天|每周", before)]
        period = max(markers)[1] if markers else None
        claims.add((match.group(1), float(match.group(2)), match.group(3).lstrip("个"), period))
    return claims


def allowed_values(lines: list[str]) -> dict:
    """Times, (number, unit) amounts and bare numbers that the fact lines state.

    Differences from another pick ("和第 2 份比：每周多等 37 分钟") are kept apart:
    a sentence may only use them while saying what they are compared with. Clock
    times are facts wherever they appear.
    """
    relative = [line for line in lines if _FIRST.search(line)]
    times = set(_times(_digits(_FIRST.sub(" ", "\n".join(lines))))[0])
    _, rest = _times(_digits("\n".join(line for line in lines if line not in relative)))
    amounts, rest = _amounts(rest)
    return {"times": times, "amounts": set(amounts),
            "relative": _relative_claims(_FIRST.sub(" ", _digits("\n".join(relative)))),
            "numbers": [number for number, _ in amounts] + _numbers(_WEEKDAY.sub(" ", rest))}


def _close(value: float, others) -> bool:
    return any(abs(value - other) <= 0.01 for other in others)


def _axis_near(text: str, start: int, end: int) -> str | None:
    """The feature a "最…" refers to: the closest feature word before it, else the first after it."""
    before = text[max(0, start - 8):start]
    found = [(match.end(), care) for care, pattern in _AXIS for match in pattern.finditer(before)]
    if found:
        return max(found)[1]
    after = text[end:end + 6]
    found = [(match.start(), care) for care, pattern in _AXIS for match in pattern.finditer(after)]
    return min(found)[1] if found else None


def check_reason(text: str, facts: dict, allowed: dict, first: bool) -> str | None:
    """None if every checkable claim matches the facts, else why the sentence was rejected."""
    if not 4 <= len(text) <= 140 or not re.search(r"[\u4e00-\u9fff]", text):
        return "length"
    if any(code not in facts["units"] for code in _UNIT.findall(text)):
        return "unit"
    if (_UNKNOWN.search(text) or (_LUNCH.search(text) and (not facts["lunch"] or _LUNCH_BAD.search(text))) or
            (_EXAM.search(text) and not facts["exceptions"])):
        return "topic"
    for sentence in filter(None, _SENTENCE.split(_digits(text))):
        problem = _check_sentence(sentence, facts, allowed, first)
        if problem:
            return problem
    return None


def _check_sentence(text: str, facts: dict, allowed: dict, first: bool) -> str | None:
    """One sentence; a comparison with the top pick only covers the sentence it is made in."""
    against_first = bool(_FIRST.search(text))
    times, rest = _times(_FIRST.sub(" ", text))
    if any(value not in allowed["times"] for value in times):
        return "time"
    for way, number, unit, period in _relative_claims(rest):
        # Same direction, amount and unit as a stated difference, and not "每天" for a weekly figure.
        if not any(way == fact_way and abs(number - fact_number) <= 0.01 and unit == fact_unit and
                   (period is None or fact_period is None or period == fact_period)
                   for fact_way, fact_number, fact_unit, fact_period in allowed["relative"]):
            return "number"
        if not against_first:
            return "reference"
    amounts, rest = _amounts(_RELATIVE.sub(" ", rest))
    for number, unit in amounts:
        if not _close(number, [value for value, kind in allowed["amounts"] if kind == unit]):
            return "number"
    if any(not _close(value, allowed["numbers"]) for value in _numbers(_WEEKDAY.sub(" ", rest))):
        return "number"
    off_campus = {day for day in range(1, 8) if day not in facts["campus"]}
    for clause in _CLAUSE.split(text):
        days = _mentioned_days(clause)
        if not days:
            continue
        if _OFF.search(clause):
            if not days <= (off_campus if _CAMPUS.search(clause) else set(facts["free"])):
                return "weekday"
        elif not days <= set(facts["class_days"]) | set(facts["campus"]):
            return "weekday"
        elif _ONLY.search(clause):  # "固定周二、周三到校" must name every such day
            if days != (set(facts["campus"]) if _CAMPUS.search(clause) else set(facts["class_days"]) | set(facts["campus"])):
                return "weekday"
    if (_NO_WAIT.search(text) and not re.search(r"基本不用等", text) and facts["features"]["gap_min"] >= 1 or
            re.search(r"基本不用等", text) and facts["features"]["gap_min"] >= SMALL["gap_min"]):
        return "direction"
    if _NO_EARLY_LATE.search(text) and facts["features"]["outside_min"] >= 1:
        return "direction"
    for match in _EVERY_DAY.finditer(text):
        days = set(facts["campus"]) | (set(facts["class_days"]) if match.group(1) in ("上课", "有课") else set())
        if not set(range(1, 6)) <= days:
            return "weekday"
    for match in _NO_CLASS_BY.finditer(text):
        clock = _times(match.group(1))[0][0]
        before = match.group(2) in ("之前", "以前", "前")
        bound = facts["earliest"] if before else facts["latest"]
        if bound is not None and (bound < clock if before else bound > clock):
            return "time"
    for match in _EARLIEST_LATEST.finditer(text):
        if not re.match(r"\D{0,3}\d", text[match.end():match.end() + 5]):
            return "superlative"  # "最晚下课" with no time compares picks without a fact behind it
    for match in _SUPER.finditer(text):
        word = match.group(1)
        if word in _OPINION_WORDS:
            if not first:
                return "superlative"
            continue
        if re.match(r"\D{0,3}\d", _FIRST.sub("第份", text[match.end():match.end() + 8])):
            continue  # "最多 3 天" restates a limit; the number itself was checked above
        care = _axis_near(text, match.start(), match.end())
        if word == "多" or care not in facts["best"]:
            return "superlative"
    if _COMPARATIVE.search(text) and not against_first:
        return "comparison"
    if _OPINION.search(text) and not first:
        return "opinion"
    return _check_directions(text, facts, against_first)


def _check_directions(text: str, facts: dict, against_first: bool) -> str | None:
    """Plain-word claims such as "空等时间短" must point the way the numbers do."""
    f = facts["features"]
    compared = facts["versus"] or {"strengths": [], "costs": []}
    stated = compared["strengths"] + compared["costs"]
    good = set(facts["best"]) | {care for care, key in FEATURE.items() if f[key] < SMALL[key]}
    bad = set(facts["worst"]) | {care for care, key in FEATURE.items() if f[key] >= LARGE[key]}
    words = {"campus_days": ("到校",), "gap": ("等",), "outside_hours": ("早晚课", "以外的课", "早课", "晚课")}
    for part in _PART.split(text):
        if _mentioned_days(part):
            continue  # weekday claims are checked against the routine above
        if (set(facts["hours"]) <= set(_times(part)[0]) and _WITHIN.search(part) and
                not _OUTSIDE.search(part) and f["outside_min"] >= 1):
            return "hours"
        topics = [care for care, pattern in _TOPIC if pattern.search(part)]
        if not topics or _SUPER.search(part):
            continue
        if against_first:
            differs = [care for care in topics if any(word in entry for word in words[care] for entry in stated)]
            if _SAME.search(part):  # "到校天数一样": only if the numbers do not differ
                if differs:
                    return "comparison"
                continue
            if "更" in part and len(differs) < len(topics):  # "空等更充裕" needs a real difference
                return "comparison"
        is_good = bool(_GOOD.search(part))
        is_bad = bool(_BAD.search(_GOOD.sub("", part)))
        if is_good and is_bad:
            return "direction"
        if not (is_good or is_bad):
            continue
        for care in topics:
            if against_first:  # the comparison must say the same feature moves the same way
                said = [entry for entry in stated if any(word in entry for word in words[care])
                        and ("少" if is_good else "多") in entry]
                if not said:
                    return "direction"
            elif care not in (good if is_good else bad):
                return "direction"
    return None


# ---------- asking the local model ----------

SYSTEM = (
    "你是大学排课助手。每份课表都已经满足学生的硬性条件。我会给你每份课表的事实和一句草稿理由，"
    "请把草稿改写成一两句更口语、像朋友提醒那样的大白话。规则：\n"
    "1. 只能保留或删掉草稿里的信息，不能加入草稿里没有的说法。\n"
    "2. 星期、时间和数字照抄草稿，用阿拉伯数字，不要换算单位。\n"
    "3. 不要用“更”“比较”“最”，除非草稿里就有这个说法。\n"
    "4. 草稿里和别的份比较时（如“比第 2 份”“和第 1 份比”），改写后也要写明是和第几份比。\n"
    "5. 先说草稿里排在最前面的原因，再说代价。\n"
    "6. 不要复述学生的话，不要评价“适合”“灵活”。\n"
    "7. 每条不超过 60 个字，不要写编号。\n"
    "按 JSON 输出：{\"reasons\": [第1份的理由, 第2份的理由, ...]}，条数和课表份数相同。"
)


def prompt(student_text: str, conditions: Conditions, all_facts: list[dict]) -> str:
    cares = _cares(conditions)
    hours = "–".join(_clock(value) for value in all_facts[0]["hours"])
    head = [f"学生说：「{student_text.strip()}」" if student_text.strip() else "学生没有补充说明。",
            f"学生在意：{'、'.join(CARE_NAME[care] for care in cares)}", f"学生希望的上课时间：{hours}",
            f"一共 {len(all_facts)} 份课表。"]
    blocks = [f"第 {index} 份\n事实：\n" + "\n".join(f"- {line}" for line in fact_lines(facts))
              + f"\n草稿：{template_reason(facts, cares)}"
              for index, facts in enumerate(all_facts, start=1)]
    return "\n".join(head) + "\n\n" + "\n\n".join(blocks)


def choose_model() -> str | None:
    """UNIPLAN_EXPLAIN_MODEL wins; otherwise the first preferred Qwen the server has."""
    wanted = os.environ.get("UNIPLAN_EXPLAIN_MODEL")
    if wanted is not None:
        return wanted if wanted and ollama.available(wanted) else None
    if not ollama.available():
        return None
    order = LOCAL_MODELS if ollama.base_url() == ollama.LOCAL else REMOTE_MODELS
    return next((model for model in order if ollama.available(model)), None)


def gpu_busy() -> bool:
    """A batch job holds the lock of the machine Ollama runs on (llm.gpu_lock); do not compete with it."""
    try:
        with open(LOCKS[target_of_ollama()], "a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(handle, fcntl.LOCK_UN)
    except BlockingIOError:
        return True
    except OSError:
        return False
    return False


_cache: OrderedDict[tuple[str, str], list[str]] = OrderedDict()
_cache_lock = Lock()


def ask_model(model: str, text: str, count: int, timeout: float = TIMEOUT) -> list[str]:
    key = (model, text)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    schema = {"type": "object", "required": ["reasons"], "properties": {"reasons": {
        "type": "array", "items": {"type": "string"}, "minItems": count, "maxItems": count}}}
    reply = ollama.chat(model, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}],
                        schema=schema, options={"seed": 0, "num_predict": 120 * count}, timeout=timeout)
    reasons = json.loads(reply)["reasons"]
    if not isinstance(reasons, list) or len(reasons) != count or not all(isinstance(r, str) for r in reasons):
        raise ValueError("model gave the wrong number of reasons")
    reasons = [reason.strip() for reason in reasons]
    with _cache_lock:
        _cache[key] = reasons
        while len(_cache) > 128:
            _cache.popitem(last=False)
    return reasons


def explain_detailed(student_text: str, conditions: Conditions, picks: list[Candidate], *,
                     model: str | None = "auto", timeout: float = TIMEOUT,
                     candidates: list[Candidate] | None = None) -> dict:
    """Reasons plus who wrote each one ("template" or the model name) and why the model was skipped.

    model=None: template only (instant). model="auto": choose_model(). The model is only
    asked when every pick carries its dated meetings, since only then can it be checked.
    """
    all_facts = [facts_of(index, picks, conditions, candidates) for index in range(len(picks))]
    cares = _cares(conditions)
    reasons = [template_reason(facts, cares) for facts in all_facts]
    result = {"reasons": reasons, "by": ["template"] * len(picks), "model": None, "status": "template",
              "rejected": {}}
    if model is None or not picks or not all(facts["has_meetings"] for facts in all_facts):
        return result
    if model == "auto":
        model = choose_model()
        if model is None:
            return {**result, "status": "unavailable"}
        if gpu_busy():
            return {**result, "status": "busy"}
    result["model"] = model
    try:
        written = ask_model(model, prompt(student_text, conditions, all_facts), len(picks), timeout)
    except (OSError, ValueError, KeyError, TypeError):
        return {**result, "status": "failed"}
    for index, (text, facts) in enumerate(zip(written, all_facts)):
        # Only this pick's own facts count; the student's numbers are limits, not facts.
        allowed = allowed_values([f"{facts['count']} 份", *fact_lines(facts)])
        problem = check_reason(text, facts, allowed, first=index == 0)
        if problem is None:
            reasons[index], result["by"][index] = text, model
        else:
            result["rejected"][index] = {"text": text, "why": problem}
    used = sum(by != "template" for by in result["by"])
    result["status"] = "model" if used == len(picks) else "partial" if used else "rejected"
    return result


def explain(student_text: str, conditions: Conditions, picks: list[Candidate], *,
            model: str | None = "auto", candidates: list[Candidate] | None = None) -> list[str]:
    """``candidates``: the whole list rank() saw, so feature averages match its scores."""
    return explain_detailed(student_text, conditions, picks, model=model, candidates=candidates)["reasons"]
