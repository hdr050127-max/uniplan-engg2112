import random
import unittest
from datetime import date

from uniplan.arrangement import arrange_timetables
from uniplan.choice_model import (MenuChoice, choice_probabilities, equal_prior,
                                  fit_conditional_logit, fit_population, from_scaled,
                                  implied_weights, leave_one_participant_out, natural_row,
                                  trade_offs)
from uniplan.ranking import AXIS_SETS, pareto_front, rank_schedules, weekday_pattern
from uniplan.schedule import Candidate, Meeting


def entry(cid, gap, days, outside):
    return {"candidate_id": cid, "features": {"gap_min": gap, "campus_days": days, "outside_min": outside}}


def meeting(meeting_id, group, option, day, start, end, building="J01"):
    return {"meeting_id": meeting_id, "unit_code": "TEST1234", "group_id": group, "option_id": option,
            "date": day, "start_min": str(start), "end_min": str(end), "building_code": building,
            "status": "available", "activity_type": "Tutorial", "location_raw": building}


class ParetoTests(unittest.TestCase):
    def test_front_keeps_only_non_dominated_profiles(self):
        pool = [entry("a", 0, 4, 0), entry("b", 200, 2, 0), entry("c", 250, 2, 30),
                entry("d", 100, 3, 0), entry("e", 120, 3, 10)]
        self.assertEqual({item["candidate_id"] for item in pareto_front(pool)}, {"a", "b", "d"})
        # Ignoring gaps, "b" (2 days, 0 outside) beats everything else.
        self.assertEqual([item["candidate_id"] for item in pareto_front(pool, ("campus_days", "outside_hours"))], ["b"])
        with self.assertRaises(ValueError):
            pareto_front(pool, ())
        self.assertEqual(len(AXIS_SETS), 7)

    def test_ties_on_chosen_axes_keep_the_best_on_the_rest(self):
        pool = [entry("z", 300, 2, 0), entry("y", 100, 2, 0)]
        self.assertEqual([item["candidate_id"] for item in pareto_front(pool, ("campus_days",))], ["y"])

    def test_weekday_pattern_ignores_one_off_and_online_meetings(self):
        tuesdays = [Meeting(date(2026, 8, 4 + 7 * week), 540, 600, "J01", False, "t") for week in range(3)]
        friday = Meeting(date(2026, 8, 7), 540, 600, "J01", False, "f")
        mondays = [Meeting(date(2026, 8, 3 + 7 * week), 540, 600, "", True, "m") for week in range(3)]
        self.assertEqual(weekday_pattern(Candidate("c", (), tuple(tuesdays + [friday] + mondays))), "2")

    def test_zero_weight_ties_never_prefer_more_of_the_ignored_cost(self):
        first = Meeting(date(2026, 8, 3), 540, 600, "J01", False, "x")
        late = Meeting(date(2026, 8, 3), 780, 840, "J01", False, "late")
        near = Meeting(date(2026, 8, 3), 600, 660, "J01", False, "near")
        profile = {"unavailable_windows": [], "preferred_hours": {"start_min": 0, "end_min": 1440},
                   "weights": {"gap": 0.0, "campus_days": 0.5, "outside_hours": 0.5}}
        # "0000" sorts first by id but waits three hours longer; equal D and O must not win on id.
        ranking = rank_schedules([Candidate("0000", ("x", "late"), (first, late)),
                                  Candidate("ffff", ("x", "near"), (first, near))],
                                 profile, (date(2026, 8, 3),))
        self.assertEqual(ranking["top"][0]["candidate_id"], "ffff")

    def test_shortlist_offers_weekday_variants_of_one_profile(self):
        rows = [
            meeting("a1", "G1", "A", "2026-08-03", 540, 600), meeting("a2", "G1", "A", "2026-08-10", 540, 600),
            meeting("a3", "G1", "A", "2026-08-17", 540, 600),
            # Two tutorials with identical times on different weekdays: same G/D/O, different days.
            *[meeting(f"b{w}", "G2", "B", f"2026-08-{4 + 7 * w:02d}", 540, 600) for w in range(3)],
            *[meeting(f"c{w}", "G2", "C", f"2026-08-{5 + 7 * w:02d}", 540, 600) for w in range(3)],
        ]
        profile = {"unavailable_windows": [], "transition_min": 0,
                   "preferred_hours": {"start_min": 540, "end_min": 1080},
                   "weights": {"gap": 1 / 3, "campus_days": 1 / 3, "outside_hours": 1 / 3}}
        ranking = arrange_timetables(rows, {"TEST1234": ["G1", "G2"]}, profile)
        shortlist = ranking["shortlist"]
        menu = shortlist["menus"][shortlist["default_axes"]]
        self.assertEqual(len(menu), 1)
        item = shortlist["items"][menu[0]]
        self.assertEqual(sorted(variant["pattern"] for variant in item["variants"]), ["12", "13"])
        for variant in item["variants"]:
            self.assertIn(variant["candidate_id"], shortlist["items"])
            self.assertEqual(shortlist["items"][variant["candidate_id"]]["pattern"], variant["pattern"])
        self.assertEqual(shortlist["dominated_profiles"], 0)


class ChoiceModelTests(unittest.TestCase):
    def synthetic(self, true, participants=80, seed=1):
        rng = random.Random(seed)
        choices = []
        for index in range(participants * 4):
            menu = tuple(natural_row(rng.uniform(0, 600), rng.uniform(1, 5), rng.uniform(0, 240))
                         for _ in range(rng.choice((2, 3, 4))))
            pick, chosen = rng.random(), len(menu) - 1
            for position, prob in enumerate(choice_probabilities(true, menu)):
                pick -= prob
                if pick < 0:
                    chosen = position
                    break
            choices.append(MenuChoice(f"p{index // 4}", menu, chosen))
        return choices

    def test_fit_recovers_known_trade_off(self):
        true = (-0.8, -2.0, -0.5)
        beta = fit_conditional_logit(self.synthetic(true, 150), l2=0.0)
        rates = trade_offs(beta)
        self.assertAlmostEqual(rates["gap_hours_per_campus_day"], 2.5, delta=0.6)
        weights = implied_weights(beta)
        self.assertAlmostEqual(sum(abs(value) for value in weights.values()), 1.0)
        self.assertEqual(max(weights, key=weights.get), "campus_days")

    def test_prior_without_data_and_unit_conversions(self):
        self.assertEqual(fit_population([]), equal_prior())
        self.assertEqual(implied_weights(equal_prior()),
                         {"gap": 1 / 3, "campus_days": 1 / 3, "outside_hours": 1 / 3})
        self.assertEqual(from_scaled((1.0, 0.4, 0.5)), (5.0, 2.0, 1.0))
        self.assertEqual(trade_offs((0.1, -1.0, -1.0))["gap_hours_per_campus_day"], None)
        self.assertLess(implied_weights((0.5, -1.0, 0.0))["gap"], 0)

    def test_leave_one_participant_out_beats_random(self):
        evaluation = leave_one_participant_out(self.synthetic((-0.2, -3.0, -0.2), 30))
        self.assertEqual(evaluation["participants"], 30)
        accuracy = evaluation["accuracy"]
        self.assertGreater(accuracy["pooled logit"], accuracy["random guess"] + 0.2)
        self.assertGreater(accuracy["pooled logit"], accuracy["equal weights"])


if __name__ == "__main__":
    unittest.main()
