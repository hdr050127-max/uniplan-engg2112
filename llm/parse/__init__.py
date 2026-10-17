"""Block 2: one sentence -> conditions. Owned by the parsing window.

This is the placeholder the other blocks build against: crude keyword rules with the
final input and output shapes (llm.contracts.ParseResult). The parsing window replaces
the inside with the clause splitter, the trained classifier and the value extractor.
"""
from __future__ import annotations

import re

from llm.contracts import Clause, Conditions, ParseResult

_SPLIT = re.compile(r"[，。；;,.!?！？\n]|而且|并且|但是|另外|\band\b|\bbut\b", re.IGNORECASE)
_DAYS = {"周一": 1, "周二": 2, "周三": 3, "周四": 4, "周五": 5, "周六": 6, "周日": 7, "星期一": 1, "星期二": 2,
         "星期三": 3, "星期四": 4, "星期五": 5, "monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4,
         "friday": 5, "saturday": 6, "sunday": 7}
_RULES = (
    ("max_days", r"(最多|不超过|at most|max).{0,4}(\d|一|两|三|四).{0,3}(天|days)"),
    ("max_daily_hours", r"(\d|一|两|三|四|五|六).{0,2}(小时|个小时|hours?)"),
    ("lunch", r"午饭|午餐|lunch"),
    ("in_person_only", r"线下|现场|in.person|no online"),
    ("prefer_less_waiting", r"等|空档|gap|wait"),
    ("prefer_fewer_days", r"少去|少来|天数|fewer days|few days"),
    ("prefer_no_early_late", r"太早|太晚|early|late"),
    ("blocked_time", r"打工|上班|兼职|送孩子|照顾|不能|没法|work|can't|cannot|周.|monday|tuesday|wednesday|thursday|friday"),
)


def _fields(label: str, text: str) -> Conditions:
    lowered = text.lower()
    if label == "blocked_time":
        days = sorted({day for name, day in _DAYS.items() if name in lowered}) or [1, 2, 3, 4, 5]
        start, end = (0, 600) if re.search(r"早上|上午|morning|十点前|10点前", lowered) else (0, 1439)
        return {"unavailable_windows": [{"weekday": day, "start_min": start, "end_min": end} for day in days]}
    if label == "prefer_fewer_days":
        return {"cares": ["campus_days"]}
    if label == "prefer_less_waiting":
        return {"cares": ["gap"]}
    if label == "prefer_no_early_late":
        return {"cares": ["outside_hours"]}
    if label == "in_person_only":
        return {"in_person_only": True}
    if label == "lunch":
        return {"lunch": {"start_min": 690, "end_min": 840, "minutes": 30}}
    return {}


def _merge(clauses: list[Clause]) -> Conditions:
    merged: Conditions = {}
    for clause in clauses:
        for key, value in clause["fields"].items():
            if key in ("unavailable_windows", "cares"):
                merged[key] = [*merged.get(key, []), *(v for v in value if v not in merged.get(key, []))]
            else:
                merged[key] = value
    return merged


def parse(text: str) -> ParseResult:
    clauses: list[Clause] = []
    for piece in (part.strip() for part in _SPLIT.split(text)):
        if not piece:
            continue
        label = next((name for name, pattern in _RULES if re.search(pattern, piece, re.IGNORECASE)), "other")
        clauses.append({"text": piece, "label": label, "fields": _fields(label, piece)})
    return {"clauses": clauses, "conditions": _merge(clauses),
            "unrecognised": [clause["text"] for clause in clauses if clause["label"] == "other"]}
