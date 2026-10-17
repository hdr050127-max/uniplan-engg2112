import unittest
from datetime import date

from uniplan.arrangement import arrange_timetables
from uniplan.ranking import extract_schedule_features, rank_schedules, scale_sensitivity
from uniplan.schedule import (Candidate, Meeting, ScheduleDataError, SearchLimitError,
                              extract_class_options, find_conflict_core,
                              generate_feasible_schedules, is_fixed_assessment, linked_option_id)
from uniplan.timetable_data import group_default, load_timetable_data


def meeting(meeting_id, group, option, day, start, end, building, status="available"):
    return {
        "meeting_id": meeting_id, "unit_code": "TEST1234", "group_id": group,
        "option_id": option, "date": day, "start_min": str(start), "end_min": str(end),
        "building_code": building, "status": status, "activity_type": "Tutorial",
        "location_raw": building,
    }


def profile(**overrides):
    data = {
        "unavailable_windows": [], "transition_min": 20,
        "preferred_hours": {"start_min": 540, "end_min": 1080},
        "weights": {"gap": .9, "campus_days": .1, "outside_hours": 0},
    }
    data.update(overrides)
    return data


class ScheduleTests(unittest.TestCase):
    def test_exact_dates_and_hard_constraints(self):
        rows = [
            meeting("a", "G1", "A", "2026-08-03", 540, 600, "J01"),
            meeting("b", "G2", "B", "2026-08-03", 610, 670, "J02"),
            meeting("c", "G2", "C", "2026-08-10", 610, 670, "J02"),
            meeting("d", "G2", "D", "2026-08-03", 630, 690, "J02"),
            meeting("e", "G2", "E", "2026-08-03", 630, 690, "J02", "full"),
            meeting("f", "G2", "F", "2026-08-03", 570, 630, "J01"),
        ]
        groups = extract_class_options(rows, {"TEST1234": ["G1", "G2"]})
        options = {candidate.option_ids for candidate in generate_feasible_schedules(groups, profile())}
        self.assertEqual(options, {("A", "C"), ("A", "D")})
        blocked = profile(unavailable_windows=[{"weekday": 1, "start_min": 620, "end_min": 640}])
        options = {candidate.option_ids for candidate in generate_feasible_schedules(groups, blocked)}
        self.assertEqual(options, set())

    def test_weekly_means_and_weighted_order_differ_from_equal_baseline(self):
        first = Meeting(date(2026, 8, 3), 540, 600, "J01", False, "first")
        same_day = Meeting(date(2026, 8, 3), 630, 690, "J01", False, "same")
        next_day = Meeting(date(2026, 8, 4), 540, 600, "J01", False, "next")
        compact = Candidate("compact", ("first", "same"), (first, same_day))
        spread = Candidate("spread", ("first", "next"), (first, next_day))
        weeks = (date(2026, 8, 3), date(2026, 8, 10))
        features = extract_schedule_features(compact, profile(), weeks)
        self.assertEqual(features, {"gap_min": 15, "campus_days": .5, "outside_min": 0})
        ranking = rank_schedules([compact, spread], profile(), (weeks[0],))
        self.assertEqual(ranking["top"][0]["candidate_id"], "spread")
        self.assertEqual(ranking["equal_weight_top"][0]["candidate_id"], "compact")

    def test_arrangement_keeps_complete_class_dates_and_search_evidence(self):
        rows = [
            meeting("a1", "G1", "A", "2026-08-03", 540, 600, "J01"),
            meeting("a2", "G1", "A", "2026-08-10", 540, 600, "J01"),
            meeting("b", "G2", "B", "2026-08-03", 570, 630, "J01"),
            meeting("c", "G2", "C", "2026-08-03", 620, 680, "J02"),
            meeting("d", "G2", "D", "2026-08-03", 700, 760, "J01", "full"),
        ]
        ranking = arrange_timetables(rows, {"TEST1234": ["G1", "G2"]}, profile())
        self.assertEqual(ranking["feasible_count"], 1)
        self.assertEqual(ranking["top"][0]["option_ids"], ["A", "C"])
        self.assertEqual([item["date"] for item in ranking["top"][0]["meetings"]], [
            "2026-08-03", "2026-08-03", "2026-08-10",
        ])
        self.assertEqual(ranking["teaching_weeks"], ["2026-08-03", "2026-08-10"])
        self.assertEqual(ranking["search"]["full_options"], 1)
        self.assertEqual(ranking["search"]["rejected_branches"], 1)

    def test_no_feasible_explains_empty_group_and_search_limit_is_not_partial(self):
        rows = [
            meeting("a", "G1", "A", "2026-08-03", 540, 600, "J01", "full"),
            meeting("b", "G2", "B", "2026-08-03", 620, 680, "J02"),
        ]
        ranking = arrange_timetables(rows, {"TEST1234": ["G1", "G2"]}, profile())
        self.assertEqual(ranking["feasible_count"], 0)
        self.assertIn("G1", ranking["no_feasible_reason"])
        self.assertEqual(ranking["search"]["groups_without_options"], ("G1",))
        rows[0]["status"] = "available"
        with self.assertRaises(SearchLimitError):
            arrange_timetables(rows, {"TEST1234": ["G1", "G2"]}, profile(), max_nodes=1)

    def test_rejects_option_id_reused_across_courses(self):
        rows = [meeting("a", "G1", "A", "2026-08-03", 540, 600, "J01")]
        other = meeting("b", "G2", "A", "2026-08-04", 540, 600, "J01")
        other["unit_code"] = "OTHER1234"
        rows.append(other)
        with self.assertRaises(ScheduleDataError):
            extract_class_options(rows, {"TEST1234": ["G1"]})

    def test_no_feasible_explains_conflict_between_eligible_groups(self):
        rows = [
            meeting("a", "G1", "A", "2026-08-03", 540, 600, "J01"),
            meeting("b", "G2", "B", "2026-08-03", 570, 630, "J01"),
        ]
        ranking = arrange_timetables(rows, {"TEST1234": ["G1", "G2"]}, profile())
        self.assertEqual(ranking["feasible_count"], 0)
        self.assertEqual(ranking["search"]["groups_without_options"], ())
        self.assertIn("same times", ranking["no_feasible_reason"])

    def test_assessment_parts_stay_together_and_ignore_day_avoidance(self):
        assessment = []
        for part, day in (("P1", "2026-08-06"), ("P2", "2026-08-13")):
            row = meeting(part, "TEST1234|Assessment", f"TEST1234|Assessment|01-{part}",
                          day, 600, 660, "J01")
            row.update(activity_group="Assessment", activity_type="Assessment",
                       class_code=f"01-{part}")
            assessment.append(row)
        lecture_conflict = meeting("l1", "TEST1234|Lecture", "TEST1234|Lecture|01",
                                   "2026-08-06", 600, 660, "J01")
        lecture_other = meeting("l2", "TEST1234|Lecture", "TEST1234|Lecture|02",
                                "2026-08-03", 540, 600, "J01")
        rows = assessment + [lecture_conflict, lecture_other]
        self.assertEqual(linked_option_id(assessment[0]), "TEST1234|Assessment|01")
        self.assertTrue(is_fixed_assessment(assessment[0]))
        self.assertFalse(is_fixed_assessment(lecture_other))
        groups = {"TEST1234": ["TEST1234|Assessment", "TEST1234|Lecture"]}
        avoid_thursday = profile(unavailable_windows=[
            {"weekday": 4, "start_min": 0, "end_min": 1440},
        ])
        ranking = arrange_timetables(rows, groups, avoid_thursday)
        self.assertEqual(ranking["feasible_count"], 1)
        top = ranking["top"][0]
        self.assertEqual(top["option_ids"], ["TEST1234|Assessment|01", "TEST1234|Lecture|02"])
        self.assertEqual([item["date"] for item in top["meetings"] if item["is_fixed_assessment"]],
                         ["2026-08-06", "2026-08-13"])
        self.assertEqual(sum(item["unavailable_exception"] for item in top["meetings"]), 2)
        # The fixed assessment is still an actual time conflict for Lecture 01.
        self.assertEqual(arrange_timetables(rows, groups, profile())["feasible_count"], 1)

    def test_test_quiz_exempt_but_practical_remains_avoided(self):
        test = meeting("test", "TEST1234|Test", "TEST1234|Test|01",
                       "2026-08-06", 600, 660, "J01")
        test.update(activity_group="Test", activity_type="Test")
        quiz = meeting("quiz", "TEST1234|Quiz", "TEST1234|Quiz|01",
                       "2026-08-13", 600, 630, "J01")
        quiz.update(activity_group="Quiz", activity_type="Quiz")
        practical_thu = meeting("p1", "TEST1234|Practical", "TEST1234|Practical|01",
                                "2026-08-06", 720, 780, "J01")
        practical_mon = meeting("p2", "TEST1234|Practical", "TEST1234|Practical|02",
                                "2026-08-03", 720, 780, "J01")
        ranking = arrange_timetables(
            [test, quiz, practical_thu, practical_mon],
            {"TEST1234": ["TEST1234|Test", "TEST1234|Quiz", "TEST1234|Practical"]},
            profile(unavailable_windows=[{"weekday": 4, "start_min": 0, "end_min": 1440}]),
        )
        self.assertEqual(ranking["feasible_count"], 1)
        self.assertIn("TEST1234|Practical|02", ranking["top"][0]["option_ids"])

    def test_data_preview_counts_linked_parts_as_one_class(self):
        rows = []
        for part, day in (("P1", "2026-08-06"), ("P2", "2026-08-13")):
            row = meeting(part, "TEST1234|Assessment", f"TEST1234|Assessment|01-{part}",
                          day, 600, 660, "J01")
            row.update(year="2026", session_code="S2C", activity_group="Assessment",
                       activity_type="Assessment", class_code=f"01-{part}")
            rows.append(row)

        class Catalog:
            def resolve_snapshot(self, ref):
                return {"snapshot_id": "test", "year": 2026, "session_code": "S2C",
                        "unit_codes": ["TEST1234"], "rows": rows,
                        "snapshot_time": "2026-09-25T10:00:00+10:00", "source_url": "test"}

        data = load_timetable_data(
            {"year": 2026, "session_code": "S2C", "unit_codes": ["TEST1234"]},
            {"snapshot_id": "test"}, Catalog(),
        )
        unit = data.summary["units"][0]
        self.assertEqual(unit["option_count"], 1)
        self.assertEqual(unit["groups"][0]["option_count"], 1)
        self.assertEqual(unit["options_preview"][0]["class_code"], "01")
        self.assertEqual(unit["options_preview"][0]["meeting_count"], 2)


