"""Module three: assemble complete class choices and rank feasible timetables.

This entry point never guesses which activity groups a student must attend.
The caller supplies verified group IDs or an explicit student selection.
"""

from __future__ import annotations

from typing import Any

import time
from dataclasses import replace
from datetime import date

from .advisor import recommend
from .ranking import (AXIS_SETS, axes_name, common_teaching_weeks, dated_meetings,
                      extract_schedule_features, feature_key, pareto_front, pool_from_search,
                      rank_pool, scaled_features, weekday_pattern)
from .schedule import (WEEKDAY_NAMES, Candidate, ClassOption, FastSearch, ScheduleDataError,
                       SearchLimitError, SearchStats, extract_class_options, find_conflict_core,
                       linked_option_id, option_fits_with)


def validate_group_selection(
    meetings: list[dict[str, Any]], unit_codes: list[str], selection: Any,
) -> dict[str, list[str]]:
    """Accept only nonempty groups from the chosen units and snapshot."""
    if not isinstance(selection, dict) or set(selection) != set(unit_codes):
        raise ScheduleDataError("请为每门课程选择要纳入试算的活动组。")
    available: dict[str, set[str]] = {code: set() for code in unit_codes}
    for row in meetings:
        if row["unit_code"] in available:
            available[row["unit_code"]].add(row["group_id"])
    normalized: dict[str, list[str]] = {}
    for code in unit_codes:
        groups = selection[code]
        if (not isinstance(groups, list) or not 1 <= len(groups) <= len(available[code]) or
                any(not isinstance(group, str) or group not in available[code] for group in groups) or
                len(set(groups)) != len(groups)):
            raise ScheduleDataError(f"{code} 的活动组选择无效；请从当前课表中至少选择一组。")
        normalized[code] = sorted(groups)
    return normalized


MAX_BACKUPS = 4


def _seats(option: ClassOption) -> str:
    seats = {meeting.available_seats for meeting in option.meetings}
    return next(iter(seats)) if len(seats) == 1 else ""


def class_backups(
    item: dict[str, Any], eligible: dict[str, tuple[ClassOption, ...]],
    options: dict[str, ClassOption], profile: dict[str, Any], weeks: tuple[date, ...],
) -> dict[str, dict[str, Any]]:
    """For each chosen class: its seats and the best single-class replacements.

    A replacement keeps every other class, passes the same hard checks and is
    listed with its exact change in G, D and O (zero = an equal swap), best
    first. This is the plan B for enrolment day when a class fills up; any
    larger reshuffle still has to pass the full search.
    """
    chosen = [options[option_id] for option_id in item["option_ids"]]
    base = item["features"]
    result: dict[str, dict[str, Any]] = {}
    for index, option in enumerate(chosen):
        others = tuple(meeting for position, other in enumerate(chosen)
                       if position != index for meeting in other.meetings)
        backups = []
        for alternative in eligible.get(option.group_id, ()):
            if (alternative.option_id == option.option_id or
                    not option_fits_with(alternative, others, profile)):
                continue
            features = extract_schedule_features(Candidate("", (), others + alternative.meetings),
                                                 profile, weeks)
            delta = {key: features[key] - base[key] for key in features}
            backups.append({
                "code": alternative.option_id.rpartition("|")[2], "option_id": alternative.option_id,
                "delta": delta, "equal": feature_key(features) == feature_key(base),
                "seats": _seats(alternative),
                "_cost": sum(scaled_features({key: max(value, 0) for key, value in delta.items()}).values()),
            })
        # Equal swaps first, then cheapest; among equals, the roomiest class first.
        backups.sort(key=lambda entry: (not entry["equal"], round(entry["_cost"], 9),
                                        -(int(entry["seats"]) if entry["seats"].isdigit() else 0),
                                        entry["code"]))
        result[option.group_id] = {
            "code": option.option_id.rpartition("|")[2], "seats": _seats(option),
            "alternatives": len(backups),
            "equal_codes": [entry["code"] for entry in backups if entry["equal"]],
            "backups": [{key: value for key, value in entry.items() if key != "_cost"}
                        for entry in backups[:MAX_BACKUPS]],
        }
    return result


