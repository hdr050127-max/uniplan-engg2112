"""Block 4 (integration window): one plain-language reason per recommended timetable.

Both writers start from the same fact sheet, built from the actual dated meetings:
* a template, always available and true by construction;
* local Qwen (llm.ollama), asked to say the same facts in plain words.
Every model sentence is checked against that pick's facts (weekdays, times, numbers,
"best of the picks" claims, course codes). A sentence that fails keeps the template,
so a reason never says something the timetable does not show. Reasons are in English
(docs/DESIGN.md); the checks are the same ones the Chinese version made, read in English.
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

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
FEATURE = {"campus_days": "campus_days", "gap": "gap_min", "outside_hours": "outside_min"}
CARE_NAME = {"campus_days": "fewer days on campus", "gap": "less waiting", "outside_hours": "fewer early or late classes"}
BEST_NAME = {"campus_days": "Fewest days on campus", "gap": "Least waiting",
             "outside_hours": "Least early or late class time"}
TIES = {"campus_days": 0.05, "gap_min": 1.0, "outside_min": 1.0}
DEFAULT_HOURS = {"start_min": 540, "end_min": 1080}
# Bigger is better when the Windows GPU machine answers; on this Mac the 3B is the
# best trade-off between speed and how often its sentences pass the fact check.
REMOTE_MODELS = ("qwen2.5:7b", "qwen2.5:3b", "qwen2.5:1.5b")
LOCAL_MODELS = ("qwen2.5:3b", "qwen2.5:1.5b", "qwen2.5:7b")
TIMEOUT = 60


def _clock(minute: int) -> str:
    """540 -> "9 am", 1110 -> "6:30 pm" (docs/DESIGN.md: times as "6 pm", "9:30 am")."""
    if minute >= 1440:
        return "midnight"
    hour, rest = divmod(minute, 60)
    return f"{hour % 12 or 12}{f':{rest:02d}' if rest else ''} {'am' if hour < 12 else 'pm'}"


def _join(words: list[str], last: str = "and") -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} {last} {words[-1]}"


def _days(days: list[int], last: str = "and") -> str:
    return _join([DAYS[day - 1] for day in days], last)


def _span(hours: tuple[int, int]) -> str:
    return f"{_clock(hours[0])} to {_clock(hours[1])}"


def _num(value: float) -> str:
    """0.9 -> "0.9", 1.0 -> "1"."""
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _amount(minutes: float) -> str:
    """72 -> "1 h 12 min", 45 -> "45 min", 120 -> "2 h"."""
    hours, rest = divmod(round(minutes), 60)
    return f"{hours} h" + (f" {rest} min" if rest else "") if hours else f"{rest} min"


def _plural(value: float, word: str) -> str:
    return f"{_num(value)} {word}{'' if _num(value) == '1' else 's'}"


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
    the rest from llm.rank.features, the numbers the ranking model used. Each phrase follows
    "it has": "0.9 fewer days on campus a week", "1 h 12 min more waiting a week"."""
    def more_or_less(diff: float, count: bool = False) -> str:
        return "more" if diff > 0 else "fewer" if count else "less"

    if name in ("campus_days", "gap_h", "outside_h"):
        key = {"campus_days": "campus_days", "gap_h": "gap_min", "outside_h": "outside_min"}[name]
        diff = pick["features"][key] - rival["features"][key]
        if name == "campus_days":
            if abs(diff) < 0.1:
                return None
            days = _plural(abs(diff), "day").split(" ", 1)
            return f"{days[0]} {more_or_less(diff, count=True)} {days[1]} on campus a week"
        if abs(diff) < 15:
            return None
        return (f"{_amount(abs(diff))} {more_or_less(diff)} waiting a week" if name == "gap_h"
                else f"{_amount(abs(diff))} {more_or_less(diff)} class outside {hours} a week")
    if name not in x or name not in y:
        return None
    diff = x[name] - y[name]
    if name in ("early_h", "late_h"):
        minutes = abs(diff) * 60
        what = "early" if name == "early_h" else "late"
        return None if minutes < 15 else f"{_amount(minutes)} {more_or_less(diff)} {what} class time a week"
    if name in ("earliest_start", "latest_end"):
        if abs(diff) < 0.25:
            return None
        verb = "start" if name == "earliest_start" else "end"
        return (f"days that usually {verb} at {_clock(round(x[name] * 60))} "
                f"({_clock(round(y[name] * 60))} in option {rival_no})")
    if name in ("longest_day_h", "heaviest_day_h"):
        if abs(diff) < 0.25:
            return None
        what = "on campus on its longest day" if name == "longest_day_h" else "of class on its busiest day"
        return f"{_amount(abs(diff) * 60)} {more_or_less(diff)} {what}"
    if name == "friday_free":
        if diff > 0.05 and x[name] >= 1:
            return f"Fridays free (option {rival_no} has classes on Friday)"
        if diff < -0.05 and y[name] >= 1 and "5" in pick.get("pattern", ""):
            return f"classes on Friday (option {rival_no} has none then)"
        return None
    if name == "building_changes":
        if abs(diff) < 0.2:
            return None
        return f"{_num(abs(diff))} {more_or_less(diff, count=True)} building changes a week"
    if name == "single_class_days":
        if abs(diff) < 0.2:
            return None
        return f"{_num(abs(diff))} {more_or_less(diff, count=True)} days a week with just one class"
    if name == "online_share":
        return None if abs(diff) < 0.05 else f"{more_or_less(diff, count=True)} online classes"
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
    hours = _span(_hours(conditions))
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
    rival, plus, minus = compared["rival"], " and ".join(compared["strengths"]), " and ".join(compared["costs"])
    if facts["index"] == 0:
        if not plus:
            return f"First, with little difference from option {rival}. "
        return f"First because, compared with option {rival}, it has {plus}" + (f", but it has {minus}. " if minus else ". ")
    if plus:
        return f"Compared with option {rival}, it has {plus}" + (f", but it has {minus}. " if minus else ". ")
    return f"A backup to option {rival}: it has {minus}. " if minus else f"Little difference from option {rival}. "


