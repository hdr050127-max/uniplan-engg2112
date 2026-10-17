"""Collect and normalise public Sydney timetable meetings for specified units.

The public timetable is a JavaScript application. This module uses the same
subject and location requests as its search page; those endpoints are not a
published API and may change. Only explicit unit codes are queried.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo


BASE_URL = "https://timetable.sydney.edu.au/even"
SUBJECTS_URL = f"{BASE_URL}/rest/timetable/subjects"
PAGE_URL = f"{BASE_URL}/timetable/"
ROBOTS_URL = "https://timetable.sydney.edu.au/robots.txt"
SYDNEY = ZoneInfo("Australia/Sydney")
USER_AGENT = "UniPlan student project (small, user-requested timetable lookup)"
UNIT_RE = re.compile(r"^[A-Z]{4}[0-9]{4}$")
SESSION_RE = re.compile(r"^[A-Z0-9]+$")
BUILDING_RE = re.compile(r"^([A-Z][A-Z0-9]*)\.")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

FIELDS = (
    "meeting_id", "unit_code", "year", "session_code", "subject_offering",
    "group_id", "option_id", "activity_group", "activity_type", "class_code",
    "date", "start_min", "end_min", "start_time", "end_time",
    "location_raw", "building_code", "status", "status_raw",
    "available_seats", "source_url", "snapshot_time",
)
SUBJECT_FIELDS = {"callista_code", "semester", "activities"}
ACTIVITY_FIELDS = {
    "activity_group_code", "activity_code", "activity_type", "start_time",
    "duration", "day_of_week", "activitiesDays", "location", "selectable",
    "availability",
}
LOCATION_FIELDS = {"description", "id", "activityDays"}


class TimetableError(Exception):
    """A requested timetable could not be fetched or reliably parsed."""


def normalise_codes(values: list[str]) -> list[str]:
    """Accept space- or comma-separated unit codes and remove duplicates."""
    codes = []
    for value in values:
        for part in value.split(","):
            code = part.strip().upper()
            if not code:
                continue
            if not UNIT_RE.fullmatch(code):
                raise TimetableError(f"Invalid unit code: {part!r}")
            if code not in codes:
                codes.append(code)
    if not codes:
        raise TimetableError("At least one unit code is required")
    if len(codes) > 10:
        raise TimetableError("Limit one run to at most 10 unit codes")
    return codes


def parse_date(value: str) -> date:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Invalid teaching date: {value!r}")


def time_to_minutes(value: str) -> int:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value.strip())
    if not match:
        raise ValueError(f"Invalid time: {value!r}")
    hours, minutes = map(int, match.groups())
    if hours > 23 or minutes > 59:
        raise ValueError(f"Invalid time: {value!r}")
    return hours * 60 + minutes


def normalise_status(raw: object) -> str:
    value = str(raw or "").strip().lower()
    if value in {"available", "select", "open"}:
        return "available"
    if value in {"full", "closed"}:
        return "full"
    return "unknown"


def building_code(location: str) -> str:
    """Return a building only when every listed room is in the same building."""
    if not location or location.strip() == "-":
        return ""
    parts = re.split(r",\s*(?=[A-Z][A-Z0-9]*\.)|\s+\|\s+", location)
    matches = [BUILDING_RE.match(part.strip()) for part in parts]
    if any(match is None for match in matches):
        return ""
    codes = {match.group(1) for match in matches if match is not None}
    return next(iter(codes)) if len(codes) == 1 else ""


def _iso_now() -> str:
    return datetime.now(SYDNEY).isoformat(timespec="seconds")


def _request_json(url: str, form: dict[str, str] | None = None) -> dict:
    body = urlencode(form).encode("utf-8") if form is not None else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = Request(url, data=body, headers=headers, method="POST" if body else "GET")
    for attempt in range(3):
        try:
            with urlopen(request, timeout=25) as response:
                if "json" not in response.headers.get("Content-Type", "").lower():
                    raise TimetableError(f"Non-JSON response from {url}")
                result = json.load(response)
                if not isinstance(result, dict):
                    raise TimetableError(f"Unexpected response structure from {url}")
                return result
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise TimetableError(f"HTTP {exc.code} from {url}") from exc
        except (URLError, TimeoutError) as exc:
            if attempt == 2:
                raise TimetableError(f"Network error from {url}: {exc}") from exc
        time.sleep(2 ** attempt)
    raise AssertionError("retry loop exhausted")


def robots_text_allows_requests(text: str) -> bool:
    """Parse robots rules, including the site's observed one-line formatting."""
    fixed = re.sub(
        r"\s+(?=(?:User-agent|Allow|Disallow|Crawl-delay|Sitemap):)",
        "\n", text, flags=re.IGNORECASE,
    )
    parser = RobotFileParser()
    parser.parse(fixed.splitlines())
    return parser.can_fetch(USER_AGENT, SUBJECTS_URL) and parser.can_fetch(
        USER_AGENT, f"{BASE_URL}/rest/timetable/subject/example/location"
    )


