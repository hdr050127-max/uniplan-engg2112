"""The ranking block: features from dated meetings, the stdlib model and rank()."""
import subprocess
import sys
import unittest
from pathlib import Path

from llm.rank import contributions, model, rank, rule_scores
from llm.rank.features import NAMES, candidate_features, timetable_features
from llm.rank.metrics import membership, teacher_order

ROOT = Path(__file__).resolve().parents[1]


def meeting(day: str, weekday: int, start: str, end: str, unit="ENGG2112", group="Lecture",
            building="J07", online=False) -> dict:
    def minutes(clock: str) -> int:
        hours, _, mins = clock.partition(":")
        return int(hours) * 60 + int(mins or 0)
    return {"date": day, "weekday": weekday, "start_min": minutes(start), "end_min": minutes(end),
            "unit_code": unit, "group_id": f"{unit}|{group}", "building_code": "" if online else building,
            "is_online": online}


def weekly(weekday: int, start: str, end: str, weeks=3, **kwargs) -> list[dict]:
    """The same class in ``weeks`` consecutive weeks, starting Monday 2026-08-03."""
    from datetime import date, timedelta
    first = date(2026, 8, 3) + timedelta(days=weekday - 1)
    return [meeting((first + timedelta(weeks=w)).isoformat(), weekday, start, end, **kwargs) for w in range(weeks)]


class FeatureTests(unittest.TestCase):
    def test_week_averages_gaps_buildings_and_single_class_days(self):
        meetings = (weekly(1, "9", "11") + weekly(1, "13", "14", group="Tutorial", building="H70") +
                    weekly(3, "16", "18", group="Lab") + weekly(5, "10", "11", online=True))
        x = timetable_features(meetings, 3, {"start_min": 540, "end_min": 1080})
        self.assertEqual(set(x), set(NAMES))
        self.assertAlmostEqual(x["campus_days"], 2.0)          # Friday is online
        self.assertAlmostEqual(x["gap_h"], 2.0)                # 11:00-13:00 on Monday
        self.assertAlmostEqual(x["building_changes"], 1.0)     # J07 -> H70
        self.assertAlmostEqual(x["single_class_days"], 1.0)    # Wednesday's lab only
        self.assertAlmostEqual(x["friday_free"], 1.0)
        self.assertAlmostEqual(x["longest_day_h"], 5.0)        # Monday 09:00-14:00
        self.assertAlmostEqual(x["online_share"], 3 / 18)
        self.assertEqual((x["earliest_start"], x["latest_end"]), (9.0, 18.0))

    def test_early_and_late_follow_the_students_own_hours(self):
        meetings = weekly(2, "9", "11") + weekly(4, "16", "18", group="Tutorial")
        default = timetable_features(meetings, 3, {"start_min": 540, "end_min": 1080})
        night_owl = timetable_features(meetings, 3, {"start_min": 600, "end_min": 1260})
        parent = timetable_features(meetings, 3, {"start_min": 570, "end_min": 960})
        self.assertEqual(default["outside_h"], 0.0)
        self.assertAlmostEqual(night_owl["early_h"], 1.0)
        self.assertAlmostEqual(parent["early_h"], 0.5)
        self.assertAlmostEqual(parent["late_h"], 2.0)

    def test_candidates_without_meetings_use_the_scheduler_features(self):
        xs = candidate_features([{"candidate_id": "a", "features": {"campus_days": 2.0, "gap_min": 90.0,
                                                                   "outside_min": 30.0}}], {})
        self.assertEqual((xs[0]["campus_days"], xs[0]["gap_h"], xs[0]["outside_h"]), (2.0, 1.5, 0.5))