def _seat_count(option: ClassOption) -> int:
    seats = _seats(option)
    return int(seats) if seats.isdigit() else 0


def prefer_open_seats(option_ids: list[str], features: dict[str, float],
                      eligible: dict[str, tuple[ClassOption, ...]], options: dict[str, ClassOption],
                      profile: dict[str, Any], weeks: tuple[date, ...]) -> list[str]:
    """Among schedules identical in G, D, O and campus weekdays, prefer roomier classes.

    Swaps one class at a time; each swap must still fit the other classes, so
    the result stays feasible. Seats come from the snapshot and may be stale.
    """
    chosen = [options[option_id] for option_id in option_ids]
    key = feature_key(features)
    pattern = weekday_pattern(candidate_from_ids("", option_ids, options))
    for index, option in enumerate(list(chosen)):
        others = tuple(meeting for position, other in enumerate(chosen)
                       if position != index for meeting in other.meetings)
        best = option
        for alternative in eligible.get(option.group_id, ()):
            if (_seat_count(alternative) <= _seat_count(best) or
                    not option_fits_with(alternative, others, profile)):
                continue
            swapped = Candidate("", (), others + alternative.meetings)
            if (feature_key(extract_schedule_features(swapped, profile, weeks)) == key and
                    weekday_pattern(swapped) == pattern):
                best = alternative
        chosen[index] = best
    return sorted(option.option_id for option in chosen)


def attach_alternatives(item: dict[str, Any], eligible: dict[str, tuple[ClassOption, ...]],
                        options: dict[str, ClassOption], profile: dict[str, Any],
                        weeks: tuple[date, ...]) -> dict[str, Any]:
    """Pick the roomiest equal classes, then add plan-B classes and equal swaps.

    ``candidate_id`` keeps naming the feature profile it was ranked as; the
    class list may change to an equivalent one with more open seats.
    """
    roomier = prefer_open_seats(list(item["option_ids"]), item["features"], eligible, options,
                                profile, weeks)
    if roomier != sorted(item["option_ids"]):
        item["option_ids"] = roomier
        item["meetings"] = dated_meetings(candidate_from_ids(item["candidate_id"], roomier, options), profile)
    item["class_backups"] = class_backups(item, eligible, options, profile, weeks)
    item["equivalent_swaps"] = {group_id: info["equal_codes"]
                                for group_id, info in item["class_backups"].items() if info["equal_codes"]}
    return item


def equivalent_swaps(
    item: dict[str, Any], eligible: dict[str, tuple[ClassOption, ...]],
    options: dict[str, ClassOption], profile: dict[str, Any], weeks: tuple[date, ...],
) -> dict[str, list[str]]:
    """Single-class swaps that stay feasible and leave G, D and O unchanged."""
    return {group_id: info["equal_codes"]
            for group_id, info in class_backups(item, eligible, options, profile, weeks).items()
            if info["equal_codes"]}


MAX_VARIANTS = 6


def candidate_dict(entry: dict[str, Any], options: dict[str, ClassOption],
                   profile: dict[str, Any]) -> dict[str, Any]:
    """A pool profile in the llm.contracts.Candidate shape (no backups; cheap enough for 20)."""
    candidate = candidate_from_ids(entry["candidate_id"], entry["option_ids"], options)
    return {"candidate_id": entry["candidate_id"], "option_ids": list(entry["option_ids"]),
            "features": entry["features"], "pattern": weekday_pattern(candidate),
            "meetings": dated_meetings(candidate, profile)}


def candidate_from_ids(candidate_id: str, option_ids: tuple[str, ...] | list[str],
                       options: dict[str, ClassOption]) -> Candidate:
    """Rebuild a schedule from its class options (the pool keeps only ids)."""
    meetings = tuple(sorted(
        (meeting for option_id in option_ids for meeting in options[option_id].meetings),
        key=lambda item: (item.date, item.start_min, item.end_min),
    ))
    return Candidate(candidate_id, tuple(option_ids), meetings)