def robots_allows_requests() -> bool:
    """Check the site's published crawler policy before a live run."""
    request = Request(ROBOTS_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=15) as response:
            text = response.read().decode("utf-8", "replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise TimetableError(f"Could not check {ROBOTS_URL}: {exc}") from exc
    return robots_text_allows_requests(text)


def minimise_payload(key: str, data: dict) -> dict:
    """Cache only fields used by this module, omitting staff and contact details."""
    if key.startswith("subjects_"):
        result = {}
        for offering, subject in data.items():
            if not isinstance(subject, dict):
                continue
            slim = {name: subject[name] for name in SUBJECT_FIELDS - {"activities"}
                    if name in subject}
            activities = subject.get("activities")
            slim["activities"] = {
                option: {name: activity[name] for name in ACTIVITY_FIELDS if name in activity}
                for option, activity in activities.items() if isinstance(activity, dict)
            } if isinstance(activities, dict) else None
            result[offering] = slim
        return result
    if key.startswith("locations_"):
        return {
            option: [
                {name: item[name] for name in LOCATION_FIELDS if name in item}
                for item in values if isinstance(item, dict)
            ]
            for option, values in data.items() if isinstance(values, list)
        }
    return data


class TimetableClient:
    def __init__(self, cache_dir: Path, *, offline: bool = False, delay: float = 1.0,
                 max_age_hours: float = 24.0):
        self.cache_dir = cache_dir
        self.offline = offline
        self.delay = delay
        self.max_age = timedelta(hours=max_age_hours)
        self.last_request = 0.0
        cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, url: str, form: dict[str, str] | None = None) -> tuple[dict, str]:
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                fetched = datetime.fromisoformat(cached["snapshot_time"])
                if self.offline or datetime.now(SYDNEY) - fetched <= self.max_age:
                    slim = minimise_payload(key, cached["data"])
                    if slim != cached["data"]:
                        cached["data"] = slim
                        path.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")
                    return slim, cached["snapshot_time"]
            except (ValueError, KeyError, TypeError):
                if self.offline:
                    raise TimetableError(f"Invalid offline cache: {path}")
        if self.offline:
            raise TimetableError(f"No cached data for {key}")
        remaining = self.delay - (time.monotonic() - self.last_request)
        if remaining > 0:
            time.sleep(remaining)
        try:
            data = minimise_payload(key, _request_json(url, form))
        finally:
            self.last_request = time.monotonic()
        stamp = _iso_now()
        path.write_text(json.dumps({"snapshot_time": stamp, "url": url, "data": data},
                                   ensure_ascii=False), encoding="utf-8")
        return data, stamp


def _locations_by_date(location_data: object) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if not isinstance(location_data, list):
        return result
    for location in location_data:
        if not isinstance(location, dict):
            continue
        label = str(location.get("description") or location.get("id") or "").strip()
        if not label or label == "-":
            continue
        for raw_date in location.get("activityDays") or []:
            try:
                day = parse_date(str(raw_date)).isoformat()
            except ValueError:
                continue
            labels = result.setdefault(day, [])
            if label not in labels:
                labels.append(label)
    return result


