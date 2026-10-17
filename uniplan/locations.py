"""Read the local, source-checked campus building map cache."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode


LOCATION_FILE = Path(__file__).resolve().parent.parent / "data/locations/buildings.json"
MAP_HOME = "https://maps.sydney.edu.au/"


@lru_cache(maxsize=1)
def _buildings() -> dict[str, dict]:
    if not LOCATION_FILE.exists():
        return {}
    return json.loads(LOCATION_FILE.read_text(encoding="utf-8"))["buildings"]


def building_location(code: str) -> dict | None:
    """Return a building point; unknown codes get only an official map search link."""
    code = code.strip().upper()
    if not code:
        return None
    cached = _buildings().get(code)
    if cached:
        return {
            "name": cached["name"],
            "latitude": cached["latitude"],
            "longitude": cached["longitude"],
            "map_url": cached["map_url"],
            "precision": "building",
        }
    return {"name": None, "latitude": None, "longitude": None,
            "map_url": MAP_HOME + "?" + urlencode({"building": code}),
            "precision": "unverified"}