def _materialize(candidate_id: str, option_ids: tuple[str, ...], features: dict[str, float],
                 count: int, options: dict[str, ClassOption],
                 eligible: dict[str, tuple[ClassOption, ...]], profile: dict[str, Any],
                 weeks: tuple[date, ...]) -> dict[str, Any]:
    candidate = candidate_from_ids(candidate_id, option_ids, options)
    item = {"candidate_id": candidate_id, "option_ids": list(option_ids), "features": features,
            "equivalent_count": count, "pattern": weekday_pattern(candidate),
            "meetings": dated_meetings(candidate, profile)}
    return attach_alternatives(item, eligible, options, profile, weeks)


def add_item(items: dict[str, dict[str, Any]], entry: dict[str, Any], options: dict[str, ClassOption],
             eligible: dict[str, tuple[ClassOption, ...]], profile: dict[str, Any],
             weeks: tuple[date, ...]) -> dict[str, Any]:
    """Put one pool profile into ``items`` once, with a schedule per distinct set of weekdays."""
    if entry["candidate_id"] in items and "variants" in items[entry["candidate_id"]]:
        return items[entry["candidate_id"]]
    variants = sorted(entry["patterns"].items(),
                      key=lambda pair: (-pair[1]["count"], pair[0]))[:MAX_VARIANTS]
    item = items.get(entry["candidate_id"]) or _materialize(
        entry["candidate_id"], entry["option_ids"], entry["features"], entry["count"],
        options, eligible, profile, weeks)
    item["variants"] = [{"pattern": pattern, "count": variant["count"],
                         "candidate_id": variant["candidate_id"]}
                        for pattern, variant in variants]
    items[entry["candidate_id"]] = item
    for _, variant in variants:
        if variant["candidate_id"] not in items:
            items[variant["candidate_id"]] = _materialize(
                variant["candidate_id"], variant["option_ids"], entry["features"],
                variant["count"], options, eligible, profile, weeks)
    return item


def build_shortlist(pool: list[dict[str, Any]], options: dict[str, ClassOption],
                    eligible: dict[str, tuple[ClassOption, ...]], profile: dict[str, Any],
                    weeks: tuple[date, ...]) -> dict[str, Any]:
    """Non-dominated plans for every choice of features the student cares about.

    ``menus`` maps "gap,campus_days,outside_hours" (and each smaller subset) to
    the candidate ids on that Pareto front; ``items`` holds each plan once,
    including one schedule per distinct set of campus weekdays.
    """
    items: dict[str, dict[str, Any]] = {}
    menus: dict[str, list[str]] = {}
    for axes in AXIS_SETS:
        front = pareto_front(pool, axes)
        menus[axes_name(axes)] = [entry["candidate_id"] for entry in front]
        for entry in front:
            add_item(items, entry, options, eligible, profile, weeks)
    full = menus[axes_name(AXIS_SETS[0])]
    return {"menus": menus, "items": items, "default_axes": axes_name(AXIS_SETS[0]),
            "dominated_profiles": len(pool) - len(full),
            "dominated_examples": dominated_examples(pool, [items[cid] for cid in full])}


def dominated_examples(pool: list[dict[str, Any]], front: list[dict[str, Any]],
                       limit: int = 3) -> list[dict[str, Any]]:
    """The closest excluded profiles (by equal weights) and a plan that beats each.

    Shows students concretely why everything else was left out.
    """
    keys = ("gap_min", "campus_days", "outside_min")
    front_ids = {item["candidate_id"] for item in front}

    def beats(a: dict[str, float], b: dict[str, float]) -> bool:
        return (all(a[key] <= b[key] + 1e-9 for key in keys) and
                any(a[key] < b[key] - 1e-9 for key in keys))

    excluded = sorted((entry for entry in pool if entry["candidate_id"] not in front_ids),
                      key=lambda entry: (sum(scaled_features(entry["features"]).values()),
                                         entry["candidate_id"]))
    examples = []
    for entry in excluded:
        winner = next((item for item in front if beats(item["features"], entry["features"])), None)
        if winner is not None:
            examples.append({"features": entry["features"], "count": entry["count"],
                             "beaten_by": winner["candidate_id"]})
        if len(examples) == limit:
            break
    return examples


