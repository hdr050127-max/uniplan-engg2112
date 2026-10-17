"""Keyword rules for the 9 labels: the baseline model, and the fallback when Ollama is down.

The checks follow the boundary rules in labels.RULES, in the same order.
"""
from __future__ import annotations

import re

from llm.parse.labels import HEDGES
from llm.parse.text import find_days, find_parts, find_times, normalize


def _has(pattern: str, text: str) -> bool:
    return re.search(pattern, text) is not None


_LUNCH = r"午饭|午餐|吃饭|吃午|饭点|吃东西|\b(?:lunch|eat|meal|food)\b"
_ONLINE = r"线上|网课|在线|录播|zoom|\bonline\b|\brecorded\b|\bremote\b"
_IN_PERSON = r"线下|面授|现场|面对面|当面|\bin[- ]person\b|face[- ]to[- ]face|on campus only"
_NO = r"不|别|没|\b(?:no|not|don'?t|can'?t|cannot|busy|hate|avoid|never|without)\b"
_DAY_COUNT = r"\d+\s*(?:天|次|days?\b|times\b)"
_HOUR_COUNT = r"\d+(?:\.\d+)?\s*(?:个)?\s*半?\s*(?:小时|钟头|hours?\b|hrs?\b|h\b)|半(?:个)?小时"
_COMMITMENT = (r"打工|上班|兼职|实习|送|接|照顾|带孩子|孩子|训练|比赛|排练|教会|礼拜|祷告|家教|补习|通勤|"
               r"\b(?:work|job|shift|intern\w*|pick\s?up|drop\s?off|kids?|child\w*|training|practice|church|"
               r"mosque|pray\w*|tutor(?:ing|s)?|commut\w*|appointment|volunteer\w*|gym|rehearsal)\b")
_FINE = r"可以|没问题|都行|有空|\b(?:fine|ok|okay|free|available|good)\b"
_EARLY_LATE = (r"早课|太早|早起|起不来|起床|睡懒觉|早八|晚课|太晚|夜猫子|\b(?:early|late|morning person|sleep in|"
               r"night owl|8\s?am)\b")
_FEWER_DAYS = (r"少来|少去|少跑|集中|天数|少几天|不想每天|不用每天|压缩|几天里|fewer days|less days|"
               r"\b(?:compress\w*|cluster\w*|condens\w*|not every day|as few days|fewer trips|squeeze)\b")
_WAITING = (r"空档|空堂|空闲|等|间隔|连着|紧凑|中间.*空|干等|\b(?:gaps?|wait\w*|breaks? between|back[- ]to[- ]back|"
            r"downtime|free periods?|hang(?:ing)? around|between classes)\b")


def keyword_label(clause: str) -> str:
    text = normalize(clause)
    if _has(_LUNCH, text):
        return "lunch"
    if _has(_IN_PERSON, text) or _has(_ONLINE, text) and _has(_NO, text):
        return "in_person_only"
    if _has(_ONLINE, text):
        return "other"
    if _has(_DAY_COUNT, text) and not find_days(text):
        return "max_days"
    if _has(_HOUR_COUNT, text):
        return "max_daily_hours"
    clock = bool(find_times(text))
    if clock and not find_days(text) and not _has(_COMMITMENT, text) and any(h in text for h in HEDGES):
        return "prefer_no_early_late"
    if (find_days(text) and _has(_FINE, text) and not _has(_NO + r"|只|仅|\bonly\b", text)
            and not _has(_COMMITMENT, text)):
        return "other"            # "Thursdays are fine"
    if find_days(text) or clock or _has(_COMMITMENT, text):
        return "blocked_time"
    if _has(_EARLY_LATE, text):
        return "prefer_no_early_late"
    if _has(_FEWER_DAYS, text):
        return "prefer_fewer_days"
    if _has(_WAITING, text):
        return "prefer_less_waiting"
    if find_parts(text) and _has(_NO, text):
        return "prefer_no_early_late"
    return "other"