def template_reason(facts: dict, cares: list[str]) -> str:
    """The comparison from the ranking model first, then the weekly routine."""
    f = facts["features"]
    text = _compare_text(facts)
    if not facts["has_meetings"]:
        text += f"On campus {_num(f['campus_days'])} days a week on average."
    elif facts["campus"]:
        text += f"On campus {_days(facts['campus'])} each week."
    else:
        text += "No campus days; every class is online."
    weekday_off = [day for day in facts["free"] if day <= 5]
    if weekday_off:
        text += f" No classes on {_days(weekday_off, 'or')}."
    if facts["lunch"]:
        text += f" {_lunch_text(facts['lunch'])}."
    if facts["exceptions"]:
        count = facts["exceptions"]
        text += (f" {count} exam{'s' if count > 1 else ''} or test{'s' if count > 1 else ''} "
                 f"{'fall' if count > 1 else 'falls'} in times you can't make.")
    return text


def _lunch_text(lunch: dict) -> str:
    return (f"A {lunch['minutes']} min lunch break fits between {_clock(lunch['start_min'])} and "
            f"{_clock(lunch['end_min'])} on every class day")


def fact_lines(facts: dict) -> list[str]:
    """The same facts as the template, one per line, for the model to rephrase."""
    f, hours = facts["features"], _span(facts["hours"])
    count = len(facts["campus"])
    lines = [f"Days on campus: {_days(facts['campus'])} ({count} day{'' if count == 1 else 's'} a week)"
             if facts["campus"] else "Days on campus: none (every class is online)"]
    weekday_off = [day for day in facts["free"] if day <= 5]
    if weekday_off:
        lines.append(f"Weekdays with no classes all term: {_days(weekday_off)}")
    if facts["earliest"] is not None:
        lines.append(f"Earliest start {_clock(facts['earliest'])}, latest finish {_clock(facts['latest'])}")
    lines.append("Almost no waiting between classes" if f["gap_min"] < 10
                 else f"Waiting between classes: about {_amount(f['gap_min'])} a week")
    lines.append(f"Class outside {hours}: {round(f['outside_min'])} min a week")
    lines.extend(f"{BEST_NAME[care]} of these {facts['count']} options" for care in facts["best"])
    compared = facts["versus"]
    if compared and (compared["strengths"] or compared["costs"]):
        lines.append(f"Compared with option {compared['rival']}: " + ", ".join(compared["strengths"] + compared["costs"]))
    if facts["lunch"]:
        lines.append(_lunch_text(facts["lunch"]))
    if facts["exceptions"]:
        lines.append(f"{facts['exceptions']} exams or tests fall in times the student can't make")
    return lines


