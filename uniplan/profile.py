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
    ("max_days_per_week", 1, 7, "每周最多到校天数须为 1 至 7。"),
    ("max_daily_minutes", 60, 720, "每天最多上课时长须在 1 至 12 小时之间。"),
    ("max_daily_span", 60, 900, "每天最长在校时长须在 1 至 15 小时之间。"),
    ("walk_speed", 20, 120, "步行速度须为每分钟 20 至 120 米。"),
)


def _error(field: str, code: str, message: str) -> dict[str, str]:
    return {"field": field, "code": code, "message": message}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _time_pair(value: Any, field: str, errors: list[dict[str, str]]) -> dict[str, int] | None:
    if not isinstance(value, dict) or set(value) != {"start_min", "end_min"}:
        errors.append(_error(field, "time_shape", "请填写开始和结束时间。"))
        return None
    start, end = value["start_min"], value["end_min"]
    if not _is_int(start) or not _is_int(end) or not 0 <= start < end <= 1440:
        errors.append(_error(field, "time_range", "开始时间须早于结束时间；跨午夜请拆成两段。"))
        return None
    return {"start_min": start, "end_min": end}


def _normalize_windows(raw: Any, errors: list[dict[str, str]]) -> list[dict[str, int]]:
    if not isinstance(raw, list) or len(raw) > 35:
        errors.append(_error("unavailable_windows", "window_count", "最多可填写 35 个不可上课时段。"))
        return []
    windows: list[dict[str, int]] = []
    for index, item in enumerate(raw):
        field = f"unavailable_windows.{index}"
        if not isinstance(item, dict) or set(item) != {"weekday", "start_min", "end_min"}:
            errors.append(_error(field, "window_shape", "请填写星期、开始和结束时间。"))
            continue
        day = item["weekday"]
        if not _is_int(day) or not 1 <= day <= 7:
            errors.append(_error(field, "weekday", "请选择周一至周日。"))
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
        errors.append(_error("weights", "weight_shape", "请提供空档、到校天数和偏好时段三项优先级。"))
        return None
    numbers = [raw[key] for key in WEIGHT_KEYS]
    if any(isinstance(n, bool) or not isinstance(n, (int, float)) or
           not math.isfinite(n) or not 0 <= n <= 5 for n in numbers):
        errors.append(_error("weights", "weight_range", "每项优先级须为 0 至 5 的数字。"))
        return None
    total = sum(numbers)
    if total == 0:
        errors.append(_error("weights", "weight_zero", "三项优先级不能全部为零。"))
        return None
    return {key: numbers[index] / total for index, key in enumerate(WEIGHT_KEYS)}


def _normalize_fields(raw: Any) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    if not isinstance(raw, dict):
        return None, [_error("profile", "object_required", "输入必须是一个表单对象。")]
    errors: list[dict[str, str]] = []
    unknown = sorted(set(raw) - ALLOWED_FIELDS)
    if unknown:
        errors.append(_error("profile", "unknown_fields", "不支持的字段：" + ", ".join(unknown)))
    version = raw.get("schema_version", 1)
    if not _is_int(version) or version != 1:
        errors.append(_error("schema_version", "unsupported_version", "只支持第 1 版输入格式。"))
    year = raw.get("year")
    if not _is_int(year) or not 2000 <= year <= 2100:
        errors.append(_error("year", "invalid_year", "请选择有效的课表年份。"))
    session = raw.get("session_code")
    if not isinstance(session, str) or not SESSION_RE.fullmatch(session.strip().upper()):
        errors.append(_error("session_code", "invalid_session", "请选择有效的学期。"))
        session = None
    else:
        session = session.strip().upper()

    raw_units = raw.get("unit_codes")
    units: list[str] = []
    if not isinstance(raw_units, list):
        errors.append(_error("unit_codes", "units_required", "请填写 1 至 5 门课程代码。"))
    else:
        for index, item in enumerate(raw_units):
            if not isinstance(item, str) or not UNIT_RE.fullmatch(item.strip().upper()):
                errors.append(_error("unit_codes", "invalid_unit", f"第 {index + 1} 个课程代码应为 4 个字母加 4 个数字。"))
                continue
            code = item.strip().upper()
            if code not in units:
                units.append(code)
        if not 1 <= len(units) <= 5:
            errors.append(_error("unit_codes", "unit_count", "每次请输入 1 至 5 门不同课程。"))

    windows = _normalize_windows(raw.get("unavailable_windows", []), errors)
    transition = raw.get("transition_min", 0)
    if not _is_int(transition) or not 0 <= transition <= 120:
        errors.append(_error("transition_min", "transition_range", "换楼缓冲须为 0 至 120 分钟的整数。"))
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
            errors.append(_error("lunch", "lunch_range", "午饭时间须在所给时段内，且至少 10 分钟。"))
            lunch = None
    in_person_only = raw.get("in_person_only", False)
    if not isinstance(in_person_only, bool):
        errors.append(_error("in_person_only", "in_person_type", "“只要现场课”须为是或否。"))
    min_seats = raw.get("min_seats", 0)
    if not _is_int(min_seats) or not 0 <= min_seats <= 50:
        errors.append(_error("min_seats", "min_seats_range", "最少余位须为 0 至 50。"))
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
