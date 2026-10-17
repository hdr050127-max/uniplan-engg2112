"""The condition types a student's statement can be mapped to.

Each clause of a student's description gets exactly one label. The rules in
the definitions settle the ambiguous cases (hard limit vs. soft preference).
"""

LABELS = {
    "blocked_time": "a specific day or time the student will not attend (work, care, commute, sport, "
                    "religion, sleep). Includes 'no classes before 10am' or 'not on Mondays', even if "
                    "phrased as 'I don't want'.",
    "max_days": "an explicit number: at most N days per week on campus.",
    "max_daily_hours": "an explicit number: at most N hours of class per day.",
    "lunch": "wants a break to eat lunch.",
    "in_person_only": "wants only in-person / on-campus classes, no online ones.",
    "prefer_fewer_days": "prefers coming to campus on fewer days, with no exact number.",
    "prefer_less_waiting": "dislikes long gaps or waiting time between classes.",
    "prefer_no_early_late": "a general dislike of early or late classes, with no specific cut-off time or day.",
    "other": "anything that is not one of the above.",
}

SYSTEM = ("Classify the student's statement about their timetable into exactly one label.\n"
          + "\n".join(f"- {name}: {meaning}" for name, meaning in LABELS.items())
          + "\nAnswer with the label only.")


def messages(text: str) -> list[dict]:
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]


def parse_label(output: str) -> str:
    """Pick the label a model produced; anything unrecognised counts as 'other'."""
    cleaned = output.strip().strip('"{}').replace('"label":', "").strip().strip('"')
    if cleaned in LABELS:
        return cleaned
    found = [name for name in LABELS if name in output]
    return max(found, key=len) if found else "other"