# ---------- checking a model sentence against the facts ----------
#
# The same checks as the Chinese version (weekdays, clock times, amounts with units, which
# pick a difference is against, best-of-picks words, comparisons, opinions and topics with no
# facts behind them), written for English. Every rejection names the first check that failed.

_WORD_NUMBER = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10}
_UNITS = (r"(?:days?|hours?|hrs?|h|minutes?|mins?|min|options?|timetables?|picks?|times|"
          r"building changes?|changes?|exams?|tests?)")
_WORD_AMOUNT = re.compile(rf"\b(one|two|three|four|five|six|seven|eight|nine|ten)\b"
                          rf"(?=\s+(?:(?:more|fewer|less|extra)\s+)?(?:[a-z-]+\s+)?{_UNITS}\b)", re.I)
_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b|\b(\d{1,2}):(\d{2})\b", re.I)
# Amounts stay on one line ([ \t], not \s): fact lines are joined with newlines.
_DURATION = (r"(\d+(?:\.\d+)?)[ \t]*(?:h|hrs?|hours?)\b(?:[ \t]*(?:and[ \t]+)?(\d+)[ \t]*(?:min|mins|minutes?)\b)?"
             r"|(\d+(?:\.\d+)?)[ \t]*(?:min|mins|minutes?)\b")
_COUNTED = r"(days?|options?|timetables?|picks?|building changes?|changes?|times|exams?|tests?)"
_NOT_WORD = r"(?!(?:more|fewer|less|extra|days?|options?|timetables?|picks?|changes?|times|exams?|tests?)\b)"
_AMOUNT = re.compile(rf"{_DURATION}|(\d+(?:\.\d+)?)[ \t]+(?:{_NOT_WORD}[a-z-]+[ \t]+)?{_COUNTED}\b", re.I)
# "1 h 12 min more", "0.9 fewer days", "1 day fewer": a difference between two picks.
_DIRECTION = r"(more|fewer|less|extra)"
_RELATIVE = (re.compile(rf"(?:{_DURATION})[ \t]+{_DIRECTION}\b", re.I),
             re.compile(rf"(\d+(?:\.\d+)?)[ \t]+{_DIRECTION}[ \t]+(?:{_NOT_WORD}[a-z-]+[ \t]+)?"
                        rf"(days?|building changes?|changes?)\b", re.I),
             re.compile(rf"(\d+(?:\.\d+)?)[ \t]+(days?|building changes?|changes?)[ \t]+{_DIRECTION}\b", re.I))
_WEEK = re.compile(r"\b(?:a|per|each|every)\s+week\b|\bweekly\b", re.I)
_DAILY = re.compile(r"\b(?:a|per|each|every)\s+day\b|\bdaily\b|\blongest day\b|\bbusiest day\b|\bthat day\b", re.I)
_DAYNAME = r"(?:Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|Thu(?:r(?:s(?:day)?)?)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)s?"
_WEEKDAY = re.compile(rf"\b({_DAYNAME})\b(?:\s*(?:to|through|until|till|-)\s*({_DAYNAME})\b)?|\b((?i:week(?:day|end))s?)\b")
_DAY_LIST = re.compile(rf"\b({_DAYNAME}),\s*(?={_DAYNAME}\b)")
_SENTENCE = re.compile(r"(?<!\d)\.(?!\d)|[!?\n]")
_CLAUSE = re.compile(r"(?<!\d)\.(?!\d)|[,;:!?\n]")
_PART = re.compile(r"(?<!\d)\.(?!\d)|[,;:!?\n()]|\b(?:but|though|although|while|and|plus|whereas)\b", re.I)
# Words that say a day is free (not "no waiting", which is about gaps).
_OFF = re.compile(r"\bno class(?:es)?\b|\bnothing\b|\bfree\b|\boff\b|\bdon'?t (?:have to |need to )?(?:come|go|be)\b|"
                  r"\bnot on campus\b|\bstay (?:at )?home\b|\bwithout class(?:es)?\b|\bclass-free\b|\brest\b|"
                  r"\bwork\b|\bjob\b|\bshifts?\b|\bsleep in\b|\bclear\b|\bempty\b", re.I)
