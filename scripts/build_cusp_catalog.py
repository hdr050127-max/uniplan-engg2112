"""Build a local code/title supplement from CUSP's public All Units table."""

from __future__ import annotations

import csv
import html
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo


BASE = "https://cusp.sydney.edu.au"
PAGE_URL = f"{BASE}/students/view-units-page/"
DATA_URL = f"{BASE}/students/view-units-page/did//get_table/1/?iDisplayStart=0&iDisplayLength=2000"
USER_AGENT = "UniPlan student project (local catalogue build)"
CODE_RE = re.compile(r"^[A-Z]{4}\d{4}$")
TAG_RE = re.compile(r"<[^>]+>")


def _plain(value: str) -> str:
    return " ".join(html.unescape(TAG_RE.sub("", value)).split())


def fetch_catalogue() -> dict[str, str]:
    robots_url = urljoin(BASE, "/robots.txt")
    with urlopen(Request(robots_url, headers={"User-Agent": USER_AGENT}), timeout=15) as response:
        robots = response.read().decode("utf-8", "replace")
    parser = RobotFileParser()
    parser.parse(robots.splitlines())
    if not parser.can_fetch(USER_AGENT, DATA_URL):
        raise RuntimeError("CUSP robots.txt does not permit this catalogue request")
    request = Request(DATA_URL, headers={
        "User-Agent": USER_AGENT, "X-Requested-With": "XMLHttpRequest",
    })
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)
    rows = payload.get("aaData")
    if not isinstance(rows, list) or len(rows) != int(payload.get("iTotalRecords", -1)):
        raise ValueError("CUSP table is incomplete or changed format")
    units: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            raise ValueError("Invalid CUSP row")
        code, name = _plain(row[0]), _plain(row[1])
        if not CODE_RE.fullmatch(code) or not name:
            raise ValueError(f"Invalid CUSP code or name: {code!r}")
        if code in units and units[code] != name:
            raise ValueError(f"Conflicting CUSP names for {code}")
        units[code] = name
    return units


def main() -> None:
    units = fetch_catalogue()
    out = Path("data/catalog")
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "units_2026_cusp.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("unit_code", "unit_name"))
        writer.writerows(sorted(units.items()))
    meta = {
        "catalog_year": 2026,
        "source_url": PAGE_URL,
        "data_url": DATA_URL,
        "source_scope": "CUSP All Units table; supplement to the 2026 CSP list, not proof of session availability",
        "retrieved_at": datetime.now(ZoneInfo("Australia/Sydney")).isoformat(timespec="seconds"),
        "unit_count": len(units),
    }
    (out / "units_2026_cusp_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"Wrote {len(units)} CUSP units to {csv_path}")


if __name__ == "__main__":
    main()
