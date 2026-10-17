"""The closest timetables when nothing meets every limit (uniplan.nearest, docs/DESIGN.md 10.1)."""

import json
import unittest
from datetime import date, timedelta
from pathlib import Path

import llm.parse as parse_module
from uniplan import advisor, nearest
from uniplan.catalog import SnapshotCatalog
from uniplan.main import main
from uniplan.schedule import ClassOption, Meeting

ROOT = Path(__file__).resolve().parent.parent
MONDAY = date(2026, 8, 3)


def setUpModule():
    parse_module.RUNTIME = "linear"  # no model calls from tests


def option(option_id, group_id, weekday, start, end, *, weeks=4, online=False, seats="", assessment=False):
    meetings = tuple(Meeting(date=MONDAY + timedelta(days=7 * week + weekday - 1), start_min=start, end_min=end,
                             building_code="" if online else "J01", is_online=online, option_id=option_id,
                             unit_code=group_id.split("|")[0], group_id=group_id, available_seats=seats,
                             is_fixed_assessment=assessment)
                     for week in range(weeks))
    return ClassOption(option_id=option_id, group_id=group_id, meetings=meetings, is_full=False)


PROFILE = {"preferred_hours": {"start_min": 540, "end_min": 1080}, "unavailable_windows": [], "transition_min": 0,
           "weights": {"gap": 1, "campus_days": 1, "outside_hours": 1}}


