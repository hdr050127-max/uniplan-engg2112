"""Shared text rules: normalising, Chinese numerals, weekday names and clock times.

Everything here is plain regular expressions so the runtime stays standard-library only.
Times are minutes after midnight; windows are half-open [start, end).
"""
from __future__ import annotations

import re
import unicodedata

WEEKDAYS = (1, 2, 3, 4, 5)       # "every day" means teaching days
DAY_NAMES = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}

_CN_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
# A Chinese number only counts when a unit follows, so 一周 and 周一 stay words.
_CN_WORD = r"([一二两三四五六七八九]?十[一二三四五六七八九]?|[零〇一二两三四五六七八九])"
_CN_CLOCK = r"([一二两三四五六七八九]?十[一二三四五六七八九]?|[零〇二两三四五六七八九]|(?<![少多早晚快慢好大小高低松些有差])一)"
_CN_NUM = re.compile(r"(?<![周期拜])" + _CN_CLOCK + r"(?=\s*点(?![儿点]))"     # 周一三点 = Monday 3:00; 少一点 = a bit
                     r"|" + _CN_WORD + r"(?=\s*(?:個|个|小时|钟头|天|分|次|节|门|days?\b|hours?\b))")
_EN_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_EN_NUM_RE = re.compile(r"\b(" + "|".join(_EN_NUM) + r")\b")


def _cn_number(word: str) -> int:
    if "十" in word:
        tens, _, ones = word.partition("十")
        return (_CN_DIGIT[tens] if tens else 1) * 10 + (_CN_DIGIT[ones] if ones else 0)
    return _CN_DIGIT[word]


