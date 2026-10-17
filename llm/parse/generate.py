"""Make SYNTHETIC training clauses with Qwen 7B: pick the label first, then ask for sentences.

The label is decided before the model writes anything, so it is right by construction
(apart from the model ignoring the instruction, which the checks below catch). Nothing
here is real student data; every output row says so in its "source" field.

    python3 -m llm.parse.generate                       # uses llm/ollama.py's server
    python3 -m llm.gpu_lock -- python3 -m llm.parse.generate   # when it runs on this Mac

Output: llm/parse/output/synthetic_clauses.jsonl, synthetic_meta.json, and synthetic_dropped.jsonl
(the clauses the checks threw out, with the reason, so the filtering can be inspected).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

from llm import ollama
from llm.parse.gold import clause_key
from llm.parse.labels import HEDGES, LABELS
from llm.parse.text import find_days, find_parts, find_times, normalize

OUTPUT = Path(__file__).resolve().parent / "output"
SOURCE = "synthetic: written by qwen2.5:7b from a fixed label, not real student data"
SEED = 2112

SUBTYPES = {
    "blocked_time": (
        "a part-time job or work shift on one or more named weekdays, with or without the hours",
        "dropping off or picking up children, or caring for a family member, at a time of day or a clock time",
        "sport training, music rehearsal, a religious service, volunteering or another fixed commitment on a "
        "named day or at a named time",
        "not wanting class on a named weekday or at a clock time, worded softly (I don't want, 不太想), "
        "but with NO hedge word such as ideally, if possible, 最好 or 尽量",
        "being able to come only on certain named weekdays, or only during certain hours",
        "a firm clock-time cut-off: cannot have class before or after a certain time",
    ),
    "max_days": (
        "at most a given NUMBER of days per week on campus (write the number, e.g. 2, 3 or 4 days); "
        "never name a weekday",
        "wanting to come in only a given NUMBER of days a week, or saying that NUMBER of days is enough; "
        "never name a weekday",
        "a soft wish with a NUMBER of days per week (ideally 3 days, 最好一周三天); never name a weekday",
    ),
    "max_daily_hours": (
        "at most a given NUMBER of hours of class per day",
        "at most a given NUMBER of hours on campus per day, from the first class to the last",
        "a soft wish with a NUMBER of hours per day",
    ),
    "lunch": (
        "needing a break to eat lunch, with no time given",
        "a lunch break at a given clock time or window, or for a given number of minutes",
    ),
    "in_person_only": (
        "wanting only face-to-face / on-campus classes and no online classes",
        "learning badly online and not wanting Zoom or recorded-only classes",
    ),
    "prefer_fewer_days": (
        "wanting to come to campus on fewer days, with no number and no named weekday",
        "wanting classes packed into as few days as possible because the commute is long, with no number "
        "and no named weekday",
    ),
    "prefer_less_waiting": (
        "disliking long gaps or waiting time between classes",
        "wanting classes back to back with no free periods in between",
    ),
    "prefer_no_early_late": (
        "a general dislike of early-morning classes, with NO clock time (no numbers at all) and NO weekday",
        "a general dislike of late or evening classes, with NO clock time (no numbers at all) and NO weekday",
        "a soft wish with a clock time using a hedge word (ideally, if possible, preferably, 最好, 尽量, "
        "如果可以), with NO weekday and NO reason such as work or children",
    ),
    "other": (
        "wanting a particular teacher, room, building or campus",
        "wanting to be in the same class as a friend or partner",
        "preferring online or recorded classes",
        "something unrelated to time: the degree, feelings about uni, greetings, or 'anything is fine'",
        "the number of units, exams, assignments or workload",
        "saying a named weekday or time is fine for them, without limiting any other day",
    ),
}
LANGUAGES = {
    "zh": "Simplified Chinese, casual, like a Chinese-speaking student in Australia typing in a chat box.",
    "en": "English, casual, like an Australian university student typing in a chat box.",
    "mix": "Chinese with a few English words mixed in (such as Mon, Fri, tutorial, lab, 9am, online, gap), "
           "the way Chinese international students often write.",
}
PERSONAS = ("an international student", "a student with a part-time job", "a parent with young children",
            "a student athlete", "a student who commutes 90 minutes each way", "a mature-age student",
            "a student who cares for a family member", "a first-year student", "a student musician",
            "a student who volunteers")
STYLES = ("very short, under 8 words", "one normal sentence", "a sentence that also gives the reason",
          "polite", "blunt", "no punctuation, a bit sloppy")
# The model often slips on these (names weekdays, adds clock times), so they get more requests.
BOOST = {"max_days": 2.0, "prefer_no_early_late": 2.0, "prefer_fewer_days": 1.5, "prefer_less_waiting": 1.5}
SCHEMA = {"type": "object", "properties": {"clauses": {"type": "array", "items": {"type": "string"}}},
          "required": ["clauses"]}
SYSTEM = ("You write realistic statements that university students type when they describe their timetable "
          "needs to a scheduling app. You follow the requested meaning exactly and return JSON only.")

_DAY_COUNT = re.compile(r"\d+\s*(?:天|次|days?\b|times\b)")
_HOUR_COUNT = re.compile(r"\d+(?:\.\d+)?\s*(?:个)?\s*半?\s*(?:小时|钟头|hours?\b|hrs?\b|h\b)|半(?:个)?小时")
_LUNCH = re.compile(r"午饭|午餐|吃饭|吃午|饭|吃|lunch|eat|meal|food")
_NAMED_DAY = re.compile(r"(?:周|星期|礼拜)[一二三四五六日天1-7](?![天次节个点小])|周末|\bweekends?\b"
                        r"|\b(?:mon|tue|wed|thu|fri|sat|sun)(?:day|s|nesday|rsday|urday)?s?\b")
_ONLINE = re.compile(r"线上|网课|在线|录播|zoom|online|recorded|face|in[- ]person|线下|面授|现场|当面")


def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def prompt(label: str, subtype: str, language: str, persona: str, style: str, count: int) -> list[dict]:
    user = (f"Write {count} different clauses. Every clause must mean exactly this: {subtype}.\n"
            f"(Category for context: {LABELS[label]})\n"
            f"Language: {LANGUAGES[language]}\n"
            f"The writer is {persona}. Style: {style}.\n"
            "Each clause is a single requirement, typed the way a real student would. Vary the wording, the days, "
            "the times and the numbers. Do not add any other requirement. Do not number the clauses.\n"
            'Return JSON: {"clauses": ["...", "..."]}')
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def check(label: str, subtype_index: int, text: str) -> str | None:
    """Why a generated clause cannot be trusted to carry its label, or None if it can."""
    norm = normalize(text)
    if not 2 <= len(text) <= 120:
        return "length"
    days, clock = bool(find_days(norm)), bool(find_times(norm))
    hedged = any(word in norm for word in HEDGES)
    if label == "max_days" and (not _DAY_COUNT.search(norm) or _NAMED_DAY.search(norm)):
        return "no day count, or names a weekday"
    if label == "max_daily_hours" and not _HOUR_COUNT.search(norm):
        return "no hour count"
    if label == "lunch" and not _LUNCH.search(norm):
        return "no meal word"
    if label == "in_person_only" and not _ONLINE.search(norm):
        return "no online/in-person word"
    if label == "blocked_time":
        if not (days or clock or find_parts(norm)):
            return "no day or time"
        if subtype_index == 3 and hedged and not days:
            return "hedged clock time"
    if label == "prefer_no_early_late":
        if _NAMED_DAY.search(norm):
            return "names a weekday"
        if subtype_index < 2 and clock:
            return "has a clock time"
        if subtype_index == 2 and not (clock and hedged):
            return "no hedged clock time"
    if label == "prefer_fewer_days" and (_NAMED_DAY.search(norm) or _DAY_COUNT.search(norm)):
        return "names a weekday or a day count"
    if label == "prefer_less_waiting" and _NAMED_DAY.search(norm):
        return "names a weekday"
    return None


def jobs(per_label: int, count: int) -> list[dict]:
    """Every request, in a fixed order with fixed seeds."""
    rng = random.Random(SEED)
    plan = []
    for label, subtypes in SUBTYPES.items():
        combos = [(index, language) for index in range(len(subtypes)) for language in LANGUAGES]
        requests = -(-round(per_label * BOOST.get(label, 1.0)) // count)
        for number in range(requests):
            index, language = combos[number % len(combos)]
            plan.append({"label": label, "subtype": index, "language": language,
                         "persona": rng.choice(PERSONAS), "style": rng.choice(STYLES),
                         "request": f"{label}/{index}/{language}/{number}",
                         "seed": _seed(SEED, label, index, language, number)})
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--per-label", type=int, default=200, help="clauses to ask for per label")
    parser.add_argument("--count", type=int, default=8, help="clauses per request")
    parser.add_argument("--val-share", type=float, default=0.15)
    parser.add_argument("--limit", type=int, default=0, help="only the first N requests (a dry run)")
    args = parser.parse_args(argv)

    server = ollama.base_url()
    if not ollama.available(args.model):
        print(f"{args.model} is not available on {server}", file=sys.stderr)
        return 1
    print(f"generating with {args.model} on {server}", file=sys.stderr)
    OUTPUT.mkdir(exist_ok=True)
    plan = jobs(args.per_label, args.count)[: args.limit or None]
    rows, seen, dropped, rejected = [], set(), Counter(), []
    started = time.time()
    for number, job in enumerate(plan, 1):
        messages = prompt(job["label"], SUBTYPES[job["label"]][job["subtype"]], job["language"],
                          job["persona"], job["style"], args.count)
        try:
            reply = ollama.chat(args.model, messages, schema=SCHEMA,
                                options={"temperature": 0.9, "top_p": 0.95, "seed": job["seed"]})
            clauses = json.loads(reply)["clauses"]
        except (OSError, ValueError, KeyError) as error:
            print(f"  {job['request']}: failed ({error})", file=sys.stderr)
            dropped["request failed"] += args.count
            continue
        for text in clauses:
            text = str(text).strip().strip('"').strip()
            key = clause_key(text)
            if reason := check(job["label"], job["subtype"], text):
                dropped[reason] += 1
                rejected.append({"text": text, "label": job["label"], "reason": reason, "request": job["request"]})
            elif key in seen:
                dropped["duplicate"] += 1
            else:
                seen.add(key)
                rows.append({"text": text, "label": job["label"], "subtype": job["subtype"],
                             "language": job["language"], "request": job["request"], "source": SOURCE})
        if number % 10 == 0 or number == len(plan):
            print(f"  {number}/{len(plan)} requests, {len(rows)} kept, {time.time() - started:.0f}s",
                  file=sys.stderr)

    # Split by request, so near-duplicates from one request never sit on both sides.
    requests = sorted({row["request"] for row in rows})
    random.Random(SEED).shuffle(requests)
    by_label: dict[str, list[str]] = {}
    for request in requests:
        by_label.setdefault(request.split("/")[0], []).append(request)
    val = {request for group in by_label.values() for request in group[: round(len(group) * args.val_share)]}
    for row in rows:
        row["split"] = "val" if row["request"] in val else "train"

    with open(OUTPUT / "synthetic_clauses.jsonl", "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(OUTPUT / "synthetic_dropped.jsonl", "w", encoding="utf-8") as handle:
        for row in rejected:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    meta = {
        "note": "SYNTHETIC DATA. Every clause was written by a language model from a label chosen in advance. "
                "None of it comes from real students. Use it for training and validation only, never as the test set.",
        "model": args.model, "server": server, "seed": SEED, "per_label": args.per_label,
        "clauses_per_request": args.count, "requests": len(plan),
        "kept": len(rows), "dropped": dict(dropped),
        "by_label": dict(Counter(row["label"] for row in rows)),
        "by_language": dict(Counter(row["language"] for row in rows)),
        "by_split": dict(Counter(row["split"] for row in rows)),
        "seconds": round(time.time() - started),
        "date": time.strftime("%Y-%m-%d"),
    }
    (OUTPUT / "synthetic_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