def clean_subjects(subjects: dict, locations: dict[str, dict], *, code: str,
                   year: int, session: str, snapshot_time: str) -> tuple[list[dict], list[str]]:
    """Expand activityDays to meeting rows; return rows and validation warnings."""
    rows: list[dict] = []
    warnings: list[str] = []
    matched_offerings = 0
    for offering_id, subject in sorted(subjects.items()):
        if not isinstance(subject, dict):
            continue
        if str(subject.get("callista_code", "")).upper() != code:
            continue
        if str(subject.get("semester", "")).upper() != session:
            continue
        matched_offerings += 1
        activities = subject.get("activities")
        if not isinstance(activities, dict):
            warnings.append(f"{offering_id}: missing activities")
            continue
        for source_key, activity in sorted(activities.items()):
            if not isinstance(activity, dict):
                warnings.append(f"{source_key}: invalid activity")
                continue
            dates = activity.get("activitiesDays")
            if not isinstance(dates, list) or not dates:
                warnings.append(f"{source_key}: missing explicit teaching dates")
                continue
            try:
                start_min = time_to_minutes(str(activity["start_time"]))
                duration = int(activity["duration"])
                end_min = start_min + duration
                if duration <= 0 or end_min > 1440:
                    raise ValueError("non-positive or overnight duration")
            except (KeyError, TypeError, ValueError) as exc:
                warnings.append(f"{source_key}: invalid time/duration ({exc})")
                continue
            group = str(activity.get("activity_group_code") or "").strip()
            class_code = str(activity.get("activity_code") or "").strip()
            if (not group or not class_code or
                    not source_key.startswith(f"{offering_id}|{group}|")):
                warnings.append(f"{source_key}: missing group or class identifier")
                continue
            status_raw = str(activity.get("selectable") or "").strip()
            status = normalise_status(status_raw)
            if status == "unknown":
                warnings.append(f"{source_key}: unknown status {status_raw!r}")
            availability = activity.get("availability")
            try:
                seats = int(availability) if availability not in (None, "", "-", -1, "-1") else ""
                if seats != "" and seats < 0:
                    raise ValueError("negative availability")
            except (TypeError, ValueError):
                seats = ""
                warnings.append(f"{source_key}: invalid seat count {availability!r}")
            daily_locations = _locations_by_date(locations.get(offering_id, {}).get(source_key))
            raw_location = str(activity.get("location") or "").strip()
            for raw_date in dates:
                try:
                    day = parse_date(str(raw_date))
                except ValueError as exc:
                    warnings.append(f"{source_key}: {exc}")
                    continue
                if day.year != year:
                    warnings.append(f"{source_key}: date outside {year}: {day}")
                    continue
                stated_weekday = str(activity.get("day_of_week") or "").strip()[:3]
                if stated_weekday and stated_weekday != WEEKDAYS[day.weekday()]:
                    warnings.append(f"{source_key}: weekday mismatch on {day}")
                    continue
                location = " | ".join(daily_locations.get(day.isoformat(), [])) or raw_location
                digest = hashlib.sha1(
                    f"{source_key}|{day}|{start_min}|{end_min}|{location}".encode()
                ).hexdigest()[:16]
                rows.append({
                    "meeting_id": digest,
                    "unit_code": code,
                    "year": year,
                    "session_code": session,
                    "subject_offering": offering_id,
                    "group_id": f"{offering_id}|{group}",
                    "option_id": source_key,
                    "activity_group": group,
                    "activity_type": str(activity.get("activity_type") or "").strip(),
                    "class_code": class_code,
                    "date": day.isoformat(),
                    "start_min": start_min,
                    "end_min": end_min,
                    "start_time": f"{start_min // 60:02d}:{start_min % 60:02d}",
                    "end_time": f"{end_min // 60:02d}:{end_min % 60:02d}",
                    "location_raw": location,
                    "building_code": building_code(location),
                    "status": status,
                    "status_raw": status_raw,
                    "available_seats": seats,
                    "source_url": PAGE_URL,
                    "snapshot_time": snapshot_time,
                })
    if matched_offerings == 0:
        warnings.append(f"{code}: no offering in session {session}")
    unique = {row["meeting_id"]: row for row in rows}
    if len(unique) < len(rows):
        warnings.append(f"{code}: removed {len(rows) - len(unique)} duplicate meetings")
    return list(unique.values()), warnings


