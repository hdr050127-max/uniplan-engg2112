import tempfile
import unittest
from pathlib import Path

from uniplan.arrangement import arrange_timetables, validate_pins
from uniplan.schedule import ScheduleDataError
from uniplan.catalog import SnapshotCatalog
import random
from collections import Counter
from datetime import date

from uniplan.ranking import extract_schedule_features, feature_key, weekday_pattern
from uniplan.schedule import (FastSearch, SearchLimitError, SearchStats, extract_class_options,
                              generate_feasible_schedules)
from uniplan.store import ProfileStore
from uniplan.timetable_data import load_timetable_data


def meeting(meeting_id, group, option, day, start, end, building="J01", seats="10", status="available"):
    return {"meeting_id": meeting_id, "unit_code": "TEST1234", "group_id": group, "option_id": option,
            "date": day, "start_min": str(start), "end_min": str(end), "building_code": building,
            "status": status, "activity_type": "Tutorial", "location_raw": building,
            "available_seats": seats, "year": "2026", "session_code": "S2C"}


def profile(**overrides):
    data = {"unavailable_windows": [], "transition_min": 0,
            "preferred_hours": {"start_min": 540, "end_min": 1080},
            "weights": {"gap": 1 / 3, "campus_days": 1 / 3, "outside_hours": 1 / 3}}
    data.update(overrides)
    return data


class SearchCollapseTests(unittest.TestCase):
    rows = [
        meeting("a", "G1", "A", "2026-08-03", 540, 600),
        # B and C differ only in building; D is at another time.
        meeting("b", "G2", "B", "2026-08-03", 600, 660, "J02", seats="1"),
        meeting("c", "G2", "C", "2026-08-03", 600, 660, "J03", seats="25"),
        meeting("d", "G2", "D", "2026-08-04", 600, 660, "J02"),
    ]

    def test_identical_options_are_searched_once_but_counted_exactly(self):
        groups = extract_class_options(self.rows, {"TEST1234": ["G1", "G2"]})
        stats = SearchStats()
        candidates = list(generate_feasible_schedules(groups, profile(), stats=stats))
        self.assertEqual(len(candidates), 2)
        self.assertEqual(stats.feasible_count, 3)
        self.assertEqual(sorted(candidate.multiplicity for candidate in candidates), [1, 2])

    def test_buildings_matter_again_once_a_transfer_buffer_is_set(self):
        groups = extract_class_options(self.rows, {"TEST1234": ["G1", "G2"]})
        stats = SearchStats()
        # A ends at 10:00 in J01; B and C start at 10:00 elsewhere, so a buffer rejects both.
        candidates = list(generate_feasible_schedules(groups, profile(transition_min=10), stats=stats))
        self.assertEqual([candidate.option_ids for candidate in candidates], [("A", "D")])
        self.assertEqual(stats.feasible_count, 1)

    def test_shortlist_prefers_the_roomier_identical_class_and_lists_backups(self):
        ranking = arrange_timetables(self.rows, {"TEST1234": ["G1", "G2"]}, profile())
        self.assertEqual(ranking["feasible_count"], 3)
        best = ranking["top"][0]
        self.assertIn("C", best["option_ids"])  # 25 seats beats the identical B with 1 seat
        backups = best["class_backups"]["G2"]
        self.assertEqual(backups["code"], "C")
        self.assertEqual(backups["equal_codes"], ["B"])
        self.assertEqual([entry["code"] for entry in backups["backups"]], ["B", "D"])
        self.assertTrue(backups["backups"][0]["equal"])
        self.assertAlmostEqual(backups["backups"][1]["delta"]["campus_days"], 1.0)
        self.assertEqual(best["equivalent_swaps"], {"G2": ["B"]})

    def test_roomier_swaps_and_backups_keep_the_daily_limits(self):
        # The roomier in-person tutorial ties on every feature but keeps the student on campus 9-16.
        weeks = ("2026-08-03", "2026-08-10", "2026-08-17")
        rows = [meeting(f"a{w}", "G1", "A", day, 540, 600) for w, day in enumerate(weeks)]
        rows += [meeting(f"x{w}", "G2", "X", day, 900, 960, building="Online", seats="5") for w, day in enumerate(weeks)]
        rows += [meeting(f"y{w}", "G2", "Y", day, 900, 960, seats="50") for w, day in enumerate(weeks)]
        ranking = arrange_timetables(rows, {"TEST1234": ["G1", "G2"]}, profile(max_daily_span=300))
        self.assertEqual(ranking["feasible_count"], 1)
        best = ranking["top"][0]
        self.assertIn("X", best["option_ids"])
        self.assertEqual(best["class_backups"]["G2"]["backups"], [])
        for item in ranking["shortlist"]["items"].values():
            self.assertIn("X", item["option_ids"])

    def test_search_limit_names_the_busiest_group(self):
        groups = extract_class_options(self.rows, {"TEST1234": ["G1", "G2"]})
        with self.assertRaises(SearchLimitError) as caught:
            list(generate_feasible_schedules(groups, profile(), max_nodes=1))
        self.assertIn("G2", str(caught.exception))