_CAMPUS = re.compile(r"\bcampus\b|\buni\b|\buniversity\b|\bcome in\b|\bgo in\b|\bin person\b", re.I)
_SUPER = re.compile(r"\b(fewest|least|shortest|lowest|smallest|most|best|ideal|easiest|lightest|nicest|optimal)\b", re.I)
_OPINION_WORDS = ("best", "ideal", "easiest", "nicest", "optimal")
_AXIS = (("campus_days", re.compile(r"\bdays?\b|\bcampus\b", re.I)), ("gap", re.compile(r"\bwait|\bgaps?\b", re.I)),
         ("outside_hours", re.compile(r"\bearly\b|\blate\b", re.I)))
# Which feature a plain-word claim is about, and which way it points.
_TOPIC = (("gap", re.compile(r"\bwait\w*|\bgaps?\b|(?<!lunch )\bbreaks?\b|\bdowntime\b|\bidle\b", re.I)),
          ("campus_days", re.compile(r"\bcampus\b|\bcome in\b|\bgo in\b|\bcommut\w*|\btrips?\b", re.I)),
          ("outside_hours", re.compile(r"\bearly\b|\blate\b|\bmornings?\b|\bevenings?\b|\bnights?\b|\boutside\b", re.I)))
_GOOD = re.compile(r"\bnot (?:much|many|long|early|late)\b|\b(?:little|few|fewer|less|short|shorter|no|low|lower|"
                   r"compact|light|lighter|minimal|hardly|barely)\b", re.I)
_BAD = re.compile(r"\b(?:lots?|many|more|much|long|longer|plenty|spread|scattered|high|higher|heavy|heavier|extra)\b", re.I)
_FIRST = re.compile(r"\b(?:option|pick|choice|timetable|number)\s*#?\s*[1-3]\b|"
                    r"\b(?:first|second|third|1st|2nd|3rd|top)\s+(?:option|pick|choice|timetable|one)\b|"
                    r"\b(?:ranked|ranks|comes|placed|is|sits)\s+(?:first|second|third|1st|2nd|3rd|top)\b|"
                    r"^\s*(?:first|second|third)\b", re.I)  # a pick ("option 2", "ranked first"); not a claim
_COMPARATIVE = re.compile(r"\b(?:more|less|fewer|better|worse|shorter|longer|lighter|heavier|earlier|later|than|"
                          r"compared|versus|vs)\b", re.I)
_MORE_LY = re.compile(r"\b(?:more|less|fewer|better|worse|shorter|longer)\b", re.I)
_OPINION = re.compile(r"\b(?:efficient|flexible|convenient|suitable|suits?|ideal|comfortable|perfect|great|good|nice|"
                      r"balanced|relaxed|easy|easier|manageable|smooth|handy|excellent|fantastic|amazing|awesome)\b", re.I)
_EARLIEST_LATEST = re.compile(r"\b(?:earliest|latest)\b", re.I)
_WITHIN = re.compile(r"\bwithin\b|\bbetween\b|\binside\b|\bfrom\b", re.I)
_OUTSIDE = re.compile(r"\boutside\b|\bbefore\b|\bafter\b|\bbeyond\b|\bpast\b", re.I)
# Things the fact sheet says nothing about; a sentence mentioning them cannot be checked.
_UNKNOWN = re.compile(r"\b(?:teachers?|lecturers?|tutors?|professors?|staff|rooms?|classrooms?|labs?|librar(?:y|ies)|"
                      r"cafeteria|canteen|cafe|homework|assignments?|grades?|marks|difficult\w*|content|classmates?|"
                      r"friends?|transport|traffic|bus(?:es)?|trains?|parking|weather|sleep\w*|extracurricular|"
                      r"activit(?:y|ies)|social|clubs?|sports?|gym)\b|\bbuildings?\b(?!\s+changes?)|"
                      r"\b(?:fewer|more|less) (?:classes|lectures|lessons|tutorials)\b|\bsame (?:times?|hours)\b", re.I)