def collect(codes: list[str], year: int, session: str, cache_dir: Path,
            *, offline: bool = False, refresh: bool = False) -> tuple[list[dict], dict]:
    client = TimetableClient(cache_dir, offline=offline,
                             max_age_hours=0.0 if refresh else 24.0)
    rows: list[dict] = []
    report: dict = {"year": year, "session_code": session, "requested_units": codes,
                    "units": {}, "warnings": []}
    for code in codes:
        try:
            subjects, stamp = client.get(f"subjects_{code}", SUBJECTS_URL,
                                          {"search-term": code})
            offerings = {
                key: value for key, value in subjects.items()
                if isinstance(value, dict)
                and str(value.get("callista_code", "")).upper() == code
                and str(value.get("semester", "")).upper() == session
            }
            locations: dict[str, dict] = {}
            for offering_id in offerings:
                endpoint = f"{BASE_URL}/rest/timetable/subject/{quote(offering_id, safe='')}/location"
                cache_key = "locations_" + hashlib.sha1(offering_id.encode()).hexdigest()[:16]
                try:
                    locations[offering_id], _ = client.get(cache_key, endpoint)
                except TimetableError as exc:
                    report["warnings"].append(
                        f"{offering_id}: location detail unavailable; using activity location ({exc})"
                    )
            unit_rows, warnings = clean_subjects(subjects, locations, code=code,
                                                  year=year, session=session,
                                                  snapshot_time=stamp)
            rows.extend(unit_rows)
            report["units"][code] = {"offerings": len(offerings),
                                     "meetings": len(unit_rows),
                                     "status": "ok" if unit_rows else "missing"}
            report["warnings"].extend(warnings)
        except TimetableError as exc:
            report["units"][code] = {"offerings": 0, "meetings": 0,
                                     "status": "error", "error": str(exc)}
    rows.sort(key=lambda row: (row["unit_code"], row["session_code"],
                               row["option_id"], row["date"], row["start_min"]))
    report["meeting_count"] = len(rows)
    report["complete"] = all(x["status"] == "ok" for x in report["units"].values())
    return rows, report


def write_outputs(rows: list[dict], report: dict, output: Path) -> tuple[Path, Path]:
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_tmp = output.with_suffix(output.suffix + ".tmp")
    with csv_tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    csv_tmp.replace(output)
    report_path = output.with_name(output.stem + "_report.json")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    return output, report_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("codes", nargs="+", help="Unit codes, e.g. ENGG2112 AMME1362")
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--session", required=True, help="Session code, e.g. S2C")
    parser.add_argument("--output", type=Path, help="Destination CSV path")
    parser.add_argument("--cache-dir", type=Path, default=Path("data/timetable_cache"))
    parser.add_argument("--offline", action="store_true", help="Use cached responses only")
    parser.add_argument("--refresh", action="store_true", help="Fetch a fresh snapshot")
    parser.add_argument("--allow-robots-disallowed", action="store_true",
                        help="Explicitly permit limited queries despite a robots.txt disallow")
    args = parser.parse_args(argv)
    try:
        codes = normalise_codes(args.codes)
        if args.offline and args.refresh:
            raise TimetableError("--offline and --refresh cannot be combined")
        session = args.session.upper().strip()
        if not SESSION_RE.fullmatch(session):
            raise TimetableError(f"Invalid session code: {args.session!r}")
        if not 2020 <= args.year <= 2100:
            raise TimetableError("Year must be between 2020 and 2100")
        unit_slug = "_".join(codes)
        output = args.output or Path(
            f"data/processed/timetable_meetings_{args.year}_{session}_{unit_slug}_"
            f"{datetime.now(SYDNEY):%Y%m%d}.csv"
        )
        robots_allowed = None if args.offline else robots_allows_requests()
        if robots_allowed is False and not args.allow_robots_disallowed:
            raise TimetableError(
                "The timetable site's robots.txt disallows automated requests. "
                "Use --offline with cached data, or explicitly pass "
                "--allow-robots-disallowed if you are permitted to make these limited queries."
            )
        if robots_allowed is False:
            print("Warning: robots.txt disallows automated requests; querying only the supplied codes.",
                  file=sys.stderr)
        rows, report = collect(codes, args.year, session, args.cache_dir,
                               offline=args.offline, refresh=args.refresh)
        report["robots_policy"] = ("offline" if args.offline else
                                   "allowed" if robots_allowed else "disallowed_override")
        csv_path, report_path = write_outputs(rows, report, output)
        print(f"Wrote {len(rows)} meetings to {csv_path}")
        print(f"Report: {report_path}")
        if not report["complete"]:
            print("Some units have no clean meetings; check the report.", file=sys.stderr)
            return 2
        return 0
    except TimetableError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
