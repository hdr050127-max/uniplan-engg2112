"""Local unit-name suggestions and timetable snapshot readiness checks."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def load_unit_catalog(path: Path, overlays: tuple[Path, ...] = ()) -> list[dict[str, str]]:
    units: dict[str, str] = {}
    for source in (path, *overlays):
        if not source.is_file():
            continue
        with source.open(newline="", encoding="utf-8-sig") as handle:
            rows = csv.DictReader(handle)
            for row in rows:
                code = (row.get("unit_code") or "").strip().upper()
                name = (row.get("unit_name") or "").strip()
                if len(code) == 8 and name:
                    units.setdefault(code, name)
    return [{"unit_code": code, "unit_name": name} for code, name in sorted(units.items())]


def suggest_units(
    query: str, unit_catalog: list[dict[str, str]], available_codes: set[str],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search local data; no network requests while the student types."""
    needle = query.strip().casefold()
    if len(needle) < 2 or limit < 1:
        return []
    matches: list[tuple[int, bool, str, dict[str, Any]]] = []
    for row in unit_catalog:
        code, name = row["unit_code"], row["unit_name"]
        code_fold, name_fold = code.casefold(), name.casefold()
        if code_fold.startswith(needle):
            rank = 0
        elif name_fold.startswith(needle):
            rank = 1
        elif needle in name_fold:
            rank = 2
        else:
            continue
        matches.append((rank, code not in available_codes, code, {
            "unit_code": code, "unit_name": name,
            "available_in_snapshot": code in available_codes,
        }))
    matches.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in matches[:limit]]


