"""Read the hand-written test set (one row per clause) into clauses and correct conditions.

Columns (see llm/parse/data/README.md for how to fill them):
    sentence_id, sentence, clause, label, block, max_days, max_class_hours,
    max_campus_hours, lunch, prefer_hours, note
sentence_id and sentence may be left blank on a sentence's second and later rows.
cares and in_person_only are not written by hand: they follow from the label.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from llm.contracts import Clause, Conditions
from llm.parse.extract import merge, merge_windows
from llm.parse.labels import LABELS
from llm.parse.text import DAY_NAMES

COLUMNS = ("sentence_id", "sentence", "clause", "label", "block", "max_days", "max_class_hours",
           "max_campus_hours", "lunch", "prefer_hours", "note")
_DAY = {name.lower(): number for number, name in DAY_NAMES.items()}
_CARES = {"prefer_fewer_days": "campus_days", "prefer_less_waiting": "gap", "prefer_no_early_late": "outside_hours"}


def _minutes(clock: str) -> int:
    hours, _, minutes = clock.strip().partition(":")
    return int(hours) * 60 + int(minutes or 0)


def _days(spec: str) -> list[int]:
    days = []
    for part in spec.lower().split(","):
        first, _, last = part.strip().partition("-")
        start, end = _DAY[first[:3]], _DAY[(last or first)[:3]]
        days += range(start, end + 1)
    return days


def _range(spec: str) -> tuple[int, int]:
    first, last = spec.split("-")
    return _minutes(first), _minutes(last)


def read_block(cell: str) -> list[dict]:
    """'Fri all; Mon-Fri 0:00-10:00' -> unavailable windows (overlaps joined, sorted)."""
    windows = []
    for entry in filter(None, (part.strip() for part in cell.split(";"))):
        days, _, times = entry.partition(" ")
        start, end = (0, 1440) if times.strip().lower() in ("", "all") else _range(times)
        windows += [(day, start, end) for day in _days(days)]
    return merge_windows(windows)


def write_block(windows: list[dict]) -> str:
    """The inverse of read_block, grouping days that share a time."""
    by_time: dict[tuple[int, int], list[int]] = {}
    for window in windows:
        by_time.setdefault((window["start_min"], window["end_min"]), []).append(window["weekday"])
    entries = []
    for (start, end), days in sorted(by_time.items(), key=lambda item: (min(item[1]), item[0])):
        names = ",".join(DAY_NAMES[day] for day in sorted(days))
        if sorted(days) == list(range(min(days), max(days) + 1)) and len(days) > 2:
            names = f"{DAY_NAMES[min(days)]}-{DAY_NAMES[max(days)]}"
        times = "all" if (start, end) == (0, 1440) else f"{_clock(start)}-{_clock(end)}"
        entries.append(f"{names} {times}")
    return "; ".join(entries)


def _clock(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d}"


def row_fields(row: dict) -> Conditions:
    """The correct fields of one clause row."""
    fields: Conditions = {}
    if row.get("block", "").strip():
        fields["unavailable_windows"] = read_block(row["block"])
    if row.get("max_days", "").strip():
        fields["max_days_per_week"] = int(row["max_days"])
    if row.get("max_class_hours", "").strip():
        fields["max_daily_minutes"] = round(float(row["max_class_hours"]) * 60)
    if row.get("max_campus_hours", "").strip():
        fields["max_daily_span"] = round(float(row["max_campus_hours"]) * 60)
    if row.get("lunch", "").strip():
        window, _, minutes = row["lunch"].strip().partition(" ")
        start, end = _range(window)
        fields["lunch"] = {"start_min": start, "end_min": end, "minutes": int(minutes or end - start)}
    if row["label"] == "in_person_only":
        fields["in_person_only"] = True
    if row["label"] in _CARES:
        fields["cares"] = [_CARES[row["label"]]]
    if row.get("prefer_hours", "").strip():
        start, end = _range(row["prefer_hours"])
        fields["preferred_hours"] = {"weekday": 1, "start_min": start, "end_min": end}
    return fields


def fields_to_row(fields: Conditions) -> dict:
    """Clause fields back into the spreadsheet cells (for examples and error reports)."""
    row = {}
    if fields.get("unavailable_windows"):
        row["block"] = write_block(fields["unavailable_windows"])
    if fields.get("max_days_per_week"):
        row["max_days"] = str(fields["max_days_per_week"])
    if fields.get("max_daily_minutes"):
        row["max_class_hours"] = f"{fields['max_daily_minutes'] / 60:g}"
    if fields.get("max_daily_span"):
        row["max_campus_hours"] = f"{fields['max_daily_span'] / 60:g}"
    if fields.get("lunch"):
        lunch = fields["lunch"]
        row["lunch"] = f"{_clock(lunch['start_min'])}-{_clock(lunch['end_min'])} {lunch['minutes']}"
    if fields.get("preferred_hours"):
        hours = fields["preferred_hours"]
        row["prefer_hours"] = f"{_clock(hours['start_min'])}-{_clock(hours['end_min'])}"
    return row


def load(path: str | Path) -> list[dict]:
    """[{id, sentence, clauses: [Clause], conditions}] in file order."""
    sentences: list[dict] = []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            row = {key: (value or "").strip() for key, value in row.items() if key}
            if not row.get("clause"):
                continue
            if row["label"] not in LABELS:
                raise ValueError(f"{path}:{line}: unknown label {row['label']!r}")
            if row.get("sentence_id") and (not sentences or sentences[-1]["id"] != row["sentence_id"]):
                if not row.get("sentence"):
                    raise ValueError(f"{path}:{line}: a new sentence_id needs its sentence")
                sentences.append({"id": row["sentence_id"], "sentence": row["sentence"], "clauses": []})
            elif not sentences:
                raise ValueError(f"{path}:{line}: the first row needs a sentence_id")
            try:
                fields = row_fields(row)
            except (KeyError, ValueError) as error:
                raise ValueError(f"{path}:{line}: cannot read the condition cells ({error})") from error
            clause: Clause = {"text": row["clause"], "label": row["label"], "fields": fields}
            sentences[-1]["clauses"].append(clause)
    for sentence in sentences:
        sentence["conditions"] = merge(sentence["clauses"])
    return sentences


def clause_key(text: str) -> str:
    """Clause text without spaces and punctuation, for comparing splits."""
    return re.sub(r"[\W_]+", "", text.lower())