class FastSearchEquivalenceTests(unittest.TestCase):
    def test_fast_search_matches_the_reference_search_on_random_timetables(self):
        self._compare(random.Random(7), trials=25, limits=False)

    def test_fast_search_matches_reference_with_lifestyle_limits(self):
        self._compare(random.Random(11), trials=40, limits=True)

    def _compare(self, rng, trials, limits):
        for trial in range(trials):
            rows, serial = [], 0
            for group in range(rng.randint(2, 4)):
                for option in range(rng.randint(1, 4)):
                    start = rng.choice((540, 600, 660, 720, 840))
                    weekday = rng.randint(0, 4)
                    online = rng.random() < 0.2
                    for week in range(rng.choice((1, 3, 4))):
                        serial += 1
                        row = meeting(f"m{serial}", f"G{group}", f"G{group}|{option}",
                                      date.fromordinal(date(2026, 8, 3).toordinal() + 7 * week + weekday).isoformat(),
                                      start, start + rng.choice((60, 120)), rng.choice(("J07", "A08", "F11", "")),
                                      seats=str(rng.choice((0, 2, 9, 30))))
                        if online:
                            row["location_raw"] = "Online"
                        rows.append(row)
            required = {"TEST1234": sorted({row["group_id"] for row in rows})}
            groups = extract_class_options(rows, required)
            prof = profile(transition_min=rng.choice((0, 10)),
                           unavailable_windows=[{"weekday": rng.randint(1, 5), "start_min": 600, "end_min": 720}]
                           if rng.random() < 0.5 else [])
            if limits:
                prof.update(
                    max_days_per_week=rng.choice((None, 1, 2, 3)),
                    max_daily_minutes=rng.choice((None, 120, 180)),
                    max_daily_span=rng.choice((None, 180, 300)),
                    lunch=rng.choice((None, {"start_min": 690, "end_min": 840, "minutes": 30})),
                    walk_speed=rng.choice((None, 30, 80)),
                    in_person_only=rng.random() < 0.3,
                    min_seats=rng.choice((0, 0, 3)),
                )
            weeks = 4
            reference, patterns = Counter(), Counter()
            for candidate in generate_feasible_schedules(groups, prof):
                key = feature_key(extract_schedule_features(candidate, prof, tuple(range(weeks))))
                reference[key] += candidate.multiplicity
                patterns[(key, weekday_pattern(candidate))] += candidate.multiplicity
            fast, fast_patterns = Counter(), Counter()
            search = FastSearch(groups, prof, weeks)

            def sink(chosen, copies, span, duration, outside, attend):
                key = feature_key(search.features_of(span, duration, outside, attend))
                fast[key] += copies
                fast_patterns[(key, search.pattern_of(attend))] += copies

            search.run(sink)
            self.assertEqual(fast, reference, trial)
            self.assertEqual(fast_patterns, patterns, trial)