class SnapshotCatalog:
    def __init__(self, processed_dir: Path, requirements_dir: Path):
        self.processed_dir = processed_dir
        self.requirements_dir = requirements_dir
        self.snapshots = self._load_snapshots()

    def refresh(self) -> None:
        """Load snapshots produced after the web service started."""
        self.snapshots = self._load_snapshots()

    def _load_snapshots(self) -> list[dict[str, Any]]:
        snapshots = []
        for report_path in sorted(self.processed_dir.glob("*_report.json")):
            csv_path = report_path.with_name(report_path.name.removesuffix("_report.json") + ".csv")
            if not csv_path.is_file():
                continue
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                with csv_path.open(newline="", encoding="utf-8-sig") as handle:
                    rows = list(csv.DictReader(handle))
            except (OSError, ValueError, csv.Error):
                continue
            if not isinstance(report, dict) or not rows or not isinstance(report.get("units"), dict):
                continue
            year, session = report.get("year"), report.get("session_code")
            units = {code for code, detail in report["units"].items()
                     if isinstance(detail, dict) and detail.get("status") == "ok"}
            actual = {row.get("unit_code") for row in rows
                      if str(row.get("year")) == str(year) and row.get("session_code") == session}
            units &= actual
            snapshots.append({
                "snapshot_id": csv_path.stem,
                "year": year,
                "session_code": session,
                "unit_codes": sorted(units),
                "rows": rows,
                "snapshot_time": max((row.get("snapshot_time") or "") for row in rows),
                "source_url": rows[0].get("source_url", ""),
            })
        return snapshots

    def public_snapshots(self) -> list[dict[str, Any]]:
        return [{key: snap[key] for key in (
            "snapshot_id", "year", "session_code", "unit_codes", "snapshot_time",
        )} for snap in self.snapshots]

    def resolve_snapshot(self, ref: dict[str, Any]) -> dict[str, Any] | None:
        """Resolve only the exact snapshot previously selected by module one."""
        if not isinstance(ref, dict):
            return None
        return next((snap for snap in self.snapshots
                     if all(snap.get(key) == ref.get(key) for key in (
                         "snapshot_id", "year", "session_code", "snapshot_time",
                     ))), None)

    def _combine(self, same_term: list[dict[str, Any]], units: list[str]) -> dict[str, Any]:
        """Join each unit's latest snapshot so courses fetched on different days can be planned.

        The result is registered so ``resolve_snapshot`` finds it; its time is
        the oldest part, so freshness warnings stay conservative.
        """
        parts = {unit: max((snap for snap in same_term if unit in snap["unit_codes"]),
                           key=lambda item: item["snapshot_time"]) for unit in sorted(units)}
        snapshot_id = "combined:" + "+".join(f"{unit}@{snap['snapshot_id']}" for unit, snap in parts.items())
        existing = next((snap for snap in self.snapshots if snap["snapshot_id"] == snapshot_id), None)
        if existing:
            return existing
        first = next(iter(parts.values()))
        combined = {
            "snapshot_id": snapshot_id, "year": first["year"], "session_code": first["session_code"],
            "unit_codes": sorted(units),
            "rows": [row for unit, snap in parts.items() for row in snap["rows"] if row.get("unit_code") == unit],
            "snapshot_time": min(snap["snapshot_time"] for snap in parts.values()),
            "source_url": first["source_url"],
            "combined_from": {unit: snap["snapshot_time"] for unit, snap in parts.items()},
        }
        self.snapshots.append(combined)
        return combined

    def available_codes(self, year: int, session: str) -> set[str]:
        return {code for snap in self.snapshots
                if snap["year"] == year and snap["session_code"] == session
                for code in snap["unit_codes"]}

    def _requirements_blockers(
        self, year: int, session: str, units: list[str], rows: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        path = self.requirements_dir / f"requirements_{year}_{session}.json"
        if not path.is_file():
            return [{"code": "requirements_unverified", "message": "必修活动组尚未核实，暂不能生成课表。"}]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return [{"code": "requirements_invalid", "message": "必修活动组核实文件无法读取。"}]
        if data.get("year") != year or data.get("session_code") != session:
            return [{"code": "requirements_mismatch", "message": "必修活动组与所选学期不匹配。"}]
        verified = data.get("verified_units")
        if not isinstance(verified, dict):
            return [{"code": "requirements_invalid", "message": "必修活动组核实文件格式不正确。"}]
        blockers = []
        for unit in units:
            record = verified.get(unit)
            available_groups = {row.get("group_id") for row in rows if row.get("unit_code") == unit}
            if (not isinstance(record, dict) or
                    not isinstance(record.get("group_ids"), list) or
                    not record["group_ids"] or
                    not all(isinstance(group, str) and group for group in record["group_ids"]) or
                    not set(record["group_ids"]).issubset(available_groups) or
                    not record.get("source_url") or not record.get("snapshot_time")):
                blockers.append({"code": "requirements_unverified", "message": f"{unit} 的必修活动组尚未核实。"})
        return blockers

    def verified_group_ids(
        self, profile: dict[str, Any], rows: list[dict[str, Any]],
    ) -> dict[str, list[str]]:
        """Return the checked required groups; never infer them from the CSV."""
        year, session, units = profile["year"], profile["session_code"], profile["unit_codes"]
        blockers = self._requirements_blockers(year, session, units, rows)
        if blockers:
            raise ValueError(blockers[0]["message"])
        path = self.requirements_dir / f"requirements_{year}_{session}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return {unit: data["verified_units"][unit]["group_ids"] for unit in units}

    def assess(self, profile: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, str]], list[dict[str, str]]]:
        year, session, units = profile["year"], profile["session_code"], profile["unit_codes"]
        same_term = [snap for snap in self.snapshots
                     if snap["year"] == year and snap["session_code"] == session]
        if not same_term:
            return None, [{"code": "missing_session", "message": "该学期尚无可用的课表快照。"}], []
        candidates = [snap for snap in same_term if set(units).issubset(snap["unit_codes"])]
        warnings = []
        if not candidates:
            known = self.available_codes(year, session)
            missing = [unit for unit in units if unit not in known]
            if missing:
                return None, [{"code": "missing_timetable", "message": "缺少这些课程的课表：" + ", ".join(missing)
                               + "。实时查询受限时，请在学校官方课表网站核对这些课程。"}], []
            combined = self._combine(same_term, units)
            candidates = [combined]
            warnings.append({"code": "mixed_snapshots", "message": "所选课程来自不同日期的快照，已按每门课最新的一份合并：" +
                             "、".join(f"{unit} {stamp[:10]}" for unit, stamp in combined["combined_from"].items()) +
                             "。数据日期按最早的一份显示。"})
        snap = max(candidates, key=lambda item: item["snapshot_time"])
        rows = [row for row in snap["rows"] if row.get("unit_code") in units
                and str(row.get("year")) == str(year) and row.get("session_code") == session]
        ref = {key: snap[key] for key in ("snapshot_id", "year", "session_code", "snapshot_time", "source_url")}
        blockers = self._requirements_blockers(year, session, units, rows)
        unknown_status = sum(row.get("status") == "unknown" for row in rows)
        unknown_building = sum(not row.get("building_code") for row in rows)
        if unknown_status:
            warnings.append({"code": "unknown_status", "message": f"有 {unknown_status} 次课程的状态未知，后续结果须核对。"})
        if unknown_building:
            warnings.append({"code": "unknown_building", "message": f"有 {unknown_building} 次活动未标识教学楼（可能包括在线活动），换楼缓冲无法检查这些记录。"})
        return ref, blockers, warnings
