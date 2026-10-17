"""Transport-independent entry function for module one: student input.

Times are Australia/Sydney wall-clock minutes on the local teaching date.
Every interval is half-open: [start_min, end_min).
"""

from __future__ import annotations

import math
import re
import secrets
from typing import Any


UNIT_RE = re.compile(r"^[A-Z]{4}[0-9]{4}$")
SESSION_RE = re.compile(r"^[A-Z0-9]+$")
WEIGHT_KEYS = ("gap", "campus_days", "outside_hours")
DEFAULT_HOURS = {"start_min": 540, "end_min": 1080}
ALLOWED_FIELDS = {
    "schema_version", "year", "session_code", "unit_codes",
    "unavailable_windows", "transition_min", "preferred_hours", "weights",
    "max_days_per_week", "max_daily_minutes", "max_daily_span", "lunch",
    "in_person_only", "min_seats", "walk_speed",
}
# Optional lifestyle limits: (field, lowest, highest, message). None switches a limit off.
LIMITS = (
    ("max_days_per_week", 1, 7, "Days on campus a week must be 1 to 7."),
    ("max_daily_minutes", 60, 720, "Hours of class a day must be between 1 and 12."),
    ("max_daily_span", 60, 900, "Hours on campus a day must be between 1 and 15."),
    ("walk_speed", 20, 120, "Walking speed must be 20 to 120 metres a minute."),
)


def _error(field: str, code: str, message: str) -> dict[str, str]:
    return {"field": field, "code": code, "message": message}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _time_pair(value: Any, field: str, errors: list[dict[str, str]]) -> dict[str, int] | None:
    if not isinstance(value, dict) or set(value) != {"start_min", "end_min"}:
        errors.append(_error(field, "time_shape", "Enter a start and an end time."))
        return None
    start, end = value["start_min"], value["end_min"]
    if not _is_int(start) or not _is_int(end) or not 0 <= start < end <= 1440:
        errors.append(_error(field, "time_range", "The start time must be before the end time. Split times past midnight into two."))
        return None
    return {"start_min": start, "end_min": end}


def _normalize_windows(raw: Any, errors: list[dict[str, str]]) -> list[dict[str, int]]:
    if not isinstance(raw, list) or len(raw) > 35:
        errors.append(_error("unavailable_windows", "window_count", "You can add up to 35 times you can't make."))
        return []
    windows: list[dict[str, int]] = []
    for index, item in enumerate(raw):
        field = f"unavailable_windows.{index}"
        if not isinstance(item, dict) or set(item) != {"weekday", "start_min", "end_min"}:
            errors.append(_error(field, "window_shape", "Enter a day, a start time and an end time."))
            continue
        day = item["weekday"]
        if not _is_int(day) or not 1 <= day <= 7:
            errors.append(_error(field, "weekday", "Choose a day from Monday to Sunday."))
            continue
        interval = _time_pair(
            {"start_min": item["start_min"], "end_min": item["end_min"]}, field, errors,
        )
        if interval is not None:
            windows.append({"weekday": day, **interval})
    merged: list[dict[str, int]] = []
    for item in sorted(windows, key=lambda w: (w["weekday"], w["start_min"], w["end_min"])):
        if merged and merged[-1]["weekday"] == item["weekday"] and item["start_min"] <= merged[-1]["end_min"]:
            merged[-1]["end_min"] = max(merged[-1]["end_min"], item["end_min"])
        else:
            merged.append(item.copy())
    return merged


def _normalize_weights(raw: Any, errors: list[dict[str, str]]) -> dict[str, float] | None:
    if raw is None:
        return {key: 1 / 3 for key in WEIGHT_KEYS}
    if not isinstance(raw, dict) or set(raw) != set(WEIGHT_KEYS):
        errors.append(_error("weights", "weight_shape", "Give a priority for waiting, days on campus and preferred hours."))
        return None
    numbers = [raw[key] for key in WEIGHT_KEYS]
    if any(isinstance(n, bool) or not isinstance(n, (int, float)) or
           not math.isfinite(n) or not 0 <= n <= 5 for n in numbers):
        errors.append(_error("weights", "weight_range", "Each priority must be a number from 0 to 5."))
        return None
    total = sum(numbers)
    if total == 0:
        errors.append(_error("weights", "weight_zero", "At least one priority must be above 0."))
        return None
    return {key: numbers[index] / total for index, key in enumerate(WEIGHT_KEYS)}