class RelaxationTests(unittest.TestCase):
    def test_no_feasible_lists_single_changes_that_would_work(self):
        rows = [meeting("a", "G1", "A", "2026-08-03", 540, 600),
                meeting("b", "G2", "B", "2026-08-03", 570, 630),
                meeting("c", "G3", "C", "2026-08-05", 540, 600)]
        avoid_wednesday = profile(unavailable_windows=[{"weekday": 3, "start_min": 0, "end_min": 1440}])
        ranking = arrange_timetables(rows, {"TEST1234": ["G1", "G2", "G3"]}, avoid_wednesday)
        self.assertEqual(ranking["feasible_count"], 0)
        labels = [change["label"] for change in ranking["what_if"]["changes"]]
        # Wednesday blocks G3's only class; dropping it alone is not enough, nor is any single group.
        self.assertEqual(labels, [])
        ranking = arrange_timetables(rows[:2], {"TEST1234": ["G1", "G2"]}, profile())
        kinds = sorted(change["kind"] for change in ranking["what_if"]["changes"])
        self.assertEqual(kinds, ["group", "group"])
        self.assertTrue(all(change["count"] == 1 for change in ranking["what_if"]["changes"]))

    def test_constraint_costs_show_what_a_window_gives_up(self):
        rows = [meeting("a", "G1", "A", "2026-08-03", 540, 600),
                meeting("b", "G2", "B", "2026-08-03", 600, 660),
                meeting("c", "G2", "C", "2026-08-04", 600, 660)]
        no_monday_late = profile(unavailable_windows=[{"weekday": 1, "start_min": 600, "end_min": 720}])
        ranking = arrange_timetables(rows, {"TEST1234": ["G1", "G2"]}, no_monday_late)
        self.assertEqual(ranking["feasible_count"], 1)
        change = ranking["constraint_costs"]["changes"][0]
        self.assertEqual(change["kind"], "window")
        self.assertEqual(change["count"], 2)
        self.assertAlmostEqual(change["gain"]["campus_days"], 1.0)  # two days -> one day