_LUNCH = re.compile(r"\blunch|\bmeals?\b|\beat(?:ing)?\b|\bfood\b", re.I)
_LUNCH_BAD = re.compile(r"\btight\b|\brushed\b|\bhurr\w*|\bnot enough\b|\bno time\b|\bcan'?t\b|\bcannot\b|\bsqueez\w*|"
                        r"\bshort\b", re.I)
_EXAM = re.compile(r"\bexams?\b|\btests?\b|\bquiz\w*|\bassessments?\b|\bmidterms?\b", re.I)
_EVERY_DAY = re.compile(r"\b(on campus|at uni|come in|go in|class(?:es)?)\b[^.,;]{0,15}\b(?:every|each)\s+(?:week)?day\b|"
                        r"\b(?:every|each)\s+(?:week)?day\b[^.,;]{0,20}?\b(on campus|at uni|class(?:es)?)\b", re.I)
_ONLY = re.compile(r"\bonly\b|\bjust\b", re.I)
# Absolute "none at all" claims; being the best of the picks is not enough for these.
_ALMOST_NO_WAIT = re.compile(r"\b(?:almost|nearly|hardly any|barely any|virtually|practically)\s+(?:no\s+)?"
                             r"(?:waiting|wait|gaps?)\b", re.I)
_NO_WAIT = re.compile(r"\bno (?:waiting|wait|gaps?|downtime)\b|\bwithout (?:any )?(?:waiting|gaps?)\b|"
                      r"\bnever (?:have to )?wait\b|\bzero (?:waiting|gaps?)\b|\bback[- ]to[- ]back\b", re.I)
_NO_EARLY_LATE = re.compile(r"\bno (?:early|late|early or late|early and late|morning|evening) "
                            r"(?:classes|class|lectures|starts|finishes)\b|\bnothing (?:early|late)\b", re.I)
_CLOCK = r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)"
_NO_CLASS_BY = (re.compile(rf"\b(?:no class(?:es)?|nothing|free|never starts?|no starts?)\s+(?:before|until|till)\s+{_CLOCK}",
                           re.I),
                re.compile(rf"\b(?:no class(?:es)?|nothing)\s+(?:after|past|beyond)\s+{_CLOCK}|"
                           rf"\b(?:done|finished|finish(?:es)?|ends?|home|out)\s+(?:by|before)\s+{_CLOCK}", re.I))
_SAME = re.compile(r"\b(?:same|equal|similar|unchanged|identical|no different|as many|as much)\b", re.I)
_UNIT = re.compile(r"[A-Z]{4}\d{4}")
_LATIN = re.compile(r"[A-Za-z]")
_CJK = re.compile(r"[一-鿿]")


def _digits(text: str) -> str:
    """"two days" -> "2 days", "half an hour" -> "30 min", "a.m." -> "am"; "one of them" is left alone."""
    text = re.sub(r"\b([ap])\.m\.", r"\1m", text, flags=re.I)
    text = re.sub(r"\bhalf an hour\b", "30 min", text, flags=re.I)
    text = re.sub(r"\ban hour and a half\b", "90 min", text, flags=re.I)
    text = re.sub(r"\b(?:an|one) hour\b", "1 h", text, flags=re.I)
    text = re.sub(r"\bhalf a day\b", "0.5 days", text, flags=re.I)
    text = re.sub(r"\b(?:noon|midday)\b", "12 pm", text, flags=re.I)
    return _WORD_AMOUNT.sub(lambda match: str(_WORD_NUMBER[match.group(1).lower()]), text)


def _times(text: str) -> tuple[list[int], str]:
    """Clock times in the text (minutes after midnight) and the text with them removed."""
    found = []
    for match in _TIME.finditer(text):
        hour, minute, half, hour24, minute24 = match.groups()
        if hour24 is not None:
            found.append(int(hour24) * 60 + int(minute24))
            continue
        value = (int(hour) % 12) * 60 + int(minute or 0)
        found.append(value + (720 if half.lower() == "pm" else 0))
    return found, _TIME.sub(" ", text)


def _minutes_of(groups: tuple) -> float:
    hours, extra, minutes = groups[:3]
    return float(hours) * 60 + float(extra or 0) if hours is not None else float(minutes)


def _unit(word: str) -> str:
    word = word.lower()
    if word.startswith("day"):
        return "day"
    if word.startswith(("option", "timetable", "pick")):
        return "option"
    if word.startswith(("exam", "test")):
        return "exam"
    return "change"  # building changes, changes, times