def _normalize_fields(raw: Any) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    if not isinstance(raw, dict):
        return None, [_error("profile", "object_required", "The request must be a form object.")]
    errors: list[dict[str, str]] = []
    unknown = sorted(set(raw) - ALLOWED_FIELDS)
    if unknown:
        errors.append(_error("profile", "unknown_fields", "Unknown fields: " + ", ".join(unknown)))
    version = raw.get("schema_version", 1)
    if not _is_int(version) or version != 1:
        errors.append(_error("schema_version", "unsupported_version", "Only version 1 of the input format is supported."))
    year = raw.get("year")
    if not _is_int(year) or not 2000 <= year <= 2100:
        errors.append(_error("year", "invalid_year", "Choose a timetable year from the list."))
    session = raw.get("session_code")
    if not isinstance(session, str) or not SESSION_RE.fullmatch(session.strip().upper()):
        errors.append(_error("session_code", "invalid_session", "Choose a semester from the list."))
        session = None
    else:
        session = session.strip().upper()

    raw_units = raw.get("unit_codes")
    units: list[str] = []
    if not isinstance(raw_units, list):
        errors.append(_error("unit_codes", "units_required", "Add 1 to 5 unit codes."))
    else:
        for index, item in enumerate(raw_units):
            if not isinstance(item, str) or not UNIT_RE.fullmatch(item.strip().upper()):
                errors.append(_error("unit_codes", "invalid_unit", f"Unit code {index + 1} should be 4 letters and 4 digits, like ENGG2112."))
                continue
            code = item.strip().upper()
            if code not in units:
                units.append(code)
        if not 1 <= len(units) <= 5:
            errors.append(_error("unit_codes", "unit_count", "Add 1 to 5 different units."))

    windows = _normalize_windows(raw.get("unavailable_windows", []), errors)
    transition = raw.get("transition_min", 0)
    if not _is_int(transition) or not 0 <= transition <= 120:
        errors.append(_error("transition_min", "transition_range", "Time between buildings must be a whole number from 0 to 120 minutes."))
    hours = _time_pair(raw.get("preferred_hours", DEFAULT_HOURS), "preferred_hours", errors)
    weights = _normalize_weights(raw.get("weights"), errors)
    limits = {}
    for field, lowest, highest, message in LIMITS:
        value = raw.get(field)
        if value is not None and (not _is_int(value) or not lowest <= value <= highest):
            errors.append(_error(field, f"{field}_range", message))
        limits[field] = value
    lunch = raw.get("lunch")
    if lunch is not None:
        if (not isinstance(lunch, dict) or set(lunch) != {"start_min", "end_min", "minutes"} or
                not all(_is_int(lunch[key]) for key in lunch) or
                not 0 <= lunch["start_min"] < lunch["end_min"] <= 1440 or
                not 10 <= lunch["minutes"] <= lunch["end_min"] - lunch["start_min"]):
            errors.append(_error("lunch", "lunch_range", "The lunch break must fit inside its time window and be at least 10 minutes."))
            lunch = None
    in_person_only = raw.get("in_person_only", False)
    if not isinstance(in_person_only, bool):
        errors.append(_error("in_person_only", "in_person_type", "\"In-person classes only\" must be yes or no."))
    min_seats = raw.get("min_seats", 0)
    if not _is_int(min_seats) or not 0 <= min_seats <= 50:
        errors.append(_error("min_seats", "min_seats_range", "Minimum seats must be 0 to 50."))
    if errors:
        return None, errors
    return {
        "schema_version": 1,
        "year": year,
        "session_code": session,
        "unit_codes": units,
        "unavailable_windows": windows,
        "preferred_hours": hours,
        "transition_min": transition,
        "weights": weights,
        **limits,
        "lunch": lunch,
        "in_person_only": in_person_only,
        "min_seats": min_seats,
        "time_zone": "Australia/Sydney",
    }, []


CONDITION_FIELDS = ("unavailable_windows", "max_days_per_week", "max_daily_minutes", "max_daily_span",
                    "lunch", "in_person_only", "preferred_hours")


def check_condition_fields(fields: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Keep the parsed profile fields the form would accept; report the rest.

    Each field (and each avoided window) is checked on its own with the same rules
    as a submitted form, so one bad value does not discard the others.
    """
    base = {"schema_version": 1, "year": 2026, "session_code": "X", "unit_codes": ["ABCD1234"]}
    kept: dict[str, Any] = {}
    problems: list[dict[str, str]] = []
    for key, value in fields.items():
        if key not in CONDITION_FIELDS:
            problems.append(_error(key, "unknown_field", f"Unknown condition: {key}"))
            continue
        if key == "unavailable_windows" and isinstance(value, list):
            windows = []
            for window in value:
                _, errors = _normalize_fields({**base, key: [window]})
                if errors:
                    problems.extend(errors)
                else:
                    windows.append(window)
            if windows:
                kept[key] = windows
            continue
        _, errors = _normalize_fields({**base, key: value})
        if errors:
            problems.extend(errors)
        else:
            kept[key] = value
    return kept, problems


def normalize_student_input(raw_input: Any) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """Validate form fields before any optional timetable network request."""
    return _normalize_fields(raw_input)


def prepare_student_profile(raw_input: Any, snapshot_catalog: Any) -> dict[str, Any]:
    """Module-one entry. Returns ready/invalid/needs_data without persistence.

    A ready result's ``profile`` and ``snapshot_ref`` are the module-two inputs.
    The catalogue object supplies ``assess(profile) -> (snapshot_ref, blockers,
    warnings)``. A UI or CLI can supply the same raw mapping.
    """
    profile, errors = _normalize_fields(raw_input)
    if errors:
        return {"status": "invalid", "profile": None, "snapshot_ref": None,
                "errors": errors, "blockers": [], "warnings": []}
    profile["profile_id"] = secrets.token_hex(16)
    snapshot_ref, blockers, warnings = snapshot_catalog.assess(profile)
    return {
        "status": "needs_data" if blockers else "ready",
        "profile": profile,
        "snapshot_ref": snapshot_ref,
        "errors": [], "blockers": blockers,
        "warnings": warnings,
    }