def normalize(text: str) -> str:
    """Lower case, half-width digits and punctuation, Arabic numbers for counts and clock times."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"\b([ap])\.\s?m\.?", r"\1m", text)
    text = text.replace("’", "'").replace("—", "-").replace("–", "-").replace("～", "~")
    text = _CN_NUM.sub(lambda m: str(_cn_number(m.group(1) or m.group(2))), text)
    return _EN_NUM_RE.sub(lambda m: str(_EN_NUM[m.group(1)]), text)


# ---------------------------------------------------------------- weekdays

_ZH_DAY = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}
_ZH_PREFIX = r"(?:周|星期|礼拜)"
_ZH_ITEM = r"[一二三四五六日天](?![天次节个点小])"
_EN_DAY = (r"(mon(?:day)?|tue(?:s(?:day)?)?|wed(?:s|nesday)?|thu(?:r(?:s(?:day)?)?)?|fri(?:day)?|"
           r"sat(?:urday)?|sun(?:day)?)s?\b")
_EN_INDEX = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 7}
_DAY_PATTERNS = (
    ("zh_range", re.compile(_ZH_PREFIX + r"([一二三四五六日天])\s*(?:到|至|-|~)\s*" + _ZH_PREFIX + r"?([一二三四五六日天])")),
    ("en_range", re.compile(r"\b" + _EN_DAY + r"\s*(?:-|to|through|thru|till|until)\s*" + _EN_DAY)),
    ("zh_list", re.compile(_ZH_PREFIX + r"(" + _ZH_ITEM + r"(?:\s*[、,/和及与跟]?\s*" + _ZH_ITEM + r")*)")),
    ("en_day", re.compile(r"\b" + _EN_DAY)),
    ("weekend", re.compile(r"周末|weekends?\b")),
    ("weekdays", re.compile(r"工作日|平日|weekdays?\b|every\s?day|each day|daily|每天|天天|每日|每一天")),
)


def named_days(text: str) -> bool:
    """Whether normalised text names a weekday or the weekend (not just "every day" or "weekdays")."""
    return any(pattern.search(text) for kind, pattern in _DAY_PATTERNS if kind != "weekdays")


def _span(start: int, end: int) -> list[int]:
    return list(range(start, end + 1)) if start <= end else [*range(start, 8), *range(1, end + 1)]


def find_days(text: str) -> list[tuple[int, int, list[int]]]:
    """(start, end, weekdays) for every weekday mention in normalised text, in order."""
    found: list[tuple[int, int, list[int]]] = []
    taken: list[tuple[int, int]] = []
    for kind, pattern in _DAY_PATTERNS:
        for match in pattern.finditer(text):
            if any(match.start() < end and start < match.end() for start, end in taken):
                continue
            if kind == "zh_range":
                days = _span(_ZH_DAY[match.group(1)], _ZH_DAY[match.group(2)])
            elif kind == "en_range":
                days = _span(_EN_INDEX[match.group(1)[:3]], _EN_INDEX[match.group(2)[:3]])
            elif kind == "zh_list":
                days = [_ZH_DAY[char] for char in match.group(1) if char in _ZH_DAY]
            elif kind == "en_day":
                days = [_EN_INDEX[match.group(1)[:3]]]
            elif kind == "weekend":
                days = [6, 7]
            else:
                days = list(WEEKDAYS)
            taken.append((match.start(), match.end()))
            found.append((match.start(), match.end(), days))
    return sorted(found)


# ---------------------------------------------------------------- clock times

_AM_MARK = ("早上", "早晨", "清晨", "上午", "凌晨", "morning")
_PM_MARK = ("下午", "傍晚", "晚上", "夜里", "夜间", "afternoon", "evening", "night", "tonight")
_MARK = r"(?:早上|早晨|清晨|上午|中午|下午|傍晚|晚上|夜里|夜间|早|晚)"     # 早八点, 晚八点
_NOT_UNIT = r"(?!\s*(?:天|个|小时|钟头|分钟|次|节|门|周|%|days?\b|hours?\b|hrs?\b|h\b|mins?\b|minutes?\b|weeks?\b|times\b))"
# One clock time: an optional part-of-day word, an hour, optional minutes, optional am/pm.
CLOCK = (r"(?:" + _MARK + r"\s*)?\d{1,2}(?:\s*[:.]\s*\d{2}|\s*点\s*(?:\d{1,2}\s*分?|半|一刻|三刻)?)?"
         r"(?:\s*(?:am|pm|o'?clock))?" + _NOT_UNIT)
_STRONG = re.compile(r"[:点]|am|pm|o'?clock")     # what makes a lone number a time
_NOON = r"(?:中午|noon|midday|midnight|lunchtime)"
_T = r"(" + CLOCK + r"|" + _NOON + r")"
_BEFORE_WORD = r"(?:before|until|till|by|earlier than|no later than|早于|不晚于)"
_AFTER_WORD = r"(?:after|from|later than|past|no earlier than|晚于|不早于)"
_TIME_PATTERNS = (
    ("range", re.compile(r"between\s*" + _T + r"\s*and\s*" + _T)),
    ("range", re.compile(_T + r"\s*(?:和|与|到|至)\s*" + _T + r"\s*之间")),
    ("range", re.compile(_T + r"\s*(?:到|至|-|~|to|till|until)\s*" + _T)),
    ("before", re.compile(_BEFORE_WORD + r"\s*" + _T)),
    ("before", re.compile(_T + r"\s*(?:之前|以前|前)")),
    ("after", re.compile(_AFTER_WORD + r"\s*" + _T)),
    ("after", re.compile(_T + r"\s*(?:之后|以后|后|起|开始|onwards|or later)")),
    ("point", re.compile(r"(?:at\s*)?(" + CLOCK + r")")),
)
PARTS = (   # part-of-day words with no clock time: (pattern, window)
    (re.compile(r"全天|一整天|整天|all day|whole day|full day"), (0, 1440)),
    (re.compile(r"早上|早晨|清晨|一早|早课|早八|mornings?\b|early\b"), (0, 600)),
    (re.compile(r"上午|before noon"), (0, 720)),
    (re.compile(r"中午|noon|midday|lunchtime"), (720, 840)),
    (re.compile(r"下午|afternoons?\b"), (720, 1080)),
    (re.compile(r"傍晚"), (1020, 1200)),
    (re.compile(r"晚上|夜里|夜间|晚课|evenings?\b|nights?\b|tonight|late\b"), (1080, 1440)),
)


def _marker(text: str) -> str | None:
    """'am' or 'pm' when the clause uses part-of-day words from one side only."""
    am = any(word in text for word in _AM_MARK)
    pm = any(word in text for word in _PM_MARK)
    return "am" if am and not pm else "pm" if pm and not am else None


def clock(token: str, default: str | None = None) -> int:
    """Minutes after midnight for one clock token. Bare hours 1-7 are afternoon (classes run 8am-9pm)."""
    token = token.strip()
    if re.fullmatch(r"中午|noon|midday|lunchtime", token):
        return 720
    if token == "midnight":
        return 1440
    mark = re.match(_MARK, token)
    hour = int(re.search(r"\d{1,2}", token).group())
    minute = 0
    if found := re.search(r"[:.]\s*(\d{2})|点\s*(\d{1,2})", token):
        minute = int(found.group(1) or found.group(2))
    elif "半" in token:
        minute = 30
    elif "一刻" in token:
        minute = 15
    elif "三刻" in token:
        minute = 45
    if "pm" in token and hour < 12:
        hour += 12
    elif "am" in token and hour == 12:
        hour = 0
    elif "am" not in token and "pm" not in token:
        side = (("am" if mark.group() in (*_AM_MARK, "早") else "noon" if mark.group() == "中午" else "pm")
                if mark else default)
        if side == "pm" and hour < 12 or side == "noon" and hour <= 3 or side is None and 1 <= hour <= 7:
            hour += 12
    return min(hour * 60 + minute, 1440)


def find_times(text: str) -> list[tuple[int, int, str, int, int]]:
    """(start, end, kind, a, b) for clock expressions in normalised text, in order.

    kind is "range" (a..b), "before" (a), "after" (a) or "point" (a). Lone numbers only
    count as times inside a range or after before/after words, so '3 days' is not a time."""
    default = _marker(text)
    found: list[tuple[int, int, str, int, int]] = []
    taken: list[tuple[int, int]] = []
    for kind, pattern in _TIME_PATTERNS:
        for match in pattern.finditer(text):
            if any(match.start() < end and start < match.end() for start, end in taken):
                continue
            tokens = [group for group in match.groups() if group]
            if kind == "point" and not _STRONG.search(tokens[0]):
                continue
            if kind == "range" and not (any(_STRONG.search(t) or re.search(_NOON, t) for t in tokens)
                                        or re.search(r"between|之间|从|from|上班|打工|work|shift", text)):
                continue
            if kind in ("before", "after") and not (_STRONG.search(tokens[0]) or re.search(_NOON, tokens[0])
                                                     or re.search(r"[a-z]|于", match.group())):
                continue
            values = [clock(token, default) for token in tokens]
            if kind == "range":
                start, end = values
                if end <= start and end < 720 and not re.search(r"am", tokens[1]):
                    end += 720
                if end <= start:
                    continue
                values = [start, end]
            taken.append((match.start(), match.end()))
            found.append((match.start(), match.end(), kind, values[0], values[-1]))
    return sorted(found)


def find_parts(text: str) -> list[tuple[int, int, tuple[int, int]]]:
    """(start, end, window) for part-of-day words, in order."""
    found = []
    for pattern, window in PARTS:
        found += [(match.start(), match.end(), window) for match in pattern.finditer(text)]
    return sorted(found)


def has_clock(text: str) -> bool:
    return bool(find_times(normalize(text)))