class SnapshotAndStoreTests(unittest.TestCase):
    def test_courses_from_different_snapshots_are_combined_with_a_warning(self):
        with tempfile.TemporaryDirectory() as temp:
            processed = Path(temp)
            for name, unit, stamp in (("one", "AAAA1111", "2026-09-20T10:00:00+10:00"),
                                      ("two", "BBBB2222", "2026-09-24T10:00:00+10:00")):
                row = meeting(f"m-{unit}", f"{unit}|Tutorial", f"{unit}|Tutorial|01", "2026-08-03", 540, 600)
                row.update(unit_code=unit, snapshot_time=stamp, source_url="test", meeting_id=f"m-{unit}")
                header = ",".join(row)
                (processed / f"{name}.csv").write_text(header + "\n" + ",".join(row.values()) + "\n")
                (processed / f"{name}_report.json").write_text(
                    '{"year": 2026, "session_code": "S2C", "units": {"%s": {"status": "ok"}}}' % unit)
            catalog = SnapshotCatalog(processed, processed / "requirements")
            ref, blockers, warnings = catalog.assess(
                {"year": 2026, "session_code": "S2C", "unit_codes": ["AAAA1111", "BBBB2222"]})
            self.assertTrue(ref["snapshot_id"].startswith("combined:"))
            self.assertEqual(ref["snapshot_time"], "2026-09-20T10:00:00+10:00")  # oldest part
            self.assertEqual(warnings[0]["code"], "mixed_snapshots")
            data = load_timetable_data({"year": 2026, "session_code": "S2C",
                                        "unit_codes": ["AAAA1111", "BBBB2222"]}, ref, catalog)
            self.assertEqual(data.summary["meeting_count"], 2)

    def test_scenarios_share_one_participant_code_that_withdraws_everything(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProfileStore(Path(temp) / "private/db.sqlite3")
            first, second, stranger = "a" * 32, "b" * 32, "c" * 32
            code = store.save({"profile_id": first}, None)
            self.assertEqual(code, first)
            self.assertEqual(store.save({"profile_id": second}, None, participant=code), first)
            self.assertEqual(store.save({"profile_id": stranger}, None, participant="d" * 32), stranger)
            store.record_outcome(second, "accepted", {"method": "shortlist"}, 10)
            self.assertEqual(store.load_outcomes()[0]["participant_id"], first)
            self.assertTrue(store.withdraw(first))
            self.assertEqual(store.load_outcomes(), [])
            self.assertFalse(store.has_profile(second))
            self.assertTrue(store.has_profile(stranger))


class PinTests(unittest.TestCase):
    rows = [meeting("a", "G1", "A", "2026-08-03", 540, 600),
            meeting("b", "G2", "B", "2026-08-03", 600, 660),
            meeting("c", "G2", "C", "2026-08-04", 600, 660, status="full"),
            meeting("d", "G2", "D", "2026-08-03", 570, 630)]
    required = {"TEST1234": ["G1", "G2"]}

    def test_pinned_class_is_used_even_if_listed_full(self):
        pins = validate_pins(self.rows, self.required, {"G2": ["C"]})
        ranking = arrange_timetables(self.rows, self.required, profile(), pins=pins)
        self.assertEqual(ranking["feasible_count"], 1)
        self.assertEqual(ranking["top"][0]["option_ids"], ["A", "C"])
        self.assertEqual(ranking["top"][0]["class_backups"]["G2"]["alternatives"], 0)

    def test_invalid_pins_are_rejected(self):
        for pins in ({"G9": ["A"]}, {"G2": ["A"]}, {"G2": []}, ["G2"]):
            with self.assertRaises(ScheduleDataError):
                validate_pins(self.rows, self.required, pins)
        self.assertEqual(validate_pins(self.rows, self.required, None), {})

    def test_a_clashing_pin_is_offered_as_the_thing_to_unpin(self):
        pins = validate_pins(self.rows, self.required, {"G2": ["D"]})
        ranking = arrange_timetables(self.rows, self.required, profile(), pins=pins)
        self.assertEqual(ranking["feasible_count"], 0)
        kinds = {change["kind"]: change["count"] for change in ranking["what_if"]["changes"]}
        self.assertEqual(kinds.get("pin"), 1)


class ExclusionExampleTests(unittest.TestCase):
    def test_excluded_examples_name_a_plan_that_beats_them(self):
        rows = [meeting("a", "G1", "A", "2026-08-03", 540, 600),
                meeting("b", "G2", "B", "2026-08-03", 600, 660),
                meeting("c", "G2", "C", "2026-08-03", 720, 780),
                meeting("d", "G2", "D", "2026-08-04", 600, 660)]
        shortlist = arrange_timetables(rows, {"TEST1234": ["G1", "G2"]}, profile())["shortlist"]
        front = shortlist["menus"][shortlist["default_axes"]]
        self.assertEqual(len(front), 1)  # B: same day, no gap
        examples = shortlist["dominated_examples"]
        self.assertEqual(len(examples), 2)
        self.assertTrue(all(example["beaten_by"] == front[0] for example in examples))


if __name__ == "__main__":
    unittest.main()


class LifestyleSettingTests(unittest.TestCase):
    def test_profile_accepts_and_rejects_new_settings(self):
        from uniplan.profile import normalize_student_input
        base = {"year": 2026, "session_code": "S2C", "unit_codes": ["ENGG2112"], "unavailable_windows": []}
        good, errors = normalize_student_input({**base, "max_days_per_week": 3, "max_daily_minutes": 300,
                                                "max_daily_span": 480, "walk_speed": 60, "min_seats": 2,
                                                "in_person_only": True,
                                                "lunch": {"start_min": 690, "end_min": 840, "minutes": 30}})
        self.assertEqual(errors, [])
        self.assertEqual((good["max_days_per_week"], good["min_seats"], good["in_person_only"]), (3, 2, True))
        defaults, _ = normalize_student_input(base)
        self.assertEqual((defaults["max_days_per_week"], defaults["lunch"], defaults["min_seats"]), (None, None, 0))
        for bad in ({"max_days_per_week": 0}, {"walk_speed": 500}, {"min_seats": -1}, {"in_person_only": "yes"},
                    {"lunch": {"start_min": 700, "end_min": 720, "minutes": 30}}):
            _, errors = normalize_student_input({**base, **bad})
            self.assertTrue(errors, bad)

    def test_walking_time_uses_real_building_distance(self):
        rows = [meeting("a", "G1", "A", "2026-08-03", 540, 600, "J07"),
                meeting("b", "G2", "B", "2026-08-03", 602, 660, "A08"),  # J07 -> A08 is a long walk
                meeting("c", "G2", "C", "2026-08-03", 602, 660, "J07")]
        required = {"TEST1234": ["G1", "G2"]}
        self.assertEqual(arrange_timetables(rows, required, profile())["feasible_count"], 2)
        slow = arrange_timetables(rows, required, profile(walk_speed=40))
        self.assertEqual(slow["feasible_count"], 1)
        self.assertEqual(slow["top"][0]["option_ids"], ["A", "C"])
        lifted = {change["kind"]: change["count"] for change in slow["constraint_costs"]["changes"]}
        self.assertEqual(lifted["walk_speed"], 2)

    def test_in_person_only_and_min_seats_filter_but_pins_win(self):
        online = meeting("o", "G1", "ON", "2026-08-03", 540, 600, "")
        online["location_raw"] = "Online"
        rows = [online, meeting("p", "G1", "IN", "2026-08-04", 540, 600, "J07", seats="1"),
                meeting("q", "G1", "IN2", "2026-08-05", 540, 600, "J07", seats="20")]
        required = {"TEST1234": ["G1"]}
        ranking = arrange_timetables(rows, required, profile(in_person_only=True, min_seats=3))
        self.assertEqual(ranking["feasible_count"], 1)
        self.assertEqual(ranking["top"][0]["option_ids"], ["IN2"])
        pinned = arrange_timetables(rows, required, profile(min_seats=3), pins={"G1": ["IN"]})
        self.assertEqual(pinned["top"][0]["option_ids"], ["IN"])

    def test_lifestyle_limits_prune_and_are_offered_as_relaxations(self):
        rows = [meeting("a", "G1", "A", "2026-08-03", 540, 660),
                meeting("b", "G2", "B", "2026-08-03", 660, 780),  # same day: 4 h of class
                meeting("c", "G2", "C", "2026-08-04", 660, 780)]
        required = {"TEST1234": ["G1", "G2"]}
        ranking = arrange_timetables(rows, required, profile(max_daily_minutes=180))
        self.assertEqual([item["option_ids"] for item in ranking["top"]], [["A", "C"]])
        lunch = arrange_timetables(rows, required, profile(lunch={"start_min": 630, "end_min": 690, "minutes": 30}))
        self.assertEqual(lunch["feasible_count"], 1)
        one_day = arrange_timetables(rows, required, profile(max_days_per_week=1))
        self.assertEqual(one_day["top"][0]["option_ids"], ["A", "B"])
        kinds = {change["kind"] for change in one_day["constraint_costs"]["changes"]}
        self.assertIn("max_days_per_week", kinds)

    def test_classes_marked_full_are_left_out_of_the_replan(self):
        from uniplan.arrangement import validate_excluded
        rows = [meeting("a", "G1", "A", "2026-08-03", 540, 600),
                meeting("b", "G2", "B", "2026-08-03", 600, 660),
                meeting("c", "G2", "C", "2026-08-04", 600, 660)]
        required = {"TEST1234": ["G1", "G2"]}
        excluded = validate_excluded(rows, required, ["B"])
        ranking = arrange_timetables(rows, required, profile(), pins={"G1": ["A"]}, excluded=excluded)
        self.assertEqual(ranking["top"][0]["option_ids"], ["A", "C"])
        with self.assertRaises(ScheduleDataError):
            validate_excluded(rows, required, ["Z"])


class ConflictReasonTests(unittest.TestCase):
    def test_conflicts_caused_by_limits_are_named_as_such(self):
        rows = [meeting("a", "G1", "A", "2026-08-03", 540, 600),
                meeting("b", "G2", "B", "2026-08-04", 540, 600)]
        required = {"TEST1234": ["G1", "G2"]}
        ranking = arrange_timetables(rows, required, profile(max_days_per_week=1))
        self.assertEqual(ranking["feasible_count"], 0)
        self.assertEqual(ranking["conflict_core"]["reason"], "limits")
        self.assertIn("limits", ranking["no_feasible_reason"])
        clash = [meeting("a", "G1", "A", "2026-08-03", 540, 600),
                 meeting("b", "G2", "B", "2026-08-03", 570, 630)]
        self.assertEqual(arrange_timetables(clash, required, profile(max_days_per_week=1))["conflict_core"]["reason"],
                         "time_overlap")

    def test_a_limit_can_be_loosened_one_step_instead_of_dropped(self):
        rows = [meeting("a", "G1", "A", "2026-08-03", 540, 600),
                meeting("b", "G2", "B", "2026-08-04", 540, 600)]
        required = {"TEST1234": ["G1", "G2"]}
        changes = arrange_timetables(rows, required, profile(max_days_per_week=1))["what_if"]["changes"]
        step = [change for change in changes if change["kind"] == "max_days_per_week" and change.get("value")]
        self.assertEqual([(change["value"], change["count"]) for change in step], [(2, 1)])
        self.assertTrue(any(change["kind"] == "max_days_per_week" and "value" not in change for change in changes))
