"""Cut one student sentence into clauses, each meant to carry a single condition.

Rules only. The text is cut at sentence punctuation and at joining words (而且, but, and ...);
"and" only cuts when a new clause starts after it ("lectures and tutes" stays whole). Then
pieces that cannot stand alone are glued back, following the splitting rules in data/README.md:
- only weekdays or times ("Wed", "周三也是"), only a hedge ("if possible"), only a number added
  on ("maybe 2", "but 3 is ok", "no more"), "all day" without a weekday, or a back-reference
  (所以, 那天, so, before that, "the happier I am") joins the piece before it;
- 其他天 / other days joins the piece before it unless it brings its own clock time;
- a reason with no time and no request of its own ("I have a casual job", "有兼职") joins its
  neighbour: the piece before it, or the one after it when it comes first;
- a condition opener (因为, if ...) or a lone word ("fewer, longer days") joins the piece after it.
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
_BACKWARD = re.compile(r"(?:所以|因此|那天|那几天|那两天|这几天|这天|那时|这样|那之前|那之后|在那之前|在那之后|so\b|then\b|"
                       r"that day|those days|which\b|before that|after that|"
                       r"the (?:more|less|fewer|earlier|later|better|longer|shorter|\w+ier)\b)", re.IGNORECASE)
_OTHER_DAYS = re.compile(r"(?:其他|其余|别的|other days|the rest)", re.IGNORECASE)
# After "and", a new clause starts with one of these; otherwise "and" joins words ("lectures and tutes").
_AND_CLAUSE = re.compile(r"(?:i|i'm|i'd|i've|i'll|im|id|also|no|not|never|nothing|please|pls|can't|cannot|can not|"
                         r"don't|dont|won't|would|could|prefer\w*|keep|avoid|it|it's|its|there|that's|lunch|gaps?|"
                         r"classes|class|mornings?|evenings?|nights?|max|at most|only|ideally|preferably|if|make|try|"
                         r"want|need|hate|love|on|fewer|less|more|as few|short\w*|long\w*|early|earlier|late|later|"
                         r"online|in[- ]person)\b", re.IGNORECASE)
_TOGETHER = re.compile(r"\b(?:partner|friend|mate|wife|husband|boyfriend|girlfriend|sister|brother|mum|mom|dad|son|"
                       r"daughter|kids?|roommate|flatmate)\s*$", re.IGNORECASE)     # "my partner and I"
_ADDON = re.compile(r"(?:maybe|perhaps|probably|realistically|honestly|but|or|at a push|is|are|"
                    r"would be|could be|be|ok|okay|fine|good|too|days?|hours?|hrs?|天|小时|个|也行|也可以|可以|就行|吧|"
                    r"\d+(?:\.\d+)?|\s|[,，.。!！])+", re.IGNORECASE)
_NO_MORE = re.compile(r"(?:but\s+)?(?:no more|not more|nothing more|no longer|not any more|no more than that)[\s.!。]*",
                      re.IGNORECASE)
_ALL_DAY = re.compile(r"全天|一整天|整天|\ball day\b|\bwhole day\b|\bfull day\b", re.IGNORECASE)
# Words that make a piece a request of its own; a piece with none of them and no time is a reason.
_REQUEST = re.compile(r"不|没|别|想|要求|希望|最好|尽量|只|最多|超过|少|多|早|晚|空|等|吃|饭|线上|线下|网课|课|"
                      r"\b(?:no|not|never|nothing|can'?t|cannot|won'?t|don'?t|avoid|prefer\w*|rather|ideally|want|wanna|"
                      r"need|would|like|hate|love|please|pls|keep|max|most|less|few|fewer|more|possible|least|must|"
                      r"have to|free|clear|busy|"
                      r"fine|ok|okay|good|bad|bother\w*|mind|suit\w*|better|best|too|early|late|mornings?|evenings?|"
                      r"nights?|arvo|afternoons?|gaps?|wait\w*|breaks?|lunch|online|person|zoom|class(?:es)?|"
                      r"lectures?|tut\w*|labs?|out)\b|n't\b|(?<!my )(?<!the )\bonly\b", re.IGNORECASE)
_HEDGE_ONLY = re.compile(r"(?:如果可以的话|如果可以|如果可能的话|如果可能|可以的话|能的话|最好是?|尽量|if possible|if i can|"
                         r"if you can|ideally|preferably|where possible|when possible)[\s!！。.?？]*", re.IGNORECASE)
_DAY_START = re.compile(r"(?:周|星期|礼拜)[一二三四五六日天]|(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\b|\d", re.IGNORECASE)
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


def _time_info(text: str) -> bool:
    return bool(find_days(text) or find_times(text) or find_parts(text) or re.search(r"\d", text))


def _reason(piece: str) -> bool:
    """A statement with no time and no request of its own: the reason for a neighbouring clause."""
    text = normalize(piece)
    return not _time_info(text) and not _REQUEST.search(text)


def _addon(piece: str) -> bool:
    """Only a number (or "no more") added to the clause before it: "maybe 2", "but 3 is ok"."""
    text = normalize(piece)
    return bool(re.search(r"\d", text) and _ADDON.fullmatch(text)) or bool(_NO_MORE.fullmatch(text))


def _all_day_back(piece: str) -> bool:
    """"I have them all day": all day with no weekday refers to the day just named."""
    text = normalize(piece)
    return bool(_ALL_DAY.search(text)) and not find_days(text) and not find_times(text)


def _joins_back(piece: str) -> bool:
    return bool(_BACKWARD.match(piece) or _only_days_or_times(piece) or _HEDGE_ONLY.fullmatch(piece)
                or _addon(piece) or _all_day_back(piece) or _reason(piece)
                or _OTHER_DAYS.match(piece) and not find_times(normalize(piece)))


def _joins_forward(piece: str) -> bool:
    return bool(_FORWARD.match(piece) or len(piece) <= 1 or re.fullmatch(r"[A-Za-z'-]+", piece) or _reason(piece))


def _spans(text: str) -> list[tuple[int, int]]:
    keep = [match.span() for match in _KEEP.finditer(text)]
    spans, cursor = [], 0
    for match in _CUT.finditer(text):
        if any(start < match.end() and match.start() < end for start, end in keep):
            continue
        if match.group().strip().lower() == "and" and (
                _DAY_START.match(text, match.end()) or not _AND_CLAUSE.match(text, match.end())
                or _TOGETHER.search(text, 0, match.start())):
            continue                      # "Tues and Thurs", "lectures and tutes", "my partner and I"
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
        if _PLEASANTRY.fullmatch(piece):
            continue
        if carry is not None:
            start, carry = carry, None
        elif merged and _joins_back(piece):
            merged[-1] = (merged[-1][0], end)
            continue
        if _joins_forward(piece):
            carry = start
            continue
        merged.append((start, end))
    if carry is not None:          # a trailing "if possible" belongs to the clause before it
        merged[-1:] = [(merged[-1][0] if merged else carry, spans[-1][1])]
    if len(merged) > 1 and _only_days_or_times(text[slice(*merged[0])]):
        merged[:2] = [(merged[0][0], merged[1][1])]
    clauses = [text[start:end].strip() for start, end in merged]
    return [clause for clause in clauses if clause and not _PLEASANTRY.fullmatch(clause)]
