"""Fetch only requested public timetable units when a student submits a form.

The existing scraper handles rate limiting and its raw response cache. This
adapter reuses recent processed snapshots, tries offline cache first, and
checks the site's crawler policy before any live request.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from timetable_scraper import (SYDNEY, TimetableError, collect,
                               robots_allows_requests, write_outputs)

from .catalog import SnapshotCatalog


class AutoFetcher:
    def __init__(
        self, root: Path, *, allow_robots_disallowed: bool = False,
        robots_check: Callable[[], bool] = robots_allows_requests,
        collector: Callable[..., tuple[list[dict[str, Any]], dict[str, Any]]] = collect,
    ) -> None:
        self.cache_dir = root / "data/timetable_cache"
        self.allow_robots_disallowed = allow_robots_disallowed
        self.robots_check = robots_check
        self.collector = collector

    @staticmethod
    def _recent_snapshot(profile: dict[str, Any], catalog: SnapshotCatalog) -> bool:
        requested = set(profile["unit_codes"])
        for snap in catalog.snapshots:
            if (snap["year"] != profile["year"] or
                    snap["session_code"] != profile["session_code"] or
                    not requested.issubset(snap["unit_codes"])):
                continue
            try:
                stamp = datetime.fromisoformat(snap["snapshot_time"])
                age = datetime.now(SYDNEY) - stamp
                if stamp.tzinfo is not None and timedelta(0) <= age < timedelta(hours=24):
                    return True
            except (TypeError, ValueError):
                continue
        return False

    @staticmethod
    def _rows_recent(rows: list[dict[str, Any]]) -> bool:
        if not rows:
            return False
        now = datetime.now(SYDNEY)
        try:
            ages = [now - datetime.fromisoformat(row["snapshot_time"]) for row in rows]
        except (KeyError, TypeError, ValueError):
            return False
        return all(timedelta(0) <= age < timedelta(hours=24) for age in ages)

    def _store(
        self, profile: dict[str, Any], catalog: SnapshotCatalog,
        rows: list[dict[str, Any]], report: dict[str, Any], *, offline: bool,
    ) -> None:
        codes = profile["unit_codes"]
        if rows:
            slug = "_".join(sorted(codes))
            today = datetime.now(SYDNEY).strftime("%Y%m%d")
            output = catalog.processed_dir / (
                f"timetable_meetings_{profile['year']}_{profile['session_code']}_{slug}_{today}.csv"
            )
            report["robots_policy"] = "offline" if offline else (
                "disallowed_override" if self.allow_robots_disallowed else "allowed"
            )
            write_outputs(rows, report, output)
            catalog.refresh()

    def _collect(self, profile: dict[str, Any], *, offline: bool
                 ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return self.collector(
            profile["unit_codes"], profile["year"], profile["session_code"],
            self.cache_dir, offline=offline,
        )

    def ensure(self, profile: dict[str, Any], catalog: SnapshotCatalog) -> dict[str, Any]:
        """Get a usable snapshot or explain exactly why fetching stopped."""
        if self._recent_snapshot(profile, catalog):
            return {"status": "cached", "message": "已使用最近 24 小时内的本地课表快照。"}

        stale_rows: list[dict[str, Any]] = []
        stale_report: dict[str, Any] = {}
        try:
            rows, report = self._collect(profile, offline=True)
            if report["complete"] and self._rows_recent(rows):
                self._store(profile, catalog, rows, report, offline=True)
                return {"status": "cached", "message": "已从本地抓取缓存生成课表快照。"}
            if report["complete"] and rows:
                stale_rows, stale_report = rows, report
        except (OSError, TimetableError, ValueError):
            # A missing or corrupt cache does not prevent an allowed live lookup.
            pass

        try:
            robots_allowed = self.robots_check()
        except TimetableError as exc:
            return {"status": "failed", "message": f"无法核查课表网站的自动访问规则：{exc}"}
        if not robots_allowed and not self.allow_robots_disallowed:
            if stale_rows:
                self._store(profile, catalog, stale_rows, stale_report, offline=True)
                return {
                    "status": "stale_cache",
                    "message": "实时抓取被网站规则阻止，只能使用超过 24 小时的本地缓存。",
                }
            return {
                "status": "blocked",
                "message": "已自动检查公开课表，但网站的 robots.txt 禁止自动请求；未进行实时抓取。请使用已授权的数据来源或在获得访问许可后启用实时查询。",
            }

        try:
            rows, report = self._collect(profile, offline=False)
            self._store(profile, catalog, rows, report, offline=False)
        except (OSError, TimetableError, ValueError) as exc:
            if stale_rows:
                self._store(profile, catalog, stale_rows, stale_report, offline=True)
                return {
                    "status": "stale_cache",
                    "message": f"实时查询失败（{exc}），只能使用超过 24 小时的本地缓存。",
                }
            return {"status": "failed", "message": f"实时课表查询失败：{exc}"}
        if report["complete"]:
            return {"status": "fetched", "message": "已自动获取所选课程的公开课表并保存快照。"}
        missing = [code for code, detail in report["units"].items()
                   if detail.get("status") != "ok"]
        return {
            "status": "failed",
            "message": "查询完成，但未取得这些课程的完整课表：" + ", ".join(missing),
        }
