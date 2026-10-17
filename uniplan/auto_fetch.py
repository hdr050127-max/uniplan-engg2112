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
            return {"status": "cached", "message": "Using the local timetable copy from the last 24 hours."}

        stale_rows: list[dict[str, Any]] = []
        stale_report: dict[str, Any] = {}
        try:
            rows, report = self._collect(profile, offline=True)
            if report["complete"] and self._rows_recent(rows):
                self._store(profile, catalog, rows, report, offline=True)
                return {"status": "cached", "message": "Built the timetable from the local download cache."}
            if report["complete"] and rows:
                stale_rows, stale_report = rows, report
        except (OSError, TimetableError, ValueError):
            # A missing or corrupt cache does not prevent an allowed live lookup.
            pass

        try:
            robots_allowed = self.robots_check()
        except TimetableError as exc:
            return {"status": "failed", "message": f"Could not check the timetable site's rules for automatic access: {exc}"}
        if not robots_allowed and not self.allow_robots_disallowed:
            if stale_rows:
                self._store(profile, catalog, stale_rows, stale_report, offline=True)
                return {
                    "status": "stale_cache",
                    "message": "The timetable site does not allow automatic downloads, so a local copy older than 24 hours is used.",
                }
            return {
                "status": "blocked",
                "message": "The timetable site's robots.txt does not allow automatic requests, so nothing was downloaded. Use a data source you have permission for.",
            }

        try:
            rows, report = self._collect(profile, offline=False)
            self._store(profile, catalog, rows, report, offline=False)
        except (OSError, TimetableError, ValueError) as exc:
            if stale_rows:
                self._store(profile, catalog, stale_rows, stale_report, offline=True)
                return {
                    "status": "stale_cache",
                    "message": f"The live timetable could not be reached ({exc}), so a local copy older than 24 hours is used.",
                }
            return {"status": "failed", "message": f"The live timetable could not be reached: {exc}"}
        if report["complete"]:
            return {"status": "fetched", "message": "Downloaded the public timetable for these units and saved a copy."}
        missing = [code for code, detail in report["units"].items()
                   if detail.get("status") != "ok"]
        return {
            "status": "failed",
            "message": "The download finished, but these units are incomplete: " + ", ".join(missing),
        }
