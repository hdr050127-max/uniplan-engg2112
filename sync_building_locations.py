"""Cache map points for buildings used by local timetable snapshots.

The University of Sydney campus map uses MazeMap's public search endpoint.
Only a unique building result with an exact code is accepted. Run this script
again after importing snapshots containing new building codes.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "data/locations/buildings.json"
MAP_HOME = "https://maps.sydney.edu.au/"
SEARCH_URL = "https://search.mazemap.com/search/equery/"
SEARCH_PARAMS = {
    "rows": "60", "start": "0", "withpois": "true", "withbuilding": "true",
    "withtype": "false", "withcampus": "false", "lng": "151.1863577738983",
    "lat": "-33.88801341641893", "boostbydistance": "true",
    "campuscollectiontag": "unisyd", "resultsFormat": "geojson",
}


def snapshot_codes(directory: Path) -> set[str]:
    codes: set[str] = set()
    for path in directory.glob("timetable_meetings_*.csv"):
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                code = (row.get("building_code") or "").strip().upper()
                if re.fullmatch(r"[A-Z][A-Z0-9]{1,9}", code):
                    codes.add(code)
    return codes


def fetch_building(code: str) -> dict[str, object]:
    url = SEARCH_URL + "?" + urlencode({"q": code, **SEARCH_PARAMS})
    request = Request(url, headers={
        "Origin": MAP_HOME.rstrip("/"), "Referer": MAP_HOME,
        "User-Agent": "UniPlan/0.1 (local campus building lookup)",
    })
    with urlopen(request, timeout=20) as response:
        results = json.load(response)["result"]
    exact = [item for item in results
             if str(item.get("solrId", "")).startswith("bld")
             and re.search(r"\(" + re.escape(code) + r"\)$", item.get("title", ""), re.I)]
    if len(exact) != 1:
        raise ValueError(f"{code}: expected one exact building, got {len(exact)}")
    item = exact[0]
    lon, lat = item["point"]["coordinates"]
    if not (-35 < lat < -33 and 150 < lon < 152):
        raise ValueError(f"{code}: map point outside Sydney area")
    building_id = int(item["id"])
    return {
        "name": re.sub(r"\s*\(" + re.escape(code) + r"\)$", "", item["title"], flags=re.I),
        "latitude": lat,
        "longitude": lon,
        "map_url": MAP_HOME + "?" + urlencode({"buildingId": building_id}),
        "map_building_id": building_id,
        "campus": item.get("campusName", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="refresh already cached codes")
    parser.add_argument("--code", action="append", help="additional building code to look up")
    args = parser.parse_args()
    codes = snapshot_codes(ROOT / "data/processed")
    for raw_code in args.code or []:
        code = raw_code.strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9]{1,9}", code):
            parser.error(f"invalid building code: {raw_code}")
        codes.add(code)
    if OUTPUT.exists():
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    else:
        payload = {"source": MAP_HOME, "position_kind": "building_map_point", "buildings": {}}
    buildings = payload["buildings"]
    failures: list[str] = []
    pending = sorted(code for code in codes if code and (args.refresh or code not in buildings))
    for index, code in enumerate(pending):
        if index:
            time.sleep(1)
        try:
            buildings[code] = fetch_building(code)
            print(f"{code}: {buildings[code]['name']}")
        except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
            failures.append(f"{code}: {error}")
    if pending and len(failures) < len(pending):
        payload["fetched_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload["buildings"] = dict(sorted(buildings.items()))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for failure in failures:
        print(f"FAILED {failure}")
    print(f"Stored {len(buildings)} buildings in {OUTPUT}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