class ModelTests(unittest.TestCase):
    def spec(self, weights_for_days: float = -1.0) -> dict:
        names = list(NAMES)
        weights = [0.0] * (len(names) * (1 + len(model.STUDENT_TERMS)))
        weights[names.index("campus_days")] = weights_for_days
        # focus_campus_days doubles the dislike of campus days.
        weights[len(names) * 1 + names.index("campus_days")] = weights_for_days
        return {"features": names, "center": {n: 0.0 for n in names}, "scale": {n: 1.0 for n in names},
                "weights": weights}

    def test_student_terms(self):
        self.assertEqual(model.student_terms({"cares": ["gap", "campus_days"],
                                              "preferred_hours": {"start_min": 720, "end_min": 1080}}),
                         [0, 1, 0, 1, 1, 0, 1.0, 0.0])
        self.assertEqual(model.student_terms({}), [0, 0, 0, 0, 0, 0, 0.0, 0.0])

    def test_personal_weights_and_pair_probability_agree(self):
        spec, s = self.spec(), model.student_terms({"cares": ["campus_days"]})
        self.assertEqual(model.personal_weights(s, spec)["campus_days"], -2.0)
        few, many = {n: 0.0 for n in NAMES}, {n: 0.0 for n in NAMES}
        many["campus_days"] = 1.0
        self.assertGreater(model.prefer(few, many, s, spec), 0.8)
        self.assertAlmostEqual(model.prefer(few, many, s, spec) + model.prefer(many, few, s, spec), 1.0)

    def test_rank_uses_the_model_and_breaks_ties_by_id(self):
        candidates = [{"candidate_id": cid, "features": {"campus_days": days, "gap_min": 0.0, "outside_min": 0.0}}
                      for cid, days in (("b", 2.0), ("a", 2.0), ("c", 4.0))]
        ranked = rank(candidates, {"cares": ["campus_days"]}, spec=self.spec())
        self.assertEqual([item["candidate_id"] for item in ranked], ["a", "b", "c"])
        self.assertEqual(ranked[0]["score"], 2 * -2.0)

    def test_rank_returns_every_candidate_best_first(self):
        # b saves a campus day but waits 5 hours more; a is worse than c on waiting and equal otherwise.
        candidates = [{"candidate_id": cid, "features": {"campus_days": d, "gap_min": g, "outside_min": 0.0}}
                      for cid, d, g in (("a", 3.0, 150.0), ("b", 2.0, 300.0), ("c", 3.0, 0.0))]
        for prefs in ({"cares": ["campus_days"]}, {"cares": ["gap"]}, {}):
            ranked = rank(candidates, prefs)
            self.assertEqual(sorted(item["candidate_id"] for item in ranked), ["a", "b", "c"])
            scores = [item["score"] for item in ranked]
            self.assertEqual(scores, sorted(scores, reverse=True))
            self.assertEqual(ranked[-1]["candidate_id"] == "c", False)      # c is never last: it beats a
        self.assertEqual(rank(candidates, {"cares": ["campus_days"]})[0]["candidate_id"], "b")
        self.assertEqual(rank(candidates, {"cares": ["gap"]})[0]["candidate_id"], "c")
        self.assertEqual(rank([], {}), [])

    def test_trained_model_file_is_sane(self):
        spec = model.load()
        if spec is None:
            self.skipTest("no model.json")
        self.assertEqual(spec["features"], list(NAMES))
        self.assertEqual(len(spec["weights"]), len(NAMES) * (1 + len(model.STUDENT_TERMS)))
        self.assertTrue(spec["synthetic_labels"])
        for care, feature in (("campus_days", "campus_days"), ("gap", "gap_h"), ("outside_hours", "outside_h")):
            weights = model.personal_weights(model.student_terms({"cares": [care]}), spec)
            self.assertLess(weights[feature], 0)                         # the student wants less of it
            self.assertEqual(min(weights, key=weights.get), feature)     # ...and it matters most

    def test_contributions_add_up_to_the_score_and_explain_the_winner(self):
        candidates = [{"candidate_id": cid, "features": {"campus_days": d, "gap_min": g, "outside_min": 0.0}}
                      for cid, d, g in (("few_days", 2.0, 0.0), ("more_days", 4.0, 0.0))]
        prefs = {"cares": ["campus_days"]}
        spec = self.spec()
        scores = {item["candidate_id"]: item["score"] for item in rank(candidates, prefs, spec=spec)}
        parts = {c["candidate_id"]: contributions(c, prefs, candidates, spec=spec) for c in candidates}
        for cid, part in parts.items():
            self.assertEqual(set(part), set(NAMES))
            self.assertAlmostEqual(sum(part.values()), scores[cid])
        gap = {name: parts["few_days"][name] - parts["more_days"][name] for name in NAMES}
        self.assertEqual(max(gap, key=gap.get), "campus_days")
        self.assertAlmostEqual(gap["campus_days"], 4.0)               # 2 days fewer x weight 2
        self.assertTrue(contributions(candidates[0], prefs))          # with model.json or the rule
        fallback = contributions(candidates[0], prefs, candidates, spec=None) if model.load() is None else None
        if fallback is not None:
            self.assertEqual(set(fallback), {"campus_days"})

    def test_rule_fallback(self):
        candidates = [{"candidate_id": "x", "features": {"campus_days": 2.0, "gap_min": 0.0, "outside_min": 0.0}},
                      {"candidate_id": "y", "features": {"campus_days": 3.0, "gap_min": 0.0, "outside_min": 0.0}}]
        scores = {item["candidate_id"]: item["score"] for item in rule_scores(candidates, {"cares": ["campus_days"]})}
        self.assertGreater(scores["x"], scores["y"])

    def test_runtime_imports_only_the_standard_library(self):
        code = ("import sys; import llm.rank; from llm.rank import rank; "
                "rank([{'candidate_id': 'a', 'features': {'campus_days': 1, 'gap_min': 0, 'outside_min': 0}}], {}); "
                "bad = [m for m in ('numpy', 'sklearn', 'scipy') if m in sys.modules]; print(bad)")
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), "[]")


class MetricTests(unittest.TestCase):
    def test_round_robin_points_and_top3_shares(self):
        rows = [{"a_id": "p", "b_id": "q", "label": "A"}, {"a_id": "p", "b_id": "r", "label": "A"},
                {"a_id": "q", "b_id": "r", "label": "tie"}, {"a_id": "s", "b_id": "p", "label": "flip"}]
        points = teacher_order(rows, ["p", "q", "r", "s"])
        self.assertEqual(points, {"p": 2.5, "q": 0.5, "r": 0.5, "s": 0.5})
        share = membership(points)
        self.assertEqual(share["p"], 1.0)
        self.assertAlmostEqual(sum(share.values()), 3.0)
        self.assertAlmostEqual(share["q"], 2 / 3)


if __name__ == "__main__":
    unittest.main()
