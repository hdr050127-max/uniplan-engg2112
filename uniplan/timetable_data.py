"""Module two: read a selected, already cached public timetable snapshot.

This function never makes a network request. It retains the dated meetings for
the later schedule generator and provides a compact summary for the interface.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from .schedule import linked_option_id

from .locations import building_location


class TimetableDataError(Exception):
    """The selected local snapshot cannot be used reliably."""


@dataclass(frozen=True)
class TimetableData:
    meetings: list[dict[str, Any]]
    summary: dict[str, Any]


def _validate_meeting(row: dict[str, Any]) -> None:
    required = ("meeting_id", "unit_code", "group_id", "option_id", "date",
                "start_min", "end_min", "status")
    if any(row.get(field) in (None, "") for field in required):
        raise TimetableDataError("课表快照含缺失的课程标识或时间字段。")
    try:
        date.fromisoformat(row["date"])
        start, end = int(row["start_min"]), int(row["end_min"])
    except (TypeError, ValueError) as exc:
        raise TimetableDataError("课表快照含无法解析的教学日期或时间。") from exc
    if not 0 <= start < end <= 1440:
        raise TimetableDataError("课表快照含无效的上课时间范围。")
    if row["status"] not in {"available", "full", "unknown"}:
        raise TimetableDataError("课表快照含未知格式的班级状态。")


def _option_preview(rows: list[dict[str, Any]]) -> dict[str, Any]:
    first = min(rows, key=lambda row: (row["date"], int(row["start_min"])))
    statuses = {row["status"] for row in rows}
    seats = {row.get("available_seats", "") for row in rows}
    option_id = linked_option_id(first)
    return {
        "option_id": option_id,
        "activity_group": first.get("activity_group", ""),
        "activity_type": first.get("activity_type", ""),
        "class_code": option_id.rpartition("|")[2],
        "first_date": first["date"],
        "weekday": date.fromisoformat(first["date"]).isoweekday(),
        "start_time": first.get("start_time", ""),
        "end_time": first.get("end_time", ""),
        "building_code": first.get("building_code", ""),
        "location_raw": first.get("location_raw", ""),
        "building_location": (building_location(first["building_code"])
                              if first.get("building_code") else None),
        "status": ("full" if "full" in statuses else
                   "available" if statuses == {"available"} else "unknown"),
        "available_seats": next(iter(seats)) if len(seats) == 1 else "",
        "meeting_count": len(rows),
    }


IGN_RE = re.compile(r"(?:^|[-_])IGN$", re.IGNORECASE)


def group_default(group_id: str, activity_types: set[str]) -> tuple[bool, str | None]:
    """Preselect teaching groups; leave source-ignored and non-teaching ones unticked.

    This is only a form default. The student still confirms every group, and
    the result is labelled as their selection, not a verified requirement.
    """
    if IGN_RE.search(group_id.rpartition("|")[2]):
        return False, "来源标记 IGN"
    if activity_types and all("non teaching" in kind.lower() for kind in activity_types):
        return False, "非教学活动（如答疑）"
    return True, None


def load_timetable_data(
    profile: dict[str, Any], snapshot_ref: dict[str, Any], snapshot_catalog: Any,
) -> TimetableData:
    """Return dated meetings and a display summary for the chosen courses.

    ``snapshot_ref`` must identify the same local snapshot that module one
    assessed. Required activity groups are checked separately and may still
    block schedule generation after this read succeeds.
    """
    snapshot = snapshot_catalog.resolve_snapshot(snapshot_ref)
    if snapshot is None:
        raise TimetableDataError("所选课表快照已变化，请刷新页面后重新提交。")
    if snapshot["year"] != profile["year"] or snapshot["session_code"] != profile["session_code"]:
        raise TimetableDataError("课表快照与所选学期不匹配。")

    requested = set(profile["unit_codes"])
    if not requested.issubset(snapshot["unit_codes"]):
        raise TimetableDataError("课表快照缺少所选课程。")
    rows = [row for row in snapshot["rows"] if row.get("unit_code") in requested]
    if not rows or {row["unit_code"] for row in rows} != requested:
        raise TimetableDataError("所选课程没有可用的逐次上课记录。")

    seen_ids: set[str] = set()
    for row in rows:
        _validate_meeting(row)
        if str(row["year"]) != str(profile["year"]) or row["session_code"] != profile["session_code"]:
            raise TimetableDataError("课表快照混入了其他学期的记录。")
        if row["meeting_id"] in seen_ids:
            raise TimetableDataError("课表快照含重复的逐次上课记录。")
        seen_ids.add(row["meeting_id"])

    units = []
    for code in profile["unit_codes"]:
        unit_rows = [row for row in rows if row["unit_code"] == code]
        groups: dict[str, set[str]] = defaultdict(set)
        kinds: dict[str, set[str]] = defaultdict(set)
        options: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in unit_rows:
            option_id = linked_option_id(row)
            groups[row["group_id"]].add(option_id)
            if row.get("activity_type"):
                kinds[row["group_id"]].add(row["activity_type"])
            options[option_id].append(row)
        previews = [_option_preview(option_rows) for _, option_rows in sorted(options.items())]
        by_group_options: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for preview, (_, option_rows) in zip(previews, sorted(options.items())):
            by_group_options[option_rows[0]["group_id"]].append(preview)
        units.append({
            "unit_code": code,
            "meeting_count": len(unit_rows),
            "group_count": len(groups),
            "option_count": len(options),
            "groups": [
                {"group_id": group, "option_count": len(option_ids),
                 "activity_types": sorted(kinds[group]),
                 "default_selected": group_default(group, kinds[group])[0],
                 "default_reason": group_default(group, kinds[group])[1],
                 "options": [{key: preview[key] for key in (
                     "option_id", "class_code", "weekday", "start_time", "end_time",
                     "building_code", "status", "available_seats", "meeting_count")}
                     for preview in sorted(by_group_options[group],
                                           key=lambda item: (item["weekday"], item["start_time"], item["class_code"]))]}
                for group, option_ids in sorted(groups.items())
            ],
            "options_preview": previews[:8],
            "remaining_options": max(0, len(previews) - 8),
        })

    return TimetableData(
        meetings=rows,
        summary={
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_time": snapshot["snapshot_time"],
            "source_url": snapshot["source_url"],
            "meeting_count": len(rows),
            "units": units,
        },
    )