def _amounts(text: str) -> tuple[list[tuple[float, str]], str]:
    """(number, unit) pairs and the text with them removed; durations count in minutes."""
    found = []
    for match in _AMOUNT.finditer(text):
        groups = match.groups()
        if groups[0] is not None or groups[2] is not None:
            found.append((_minutes_of(groups), "min"))
        else:
            found.append((float(groups[3]), _unit(groups[4])))
    return found, _AMOUNT.sub(" ", text)


def _relative_matches(text: str) -> list[tuple[int, int, str, float, str]]:
    """(start, end, "more" or "less", number, unit) for each difference stated in the text."""
    found: list[tuple[int, int, str, float, str]] = []
    taken: list[tuple[int, int]] = []
    for kind, pattern in enumerate(_RELATIVE):
        for match in pattern.finditer(text):
            if any(start < match.end() and match.start() < end for start, end in taken):
                continue
            groups = match.groups()
            if kind == 0:
                value, unit, way = _minutes_of(groups), "min", groups[3]
            elif kind == 1:
                value, way, unit = float(groups[0]), groups[1], _unit(groups[2])
            else:
                value, unit, way = float(groups[0]), _unit(groups[1]), groups[2]
            way = "more" if way.lower() in ("more", "extra") else "less"
            found.append((match.start(), match.end(), way, value, unit))
            taken.append((match.start(), match.end()))
    return sorted(found)


def _without_relative(text: str) -> str:
    for start, end, *_ in reversed(_relative_matches(text)):
        text = text[:start] + " " + text[end:]
    return text


def _numbers(text: str) -> list[float]:
    return [float(value) for value in re.findall(r"\d+(?:\.\d+)?", text)]


def _weekday(name: str) -> int:
    return DAYS.index(name[:3].title()) + 1


def _mentioned_days(clause: str) -> set[int]:
    days = set()
    for match in _WEEKDAY.finditer(clause):
        first, last, group = match.groups()
        if group:
            days.update(range(1, 6) if group.lower().startswith("weekday") else (6, 7))
            continue
        start = _weekday(first)
        days.add(start)
        if last:
            days.update(range(start, _weekday(last) + 1))
    return days


def _relative_claims(text: str) -> set[tuple[str, float, str, str | None]]:
    """("more" or "less", number, unit, "day"/"week"/None) for each difference stated in the text."""
    claims = set()
    for start, end, way, value, unit in _relative_matches(text):
        clause_end = min([found.start() + end for found in [_CLAUSE.search(text[end:])] if found] or [len(text)])
        after = text[end:clause_end]
        before = _CLAUSE.split(text[:start])[-1]
        markers = sorted([(found.start(), "week") for found in _WEEK.finditer(after)] +
                         [(found.start(), "day") for found in _DAILY.finditer(after)])
        if not markers:
            markers = sorted([(-found.start(), "week") for found in _WEEK.finditer(before)] +
                             [(-found.start(), "day") for found in _DAILY.finditer(before)])
        period = markers[0][1] if markers else None
        claims.add((way, value, unit, period))
    return claims


def allowed_values(lines: list[str]) -> dict:
    """Times, (number, unit) amounts and bare numbers that the fact lines state.

    Differences from another pick ("Compared with option 2: 1 h 12 min more waiting a week")
    are kept apart: a sentence may only use them while saying what they are compared with.
    Clock times are facts wherever they appear.
    """
    relative = [line for line in lines if _FIRST.search(line)]
    times = set(_times(_digits(_FIRST.sub(" ", "\n".join(lines))))[0])
    _, rest = _times(_digits("\n".join(line for line in lines if line not in relative)))
    amounts, rest = _amounts(rest)
    return {"times": times, "amounts": set(amounts),
            "relative": _relative_claims(_FIRST.sub(" ", _digits("\n".join(relative)))),
            "numbers": [number for number, _ in amounts] + _numbers(rest)}


def allowed_for(facts: dict) -> dict:
    """What a reason for this pick may state: its fact lines and how many picks there are."""
    return allowed_values([f"{facts['count']} options", *fact_lines(facts)])


def _close(value: float, others) -> bool:
    return any(abs(value - other) <= 0.01 for other in others)