RELAX_NODES = 2_000_000
RELAX_SECONDS = 6.0


def describe_window(window: dict[str, int]) -> str:
    def clock(value: int) -> str:
        return f"{value // 60:02d}:{value % 60:02d}"
    return f"{WEEKDAY_NAMES[window['weekday'] - 1]} {clock(window['start_min'])}–{clock(window['end_min'])}"


def _explore(groups: list[tuple[str, tuple[ClassOption, ...]]], profile: dict[str, Any],
             weeks: tuple[date, ...]) -> dict[str, Any] | None:
    """Feasible count and best achievable G, D, O; None if the search is too large."""
    search = FastSearch(groups, profile, len(weeks))
    best: dict[str, float] = {}

    def sink(chosen: list[int], copies: int, span: int, duration: int, outside: int, attend: int) -> None:
        for key, value in search.features_of(span, duration, outside, attend).items():
            best[key] = min(best.get(key, value), value)

    try:
        search.run(sink, RELAX_NODES)
    except SearchLimitError:
        return None
    return {"count": search.stats.feasible_count, "best": best or None}


def relaxations(groups: list[tuple[str, tuple[ClassOption, ...]]], profile: dict[str, Any],
                weeks: tuple[date, ...], *, drop_groups: tuple[str, ...] = (),
                unpin: dict[str, tuple[ClassOption, ...]] | None = None) -> dict[str, Any]:
    """What each hard constraint costs: re-search with exactly one of them lifted.

    Nothing here changes the student's result; it only shows the trade-off so
    they can decide whether a constraint is worth keeping. Each check has a
    node budget and the whole set a time budget.
    """
    trials: list[tuple[dict[str, Any], list, dict[str, Any]]] = []
    for index, window in enumerate(profile["unavailable_windows"]):
        trials.append(({"kind": "window", "window": window, "label": f"不再避开{describe_window(window)}"},
                       groups, {**profile, "unavailable_windows": [
                           other for position, other in enumerate(profile["unavailable_windows"])
                           if position != index]}))
    if profile.get("transition_min"):
        trials.append(({"kind": "buffer", "label": f"换楼缓冲从 {profile['transition_min']} 分钟改为 0"},
                       groups, {**profile, "transition_min": 0}))
    for group_id in drop_groups:
        trials.append(({"kind": "group", "group_id": group_id,
                        "label": f"不参加 {group_label(group_id)}（例如看录播，或与学校确认可免）"},
                       [group for group in groups if group[0] != group_id], profile))
    lifted = {"max_days_per_week": (None, "不限每周到校天数"), "max_daily_minutes": (None, "不限每天上课时长"),
              "max_daily_span": (None, "不限每天在校时长"), "lunch": (None, "不留午饭时间"),
              "in_person_only": (False, "线上课也可以"), "min_seats": (0, "余位少的班也可以"),
              "walk_speed": (None, "换楼不按距离估算")}
    for key, (off, label) in lifted.items():
        if profile.get(key):
            trials.append(({"kind": key, "label": label}, groups, {**profile, key: off}))
    for group_id, all_options in (unpin or {}).items():
        trials.append(({"kind": "pin", "group_id": group_id,
                        "label": f"不再固定 {group_label(group_id)} 的班级"},
                       [(gid, all_options if gid == group_id else options) for gid, options in groups],
                       profile))
    started = time.monotonic()
    results, skipped = [], 0
    for change, trial_groups, trial_profile in trials:
        if not trial_groups or time.monotonic() - started > RELAX_SECONDS:
            skipped += 1
            continue
        explored = _explore(trial_groups, trial_profile, weeks)
        if explored is None:
            skipped += 1
            continue
        results.append({**change, **explored})
    # A smaller step than dropping a limit: the first looser setting the page offers that works.
    for key, values in _limit_steps(profile):
        for value in values:
            if time.monotonic() - started > RELAX_SECONDS:
                skipped += 1
                break
            explored = _explore(groups, {**profile, key: value}, weeks)
            if explored is None:
                skipped += 1
                break
            if explored["count"]:
                results.append({"kind": key, "value": value, "label": LIMIT_STEPS[key][1](value), **explored})
                break
    return {"changes": results, "skipped": skipped}