class MeasureTests(unittest.TestCase):
    def test_each_limit_is_measured_in_minutes_a_week_and_named(self):
        options = [option("A|Lecture|01", "ENGG2112|Lecture", 3, 480, 600),    # Wed 8 am to 10 am
                   option("A|Tutorial|01", "ENGG2112|Tutorial", 3, 600, 810),  # Wed 10 am to 1:30 pm
                   option("B|Lab|01", "AMME2301|Lab", 2, 720, 840, online=True, seats="3"),
                   option("B|Quiz|01", "AMME2301|Quiz", 3, 420, 480, assessment=True)]  # exempt, as in the strict search
        early = [{"weekday": day, "start_min": 0, "end_min": 570} for day in range(1, 6)]
        found = nearest.measure(options, {**PROFILE, "unavailable_windows": early}, 4)
        self.assertEqual(found, [{"kind": "unavailable_windows", "amount": 90.0, "text": "1 class on Wed before 9:30 am"}])
        profile = {**PROFILE, "max_days_per_week": 1, "max_daily_minutes": 180, "max_daily_span": 240,
                   "lunch": {"start_min": 690, "end_min": 840, "minutes": 45}, "in_person_only": True, "min_seats": 5}
        found = {item["kind"]: item for item in nearest.measure(options, profile, 4, frozenset({"AMME2301|Lab"}))}
        self.assertNotIn("max_days_per_week", found)  # Tuesday is online only: one campus day a week
        self.assertEqual(found["max_daily_minutes"]["text"], "Up to 5 h 30 min of class a day, over the 3 h limit")
        self.assertEqual(found["max_daily_minutes"]["amount"], 150.0)
        self.assertEqual(found["max_daily_span"]["text"], "Up to 5 h 30 min on campus a day, over the 4 h limit")
        self.assertEqual(found["lunch"]["text"], "No 45 min lunch break on Tue and Wed")
        self.assertEqual(found["lunch"]["amount"], 90.0)
        self.assertEqual((found["in_person_only"]["text"], found["in_person_only"]["amount"]), ("1 online class", 120.0))
        self.assertEqual(found["min_seats"]["text"], "1 class with under 5 seats left")

    def test_days_over_the_limit_count_each_extra_day(self):
        options = [option("A|Lecture|01", "X|Lecture", 1, 600, 660), option("A|Tutorial|01", "X|Tutorial", 3, 600, 660),
                   option("A|Lab|01", "X|Lab", 5, 600, 660)]
        (found,) = nearest.measure(options, {**PROFILE, "max_days_per_week": 2}, 4)
        self.assertEqual((found["kind"], found["amount"]), ("max_days_per_week", nearest.DAY_MINUTES))
        self.assertEqual(found["text"], "3 days on campus a week, over the limit of 2")

    def test_closer_means_fewer_limits_then_less_amount(self):
        one_big = [{"amount": 200.0}]
        two_small = [{"amount": 5.0}, {"amount": 5.0}]
        self.assertLess(nearest.closeness(one_big), nearest.closeness(two_small))
        self.assertLess(nearest.closeness([{"amount": 20.0}]), nearest.closeness([{"amount": 60.0}]))
        self.assertEqual(nearest.closeness([{"amount": 20.0}]), nearest.closeness([{"amount": 24.0}]))  # model decides
        self.assertEqual(nearest.broken_line([{"text": "1 class on Wed before 9:30 am"}]),
                         "Breaks one limit: 1 class on Wed before 9:30 am")

    def test_a_clash_drops_the_lecture_that_misses_least(self):
        groups = [("ENGG2112|Lecture", (option("E|L|01", "ENGG2112|Lecture", 1, 540, 660),)),
                  ("AMME2301|Lecture1", (option("A|L1|01", "AMME2301|Lecture1", 1, 600, 660),)),
                  ("AMME2301|Tutorial", (option("A|T|01", "AMME2301|Tutorial", 2, 540, 600),))]
        # Without the ENGG2112 lecture (2 h) or AMME2301 Lecture1 (1 h) the rest fits; the shorter one goes.
        self.assertEqual(nearest._recording(groups, PROFILE, 4, 100_000), "AMME2301|Lecture1")
        tutorials = [("X|Tutorial", (option("X|T|01", "X|Tutorial", 1, 540, 600),)),
                     ("Y|Tutorial", (option("Y|T|01", "Y|Tutorial", 1, 540, 600),))]
        self.assertIsNone(nearest._recording(tutorials, PROFILE, 4, 100_000))  # no lecture to drop


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = SnapshotCatalog(ROOT / "data/processed", ROOT / "data/requirements")
        cls.base = {"schema_version": 1, "year": 2026, "session_code": "S2C", "unit_codes": ["ENGG2112", "AMME2301"],
                    "unavailable_windows": []}
        data = main(cls.base, cls.catalog)["module_two_result"]
        cls.groups = {unit["unit_code"]: [g["group_id"] for g in unit["groups"] if g["default_selected"]]
                      for unit in data["units"]}

    def plan(self, profile, nearest_on, text="no classes before 11am and nothing after 3pm, and no Fridays"):
        return main(profile, self.catalog, selected_groups=self.groups, student_text=text, nearest=nearest_on)

    def test_a_timetable_that_fits_is_exactly_as_before(self):
        profile = {**self.base, "unavailable_windows": [{"weekday": 5, "start_min": 0, "end_min": 1440}], "max_days_per_week": 3}
        before, after = self.plan(profile, False, "no Fridays"), self.plan(profile, True, "no Fridays")
        self.assertEqual(before["status"], "ready")
        for result in (before, after):
            result["profile"].pop("profile_id")  # a fresh random id for every request
        self.assertEqual(json.dumps(before, sort_keys=True, default=str), json.dumps(after, sort_keys=True, default=str))

    def test_nothing_fits_gives_the_closest_timetables_without_a_clash(self):
        windows = ([{"weekday": day, "start_min": 0, "end_min": 660} for day in range(1, 6)] +
                   [{"weekday": day, "start_min": 900, "end_min": 1440} for day in range(1, 6)] +
                   [{"weekday": 5, "start_min": 0, "end_min": 1440}])
        profile = {**self.base, "unavailable_windows": windows}
        self.assertEqual(self.plan(profile, False)["status"], "no_feasible")
        result = self.plan(profile, True)
        self.assertEqual(result["status"], "nearest")
        ranking = result["ranking_result"]
        self.assertIn("no_feasible_reason", ranking["strict"])
        relaxed = nearest.soften(result["profile"])
        for axes, menu in ranking["recommendation"]["menus"].items():
            picks = [ranking["shortlist"]["items"][cid] for cid in menu["picks"]]
            self.assertTrue(picks, axes)
            closeness = [nearest.closeness(pick["breaks"]) for pick in picks]
            self.assertEqual(closeness, sorted(closeness))
            for pick, reason in zip(picks, menu["reasons"]):
                self.assertEqual(advisor.hard_violations(pick["meetings"], relaxed), [])  # never a real clash
                self.assertTrue(pick["broken"].startswith("Breaks "), pick["broken"])
                self.assertTrue(reason.startswith(pick["broken"] + "."), reason)

    def test_a_real_clash_watches_one_lecture_as_a_recording(self):
        # Tutorial 06 (pinned: say, already enrolled) meets when AMME2301's only Lecture1 does.
        pins = {"ENGG2112-S2C-ND-CC|Tutorial": ["ENGG2112-S2C-ND-CC|Tutorial|06"]}
        strict = main(self.base, self.catalog, selected_groups=self.groups, student_text="", pins=pins)
        self.assertEqual(strict["status"], "no_feasible")
        result = main(self.base, self.catalog, selected_groups=self.groups, student_text="", pins=pins, nearest=True)
        self.assertEqual(result["status"], "nearest")
        ranking = result["ranking_result"]
        self.assertEqual(ranking["nearest"]["watch"], "AMME2301-S2C-ND-CC|Lecture1")
        menu = ranking["recommendation"]["menus"]["gap,campus_days,outside_hours"]
        for cid, reason in zip(menu["picks"], menu["reasons"]):
            pick = ranking["shortlist"]["items"][cid]
            self.assertTrue(reason.startswith("Watch the recording of AMME2301 Lecture1."), reason)
            self.assertNotIn("Lecture1", " ".join(pick["option_ids"]))
            self.assertIn("ENGG2112-S2C-ND-CC|Tutorial|06", pick["option_ids"])
            self.assertEqual(advisor.hard_violations(pick["meetings"], nearest.soften(result["profile"])), [])


if __name__ == "__main__":
    unittest.main()