def _axis_near(text: str, start: int, end: int) -> str | None:
    """The feature a superlative refers to: the first feature word after it, else the closest before it."""
    after = text[end:end + 25]
    found = [(match.start(), care) for care, pattern in _AXIS for match in pattern.finditer(after)]
    if found:
        return min(found)[1]
    before = text[max(0, start - 20):start]
    found = [(match.end(), care) for care, pattern in _AXIS for match in pattern.finditer(before)]
    return max(found)[1] if found else None


def check_reason(text: str, facts: dict, allowed: dict, first: bool) -> str | None:
    """None if every checkable claim matches the facts, else why the sentence was rejected."""
    if not 10 <= len(text) <= 420 or not _LATIN.search(text) or _CJK.search(text):
        return "length"
    if any(code not in facts["units"] for code in _UNIT.findall(text)):
        return "unit"
    sentences = list(filter(str.strip, _SENTENCE.split(_digits(text))))
    if (_UNKNOWN.search(text) or (_EXAM.search(text) and not facts["exceptions"]) or
            any(_LUNCH.search(sentence) and (not facts["lunch"] or _LUNCH_BAD.search(sentence)) for sentence in sentences)):
        return "topic"
    for sentence in sentences:
        problem = _check_sentence(sentence, facts, allowed, first)
        if problem:
            return problem
    return None


def _check_sentence(text: str, facts: dict, allowed: dict, first: bool) -> str | None:
    """One sentence; a comparison with another pick only covers the sentence it is made in."""
    against_first = bool(_FIRST.search(text))
    times, rest = _times(_FIRST.sub(" ", text))
    if any(value not in allowed["times"] for value in times):
        return "time"
    for way, number, unit, period in _relative_claims(rest):
        # Same direction, amount and unit as a stated difference, and not "a day" for a weekly figure.
        if not any(way == fact_way and abs(number - fact_number) <= 0.01 and unit == fact_unit and
                   (period is None or fact_period is None or period == fact_period)
                   for fact_way, fact_number, fact_unit, fact_period in allowed["relative"]):
            return "number"
        if not against_first:
            return "reference"
    amounts, rest = _amounts(_without_relative(rest))
    for number, unit in amounts:
        if not _close(number, [value for value, kind in allowed["amounts"] if kind == unit]):
            return "number"
    if any(not _close(value, allowed["numbers"]) for value in _numbers(rest)):
        return "number"
    off_campus = {day for day in range(1, 8) if day not in facts["campus"]}
    for clause in _CLAUSE.split(_DAY_LIST.sub(r"\1 and ", text)):
        days = _mentioned_days(clause)
        if not days:
            continue
        if _OFF.search(clause):
            if not days <= (off_campus if _CAMPUS.search(clause) else set(facts["free"])):
                return "weekday"
        elif not days <= set(facts["class_days"]) | set(facts["campus"]):
            return "weekday"
        elif _ONLY.search(clause):  # "only on campus Tue and Wed" must name every such day
            if days != (set(facts["campus"]) if _CAMPUS.search(clause) else set(facts["class_days"]) | set(facts["campus"])):
                return "weekday"
    gap = facts["features"]["gap_min"]
    if _ALMOST_NO_WAIT.search(text) and gap >= SMALL["gap_min"]:
        return "direction"
    if _NO_WAIT.search(_ALMOST_NO_WAIT.sub(" ", text)) and gap >= 1:
        return "direction"
    if _NO_EARLY_LATE.search(text) and facts["features"]["outside_min"] >= 1:
        return "direction"
    for match in _EVERY_DAY.finditer(text):
        where = (match.group(1) or match.group(2) or "").lower()
        days = set(facts["campus"]) | (set(facts["class_days"]) if where.startswith("class") else set())
        if not set(range(1, 6)) <= days:
            return "weekday"
    for before, pattern in zip((True, False), _NO_CLASS_BY):
        for match in pattern.finditer(text):
            found = _times(next(group for group in match.groups() if group))[0]
            if not found:
                continue
            bound = facts["earliest"] if before else facts["latest"]
            if bound is not None and (bound < found[0] if before else bound > found[0]):
                return "time"
    for match in _EARLIEST_LATEST.finditer(text):
        if not re.match(r"\D{0,25}?\d", text[match.end():match.end() + 30]):
            return "superlative"  # "finishes latest" with no time compares picks without a fact behind it
    for match in _SUPER.finditer(text):
        word = match.group(1).lower()
        if word in _OPINION_WORDS:
            if not first:
                return "superlative"
            continue
        if re.match(r"\D{0,3}\d", _FIRST.sub("option", text[match.end():match.end() + 8])):
            continue  # "at most 3 days" restates a limit; the number itself was checked above
        care = _axis_near(text, match.start(), match.end())
        if word == "most" or care not in facts["best"]:
            return "superlative"
    if _COMPARATIVE.search(text) and not against_first:
        return "comparison"
    if _OPINION.search(text) and not first:
        return "opinion"
    return _check_directions(text, facts, against_first)


