"""Real candidate timetables for a persona, from the scheduler (training and evaluation only).

The persona's hard conditions and preferred hours go into the scheduler profile, so every
timetable here is valid for that student. ``candidate_set`` then picks the kind of list
rank() receives at run time: the non-dominated plans plus the next best by a few simple
orderings, 10-16 in all.
"""
from __future__ import annotations

import random
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llm.contracts import to_profile_fields  # noqa: E402
from uniplan.arrangement import AXIS_SETS, arrange_timetables, candidate_from_ids  # noqa: E402
from uniplan.catalog import SnapshotCatalog  # noqa: E402
from uniplan.profile import prepare_student_profile  # noqa: E402
from uniplan.ranking import dated_meetings, pareto_front, scaled_features, weekday_pattern  # noqa: E402
from uniplan.timetable_data import load_timetable_data  # noqa: E402

SET_SIZE = 16


@lru_cache(maxsize=1)
def catalog() -> SnapshotCatalog:
    return SnapshotCatalog(ROOT / "data/processed", ROOT / "data/requirements")


_CACHE: dict[str, tuple[list[dict], dict, dict]] = {}


def _search(persona: dict) -> tuple[list[dict], dict, dict]:
    """(pool, class options, scheduler profile) for one persona, computed once."""
    if persona["id"] not in _CACHE:
        raw = {"year": 2026, "session_code": "S2C", "unit_codes": list(persona["units"]),
               **to_profile_fields(persona["conditions"])}
        prepared = prepare_student_profile(raw, catalog())
        if prepared["profile"] is None:
            raise ValueError(f"{persona['id']}: {prepared['errors']}")
        profile = prepared["profile"]
        data = load_timetable_data(profile, prepared["snapshot_ref"], catalog())
        groups = {unit["unit_code"]: [group["group_id"] for group in unit["groups"] if group["default_selected"]]
                  for unit in data.summary["units"]}
        ranking = arrange_timetables(data.meetings, groups, profile)
        _CACHE[persona["id"]] = ranking["_pool"], ranking["_options"], profile
    return _CACHE[persona["id"]]


def persona_pool(persona: dict) -> list[dict]:
    """Every distinct valid timetable (one per G/D/O profile), meetings not yet attached."""
    return _search(persona)[0]


def materialize(persona: dict, entries: list[dict]) -> list[dict]:
    """Pool entries -> llm.contracts.Candidate dicts with dated meetings."""
    _, options, profile = _search(persona)
    result = []
    for entry in entries:
        timetable = candidate_from_ids(entry["candidate_id"], entry["option_ids"], options)
        result.append({"candidate_id": entry["candidate_id"], "option_ids": list(entry["option_ids"]),
                       "features": dict(entry["features"]), "pattern": weekday_pattern(timetable),
                       "meetings": dated_meetings(timetable, profile)})
    return result


def routine_key(meetings: list[dict]) -> frozenset:
    """The weekly routine (slots repeating in at least three weeks). Two timetables with the same
    routine look identical to a student and to the teacher, so a set keeps only one of them."""
    slots = Counter((m["weekday"], m["start_min"], m["end_min"], m["unit_code"], m["group_id"], m["is_online"])
                    for m in meetings)
    return frozenset(slot for slot, count in slots.items() if count >= 3)


def candidate_set(persona: dict, rng: random.Random, size: int = SET_SIZE) -> list[dict]:
    """What rank() would get: the non-dominated plans for every choice of cares, then the best by
    equal weights and by this persona's cares (alternating), then 3 random valid ones.
    Timetables with the same weekly routine appear once; at most ``size`` in all."""
    pool = persona_pool(persona)
    keys = ("campus_days", "gap", "outside_hours")
    cared = persona["conditions"]["cares"]

    def by(names):
        return sorted(pool, key=lambda e: (sum(v for k, v in scaled_features(e["features"]).items() if k in names),
                                           e["candidate_id"]))
    preferred = [entry for axes in AXIS_SETS for entry in pareto_front(pool, axes)]
    preferred += [entry for pair in zip(by(keys), by(cared)) for entry in pair]
    rest = list(pool)
    rng.shuffle(rest)
    chosen, ids, routines = [], set(), set()
    for limit, entries in ((size - 3, preferred), (size, rest)):
        for entry in entries:
            if len(chosen) >= limit:
                break
            if entry["candidate_id"] in ids:
                continue
            ids.add(entry["candidate_id"])
            candidate = materialize(persona, [entry])[0]
            routine = routine_key(candidate["meetings"])
            if routine not in routines:
                routines.add(routine)
                chosen.append(candidate)
    return chosen