LIMIT_STEPS = {
    "max_days_per_week": ((2, 3, 4), lambda value: f"每周最多到校改为 {value} 天"),
    "max_daily_minutes": ((240, 360, 480), lambda value: f"每天最多上课改为 {value // 60} 小时"),
    "max_daily_span": ((420, 540), lambda value: f"每天最长在校改为 {value // 60} 小时"),
}


def _limit_steps(profile: dict[str, Any]) -> list[tuple[str, list[int]]]:
    steps = []
    for key, (values, _label) in LIMIT_STEPS.items():
        current = profile.get(key)
        following = [value for value in values if current and value > current]
        if following:
            steps.append((key, following))
    return steps


def group_label(group_id: str) -> str:
    """'AMME2301-S2C-ND-CC|Tutorial' -> 'AMME2301 Tutorial'."""
    if "|" not in group_id:
        return group_id
    offering, _, name = group_id.rpartition("|")
    return f"{offering.split('-')[0]} {name}"


def _conflict_message(core: dict[str, Any]) -> str:
    parts = [f"{group_label(group_id)}（{'、'.join(core['slots'][group_id])}）"
             for group_id in core["group_ids"]]
    reason = {"time_overlap": "这些活动组的可选班级在实际上课日期时间重叠",
              "limits": "在你设的每天或每周限制下无法同时安排",
              "filters": "按你的选班条件（只要现场课、余位）找不到能同时安排的班",
              }.get(core["reason"], "这些活动组的班级不重叠，但换楼时间不够")
    return f"无法同时安排：{' 与 '.join(parts)}。{reason}；系统不会自动放宽条件。可取消其中非必需的活动组，或调整课程与限制后重试。"


def validate_pins(meetings: list[dict[str, Any]], required: dict[str, list[str]],
                  pins: Any) -> dict[str, list[str]]:
    """Classes the student fixes in advance (already enrolled, a friend's tutorial...).

    ``pins`` maps a selected group id to one or more of its class ids.
    """
    if pins in (None, {}):
        return {}
    selected = {group for groups in required.values() for group in groups}
    by_group: dict[str, set[str]] = {}
    for row in meetings:
        by_group.setdefault(row["group_id"], set()).add(linked_option_id(row))
    if not isinstance(pins, dict) or len(pins) > len(selected):
        raise ScheduleDataError("固定班级的格式无效。")
    normalized = {}
    for group_id, option_ids in pins.items():
        if (group_id not in selected or not isinstance(option_ids, list) or not option_ids or
                any(not isinstance(option_id, str) or option_id not in by_group.get(group_id, set())
                    for option_id in option_ids)):
            raise ScheduleDataError("固定的班级不属于所选活动组；请重新选择。")
        normalized[group_id] = sorted(set(option_ids))
    return normalized


def validate_excluded(meetings: list[dict[str, Any]], required: dict[str, list[str]],
                      excluded: Any) -> list[str]:
    """Classes the student found full while enrolling; they are left out of the re-plan."""
    if excluded in (None, []):
        return []
    selected = {group for groups in required.values() for group in groups}
    known = {linked_option_id(row) for row in meetings if row["group_id"] in selected}
    if (not isinstance(excluded, list) or len(excluded) > 200 or
            any(not isinstance(option_id, str) or option_id not in known for option_id in excluded)):
        raise ScheduleDataError("标记为已满的班级无效；请刷新后重试。")
    return sorted(set(excluded))


def _apply_pins(groups: list[tuple[str, tuple[ClassOption, ...]]],
                pins: dict[str, list[str]],
                excluded: list[str] | tuple[str, ...] = ()) -> list[tuple[str, tuple[ClassOption, ...]]]:
    """Keep only pinned classes and drop excluded ones.

    A pinned class counts as open (you may already hold a seat) and skips the
    seat and online filters.
    """
    gone = set(excluded)
    return [(group_id, tuple(replace(option, is_full=False, pinned=True) for option in options
                             if option.option_id in pins[group_id]) if group_id in pins
             else tuple(option for option in options if option.option_id not in gone))
            for group_id, options in groups]


