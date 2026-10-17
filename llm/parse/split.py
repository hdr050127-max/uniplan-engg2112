"""Cut one student sentence into clauses, each meant to carry a single condition.

Rules only. The text is cut at sentence punctuation and at joining words (而且, but,
and ...); then pieces that cannot stand alone are glued back:
- a piece that is only weekdays or times ("Wed", "周三也是") joins the piece before it;
- a piece starting with a reason or condition (因为, if ...) joins the piece after it;
- a piece starting with a back-reference (所以, 那天, so ...) joins the piece before it.
Clause text is always an exact substring of the input.
"""
from __future__ import annotations

import re

from llm.parse.text import find_days, find_parts, find_times, normalize

_CUT = re.compile(
    r"[，。；;！!？?\n]+|(?<!\d),(?!\d)|(?<![\d.])\.(?![\d.])|\s+-\s+"
    r"|而且|并且|但是|不过|可是|另外|此外|再加上|再就是"
    r"|\b(?:but|plus|however|although|though|as well as)\b|\s+and\s+",
    re.IGNORECASE,
)
# Cuts never fall inside these: "between 12 and 2", "9 - 5", "e.g.", "a.m."
_KEEP = re.compile(r"between\s+[\w:.]+\s+and\s+[\w:.]+|\d\s*(?:[ap]\.?m\.?)?\s+-\s+\d|e\.g\.|i\.e\.|\b[ap]\.m\.?",
                   re.IGNORECASE)
_FORWARD = re.compile(r"(?:因为|由于|如果|要是|假如|if\b|because\b|since\b|as long as)", re.IGNORECASE)
_BACKWARD = re.compile(r"(?:所以|因此|那天|那几天|那两天|这几天|这天|那时|这样|其他|其余|别的|so\b|then\b|that day|those days|"
                       r"which\b|other days|the rest)",
                       re.IGNORECASE)
_FILLER = re.compile(r"\s|[、,，/.。]|和|及|与|跟|或|还有|也是|也一样|也不行|同样|也|都"
                     r"|\b(?:and|or|too|as well|also|on|the|every|each|in|at)\b", re.IGNORECASE)
_PLEASANTRY = re.compile(r"(?:谢谢|多谢|thanks?|thank you|please|pls|hi|hello|你好|嗯|ok|okay|好的)[\s!！。.]*",
                         re.IGNORECASE)


def _only_days_or_times(piece: str) -> bool:
    text = normalize(piece)
    marks = [(start, end) for start, end, *_ in (*find_days(text), *find_times(text), *find_parts(text))]
    if not marks:
        return False
    rest = list(text)
    for start, end in marks:
        rest[start:end] = [" "] * (end - start)
    return not _FILLER.sub("", "".join(rest)).strip()


def _spans(text: str) -> list[tuple[int, int]]:
    keep = [match.span() for match in _KEEP.finditer(text)]
    spans, cursor = [], 0
    for match in _CUT.finditer(text):
        if any(start < match.end() and match.start() < end for start, end in keep):
            continue
        spans.append((cursor, match.start()))
        cursor = match.end()
    spans.append((cursor, len(text)))
    trimmed = []
    for start, end in spans:
        piece = text[start:end]
        if piece.strip():
            trimmed.append((start + len(piece) - len(piece.lstrip()), start + len(piece.rstrip())))
    return trimmed


def split_clauses(text: str) -> list[str]:
    spans = _spans(text)
    merged: list[tuple[int, int]] = []
    carry: int | None = None       # start of a piece waiting to join the next one
    for start, end in spans:
        piece = text[start:end]
        if carry is not None:
            start, carry = carry, None
        elif merged and (_BACKWARD.match(piece) or _only_days_or_times(piece)):
            merged[-1] = (merged[-1][0], end)
            continue
        if _FORWARD.match(piece) or len(piece) <= 1:
            carry = start
            continue
        merged.append((start, end))
    if carry is not None:          # a trailing "if possible" belongs to the clause before it
        merged[-1:] = [(merged[-1][0] if merged else carry, spans[-1][1])]
    if len(merged) > 1 and _only_days_or_times(text[slice(*merged[0])]):
        merged[:2] = [(merged[0][0], merged[1][1])]
    clauses = [text[start:end].strip() for start, end in merged]
    return [clause for clause in clauses if clause and not _PLEASANTRY.fullmatch(clause)]
