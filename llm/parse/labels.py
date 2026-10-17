"""The condition types a student's statement can be mapped to.

Each clause of a student's description gets exactly one label. The definitions
and the ordered boundary rules below are the labelling guide for everyone:
whoever writes test sentences, the synthetic-data generator, and the model
prompt all use these same words.

One principle settles most hard-vs-soft questions: the label depends on WHAT
the clause pins down, not on how politely it is said. A named weekday, a clock
time, a number of days or a number of hours is a hard condition ("不想周一上课"
is blocked_time, "最多来三天" is max_days). The only exception is a clock time
softened by a hedge word (最好, 尽量, 如果可以, prefer, ideally, if possible,
rather) with no outside commitment: that becomes prefer_no_early_late, because
preferred_hours can hold it as a soft wish.
"""
from __future__ import annotations

LABELS = {
    "blocked_time": "a named weekday, a clock time, or a part of the day tied to an outside commitment "
                    "(work, childcare, sport, religion, commute, another course) when the student cannot "
                    "or will not have class. Wording strength does not matter: 'no classes before 10am', "
                    "'not on Mondays', 'I don't want Friday classes' are all blocked_time.",
    "max_days": "a NUMBER of days per week on campus (at most 3 days, only two days a week). If the days "
                "themselves are named ('only Tuesday and Thursday'), it is blocked_time instead.",
    "max_daily_hours": "a NUMBER of hours per day, either hours of class or hours spent on campus "
                       "(at most 4 hours of class a day, no more than 8 hours at uni).",
    "lunch": "wants time to eat lunch or a meal break around midday, with or without a time.",
    "in_person_only": "wants only in-person / on-campus classes, no online or recorded ones.",
    "prefer_fewer_days": "prefers coming to campus on fewer days or packing classes together, with no "
                         "number and no named day.",
    "prefer_less_waiting": "dislikes gaps, breaks or waiting between classes; wants classes back to back.",
    "prefer_no_early_late": "a general dislike of early or late classes (not a morning person, hates 8am "
                            "starts) with no named weekday and no outside commitment; also a clock time "
                            "softened by a hedge word ('ideally after 10am', '最好十点以后').",
    "other": "anything else: wishes the scheduler cannot act on (teacher, room, friends, online classes, "
             "number of courses), statements with no timetable wish, or 'anything is fine'.",
}

# Applied top to bottom; the first rule that fits decides. Kept short so people can label by hand.
# How graders applied them in review round 1 is in data/README.md; the prompt below is left as it
# was measured, so the untrained-model numbers stay reproducible.
RULES = (
    "1. A clause about meals or eating at midday is lunch, even when it gives a time ('12 点到 1 点要吃饭').",
    "2. Wanting no online classes is in_person_only. Wanting online classes is other.",
    "3. A count of days per week is max_days; a count of hours per day is max_daily_hours. "
    "Numbers keep the label even with soft words ('最好一周三天' is max_days).",
    "4. A named weekday, a clock time, or an outside commitment with a day or part of the day is "
    "blocked_time, however softly it is said.",
    "5. Exception to 4: a clock time with a hedge word (最好, 尽量, 如果可以, 希望, prefer, ideally, "
    "if possible, rather) and no weekday and no commitment is prefer_no_early_late.",
    "6. Personal tiredness or sleep without a clock time ('早上起不来', 'I'm not a morning person') is "
    "prefer_no_early_late.",
    "7. 'Fewer days', 'classes packed into a few days' (集中), 'not every day' without a number or named day "
    "is prefer_fewer_days.",
    "8. Gaps, waiting, free periods between classes, 'back to back' (连着, 紧凑) is prefer_less_waiting.",
    "9. Everything else is other.",
)

# Hedge words used by rule 5 (also used by the value extractor to decide hard vs soft).
HEDGES = ("最好", "尽量", "如果可以", "如果可能", "可以的话", "能的话", "希望", "倾向",
          "prefer", "ideally", "if possible", "if i can", "would rather", "rather", "preferably",
          "would like", "i'd like", "hopefully")

# Worked examples for the hard cases; also the few-shot block of the model prompt.
EXAMPLES = (
    ("十点前没法上课", "blocked_time"),
    ("我不想周一上课", "blocked_time"),
    ("每天早上要送孩子上学", "blocked_time"),
    ("最好十点以后再上课", "prefer_no_early_late"),
    ("I'm not a morning person", "prefer_no_early_late"),
    ("一周最多来三天", "max_days"),
    ("只想周二周四去学校", "blocked_time"),
    ("课尽量排在一起，少跑几趟", "prefer_fewer_days"),
    ("每天上课别超过五个小时", "max_daily_hours"),
    ("中午要留时间吃饭", "lunch"),
    ("I don't want long breaks between classes", "prefer_less_waiting"),
    ("No online tutorials please", "in_person_only"),
    ("想和室友上同一个 tutorial", "other"),
)

SYSTEM = ("Classify one clause a university student wrote about their timetable into exactly one label.\n"
          "Labels:\n" + "\n".join(f"- {name}: {meaning}" for name, meaning in LABELS.items())
          + "\nRules, first match wins:\n" + "\n".join(RULES)
          + "\nExamples:\n" + "\n".join(f"{text} -> {label}" for text, label in EXAMPLES)
          + "\nAnswer with the label only.")


# Fine-tuned models learn the rules from examples, so they get a short prompt (faster, fewer tokens).
SHORT_SYSTEM = ("Label one clause a student wrote about their timetable with one of: " + ", ".join(LABELS)
                + ". Answer with the label only.")


def messages(text: str) -> list[dict]:
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]


def short_messages(text: str) -> list[dict]:
    return [{"role": "system", "content": SHORT_SYSTEM}, {"role": "user", "content": text}]


def parse_label(output: str) -> str:
    """Pick the label a model produced; anything unrecognised counts as 'other'."""
    cleaned = output.strip().strip('"{}').replace('"label":', "").strip().strip('"')
    if cleaned in LABELS:
        return cleaned
    found = [name for name in LABELS if name in output]
    return max(found, key=len) if found else "other"