if __name__ == "__main__":
    unittest.main()


class ExplanationTests(unittest.TestCase):
    def test_conflict_core_names_only_the_clashing_groups(self):
        rows = [
            meeting("a", "G1", "A", "2026-08-03", 540, 600, "J01"),
            meeting("b", "G2", "B", "2026-08-03", 570, 630, "J01"),
            meeting("c", "G3", "C", "2026-08-04", 540, 600, "J01"),
        ]
        ranking = arrange_timetables(rows, {"TEST1234": ["G1", "G2", "G3"]}, profile())
        self.assertEqual(ranking["feasible_count"], 0)
        self.assertEqual(ranking["conflict_core"]["group_ids"], ["G1", "G2"])
        self.assertEqual(ranking["conflict_core"]["reason"], "time_overlap")
        self.assertEqual(ranking["conflict_core"]["slots"]["G1"], ["Mon 9 am to 10 am"])
        self.assertIn("G1", ranking["no_feasible_reason"])
        self.assertNotIn("G3", ranking["no_feasible_reason"])

    def test_conflict_core_separates_buffer_from_overlap(self):
        rows = [
            meeting("a", "G1", "A", "2026-08-03", 540, 600, "J01"),
            meeting("b", "G2", "B", "2026-08-03", 605, 660, "J02"),
        ]
        groups = extract_class_options(rows, {"TEST1234": ["G1", "G2"]})
        core = find_conflict_core(groups, profile(transition_min=20))
        self.assertEqual(core["reason"], "transition_buffer")
        self.assertIsNone(find_conflict_core(groups, profile(transition_min=0)))

    def test_equal_profiles_collapse_and_list_equivalent_swaps(self):
        rows = [
            meeting("a", "G1", "A", "2026-08-03", 540, 600, "J01"),
            meeting("b", "G2", "B", "2026-08-03", 600, 660, "J01"),
            meeting("c", "G2", "C", "2026-08-03", 600, 660, "J01"),
            meeting("d", "G2", "D", "2026-08-04", 600, 660, "J01"),
        ]
        ranking = arrange_timetables(rows, {"TEST1234": ["G1", "G2"]}, profile())
        self.assertEqual(ranking["feasible_count"], 3)
        self.assertEqual(ranking["distinct_profile_count"], 2)
        first = ranking["top"][0]
        self.assertIn(first["option_ids"], (["A", "B"], ["A", "C"]))
        self.assertEqual(first["equivalent_count"], 2)
        # B and C are interchangeable; D moves to another day and is not an equal swap.
        other = "C" if first["option_ids"][1] == "B" else "B"
        self.assertEqual(first["equivalent_swaps"], {"G2": [other]})
        self.assertEqual(len(ranking["top"]), 2)
        self.assertEqual(ranking["sensitivity"]["compared"], 2)
        self.assertTrue(ranking["sensitivity"]["stable"])
        self.assertEqual(len(ranking["sensitivity"]["changes"]), 6)
        self.assertEqual(len(ranking["_pool"]), 2)

    def test_sensitivity_reports_scale_dependent_rankings(self):
        pool = [
            {"key": (300.0, 1.0, 0.0), "features": {"gap_min": 300, "campus_days": 1, "outside_min": 0},
             "candidate_id": "a"},
            {"key": (0.0, 2.0, 0.0), "features": {"gap_min": 0, "campus_days": 2, "outside_min": 0},
             "candidate_id": "b"},
        ]
        weights = {"gap": .5, "campus_days": .5, "outside_hours": 0}
        # a: .5 + .1 = .6, b: .2 — b leads; a 25% larger G scale is not enough to flip it.
        result = scale_sensitivity(pool, weights, limit=1)
        self.assertTrue(result["stable"])
        close = [dict(pool[0], features={"gap_min": 60, "campus_days": 1, "outside_min": 0}), pool[1]]
        # a: .1 + .1 = .2 ties b; moving the D scale changes the leader.
        self.assertFalse(scale_sensitivity(close, weights, limit=1)["stable"])

    def test_group_defaults_skip_ignored_and_non_teaching_groups(self):
        self.assertEqual(group_default("X|Assessment-IGN", {"Assessment"}), (False, "Marked IGN in the source"))
        self.assertEqual(group_default("X|Consultation", {"Other (non teaching)*"})[0], False)
        self.assertEqual(group_default("X|Tutorial", {"Tutorial"}), (True, None))