def _check_directions(text: str, facts: dict, against_first: bool) -> str | None:
    """Plain-word claims such as "short waits" must point the way the numbers do."""
    f = facts["features"]
    compared = facts["versus"] or {"strengths": [], "costs": []}
    stated = compared["strengths"] + compared["costs"]
    good = set(facts["best"]) | {care for care, key in FEATURE.items() if f[key] < SMALL[key]}
    bad = set(facts["worst"]) | {care for care, key in FEATURE.items() if f[key] >= LARGE[key]}
    words = {"campus_days": ("campus",), "gap": ("waiting",), "outside_hours": ("early", "late", "outside")}
    for clause in _CLAUSE.split(text):
        if (set(facts["hours"]) <= set(_times(clause)[0]) and _WITHIN.search(clause) and
                not _OUTSIDE.search(clause) and f["outside_min"] >= 1):
            return "hours"
    for part in _PART.split(_DAY_LIST.sub(r"\1 and ", text)):
        if not part or _mentioned_days(part):
            continue  # weekday claims are checked against the routine above
        topics = [care for care, pattern in _TOPIC if pattern.search(part)]
        if not topics or _SUPER.search(part):
            continue
        if against_first:
            differs = [care for care in topics if any(word in entry for word in words[care] for entry in stated)]
            if _SAME.search(part):  # "the same waiting": only if the numbers do not differ
                if differs:
                    return "comparison"
                continue
            if _MORE_LY.search(part) and len(differs) < len(topics):  # "better early classes" needs a real difference
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
                        and (("fewer" in entry or "less" in entry) if is_good else "more" in entry)]
                if not said:
                    return "direction"
            elif care not in (good if is_good else bad):
                return "direction"
    return None


# ---------- asking the local model ----------

SYSTEM = (
    "You help university students choose a timetable. Every timetable already meets the student's hard "
    "conditions. For each timetable you get its facts and a draft reason. Rewrite each draft as one or two "
    "plain, friendly sentences, the way a friend would point it out. Rules:\n"
    "1. Only keep or drop what the draft says. Never add a claim the draft does not make.\n"
    "2. Copy weekdays, times and numbers exactly as the draft writes them, in digits. Do not convert units.\n"
    "3. Do not use \"more\", \"less\", \"fewer\", \"better\", \"most\", \"least\" or \"best\" unless the draft "
    "uses that word in that place.\n"
    "4. When the draft compares with another option (\"compared with option 2\"), say which option the "
    "comparison is with.\n"
    "5. Give the draft's first reason first, then the cost.\n"
    "6. Do not repeat the student's words. Do not call a timetable \"suitable\" or \"flexible\".\n"
    "7. At most 45 words each. No numbering, no dashes.\n"
    "Answer in JSON: {\"reasons\": [reason for option 1, reason for option 2, ...]}, one reason per timetable."
)


def prompt(student_text: str, conditions: Conditions, all_facts: list[dict]) -> str:
    cares = _cares(conditions)
    head = [f"The student wrote: \"{student_text.strip()}\"" if student_text.strip() else "The student wrote no sentence.",
            f"The student cares about: {', '.join(CARE_NAME[care] for care in cares)}",
            f"Preferred class hours: {_span(all_facts[0]['hours'])}",
            f"{len(all_facts)} timetables in all."]
    blocks = [f"Option {index}\nFacts:\n" + "\n".join(f"- {line}" for line in fact_lines(facts))
              + f"\nDraft: {template_reason(facts, cares)}"
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
        problem = check_reason(text, facts, allowed_for(facts), first=index == 0)
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
