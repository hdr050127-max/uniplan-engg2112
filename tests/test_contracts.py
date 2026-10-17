"""The shapes every block promises the others (llm/contracts.py). Must stay green on every branch."""
import unittest

from llm.contracts import HARD_FIELDS, SOFT_FIELDS, to_profile_fields, preferences_of
from llm.explain import explain
from llm.parse import parse
from llm.parse.labels import LABELS
from llm.rank import rank

CANDIDATES = [
    {"candidate_id": "a", "features": {"campus_days": 3.0, "gap_min": 100.0, "outside_min": 0.0}},
    {"candidate_id": "b", "features": {"campus_days": 2.0, "gap_min": 300.0, "outside_min": 30.0}},
    {"candidate_id": "c", "features": {"campus_days": 4.0, "gap_min": 0.0, "outside_min": 60.0}},
]


class ContractTests(unittest.TestCase):
    def test_parse_returns_clauses_conditions_and_leftovers(self):
        result = parse("我周五要打工，而且不想课之间等太久. I hate long gaps")
        self.assertEqual(set(result), {"clauses", "conditions", "unrecognised"})
        for clause in result["clauses"]:
            self.assertEqual(set(clause), {"text", "label", "fields"})
            self.assertIn(clause["label"], LABELS)
            self.assertTrue(set(clause["fields"]) <= set(HARD_FIELDS + SOFT_FIELDS))
        self.assertTrue(set(result["conditions"]) <= set(HARD_FIELDS + SOFT_FIELDS))
        for window in result["conditions"].get("unavailable_windows", []):
            self.assertTrue(1 <= window["weekday"] <= 7 and 0 <= window["start_min"] < window["end_min"] <= 1440)

    def test_parse_handles_empty_input(self):
        self.assertEqual(parse(""), {"clauses": [], "conditions": {}, "unrecognised": []})

    def test_conditions_convert_to_scheduler_profile_fields(self):
        conditions = parse("周五要打工")["conditions"]
        fields = to_profile_fields({**conditions, "preferred_hours": {"weekday": 1, "start_min": 600, "end_min": 1080}})
        self.assertEqual(fields["preferred_hours"], {"start_min": 600, "end_min": 1080})
        self.assertNotIn("cares", fields)
        self.assertEqual(preferences_of({"cares": ["gap"]}, "x")["cares"], ["gap"])

    def test_rank_orders_every_candidate_once(self):
        ranked = rank(CANDIDATES, {"cares": ["campus_days"], "student_text": ""})
        self.assertEqual(sorted(item["candidate_id"] for item in ranked), ["a", "b", "c"])
        self.assertEqual([item["score"] for item in ranked], sorted((item["score"] for item in ranked), reverse=True))
        self.assertEqual(ranked[0]["candidate_id"], "b")

    def test_explain_gives_one_reason_per_pick(self):
        reasons = explain("", {}, CANDIDATES[:2])
        self.assertEqual(len(reasons), 2)
        self.assertTrue(all(isinstance(reason, str) and reason for reason in reasons))


if __name__ == "__main__":
    unittest.main()