def arrange_timetables(
    meetings: list[dict[str, Any]], required_groups: dict[str, list[str]],
    profile: dict[str, Any], *, max_nodes: int = 5_000_000,
    pins: dict[str, list[str]] | None = None, excluded: list[str] | None = None,
    student_text: str | None = None,
) -> dict[str, Any]:
    """Choose one whole class per required group, then rank every valid choice.

    Time conflicts, full classes and building transfer constraints are checked
    on each actual teaching date. Avoidance windows apply to ordinary classes;
    assessment/test/quiz dates are retained and reported as exceptions. Search either
    completes or raises; callers must never show a partial ranking as final.

    Private keys ``_pool`` and ``_options`` carry the distinct feature profiles
    and class options to the preference study; callers pop them before output.

    With ``student_text`` (may be empty) the result also holds ``recommendation``:
    10–20 candidates, the top 3 by ``llm.rank`` and a template reason for each.
    """
    all_groups = extract_class_options(meetings, required_groups)
    pins = pins or {}
    groups = _apply_pins(all_groups, pins, excluded or ())
    stats = SearchStats()
    weeks = common_teaching_weeks(meetings)
    search = FastSearch(groups, profile, len(weeks), stats)
    pool, truncated = pool_from_search(search, max_nodes=max_nodes)
    options = {option.option_id: option for _, group in all_groups for option in group}
    options.update({option.option_id: option for _, group in groups for option in group})
    ranking = rank_pool(pool, stats.feasible_count, profile, weeks, truncated=truncated,
                        meetings_for=lambda entry: dated_meetings(
                            candidate_from_ids(entry["candidate_id"], entry["option_ids"], options), profile))
    ranking["search"] = stats.as_dict()
    ranking["required_groups"] = [
        {"group_id": group_id, "option_count": len(options)}
        for group_id, options in groups
    ]
    eligible = dict(search.eligible)
    for top in (ranking["top"], ranking["equal_weight_top"]):
        for item in top:
            attach_alternatives(item, eligible, options, profile, weeks)
    ranking["_options"] = options
    if ranking["feasible_count"]:
        ranking["shortlist"] = build_shortlist(ranking["_pool"], options, eligible, profile, weeks)
        if student_text is not None:
            items = ranking["shortlist"]["items"]
            ranking["recommendation"] = recommend(
                ranking["_pool"], profile, student_text,
                candidate=lambda entry: candidate_dict(entry, options, profile),
                item=lambda entry: add_item(items, entry, options, eligible, profile, weeks))
        if any(profile.get(key) for key in (
                "unavailable_windows", "transition_min", "max_days_per_week", "max_daily_minutes",
                "max_daily_span", "lunch", "in_person_only", "min_seats", "walk_speed")):
            costs = relaxations(groups, profile, weeks)
            current = {key: min(entry["features"][key] for entry in ranking["_pool"])
                       for key in ("gap_min", "campus_days", "outside_min")}
            for change in costs["changes"]:
                change["gain"] = {key: current[key] - change["best"][key] for key in current}
            costs["current_best"] = current
            ranking["constraint_costs"] = costs
    if ranking["feasible_count"] == 0:
        core = None if stats.groups_without_options else find_conflict_core(groups, profile)
        ranking["conflict_core"] = core
        stuck = tuple(core["group_ids"]) if core else stats.groups_without_options
        fixes = relaxations(groups, profile, weeks, drop_groups=stuck,
                            unpin={group_id: dict(all_groups)[group_id] for group_id in pins})
        fixes["changes"] = [change for change in fixes["changes"] if change["count"]]
        ranking["what_if"] = fixes
        ranking["no_feasible_reason"] = (
            "以下必修活动组没有可用班级选项（可能已满、与你的不可上课时段冲突，或班级自身时间冲突）：" +
            "、".join(stats.groups_without_options)
            if stats.groups_without_options else
            _conflict_message(core) if core else
            "班级各自可选，但组合后与时间重叠或换楼缓冲条件冲突。"
        )
    return ranking
