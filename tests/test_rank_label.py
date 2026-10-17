"""The labelling rules: program ties, dominance, swapped answers and the shown table."""
import unittest
from unittest import mock

from llm.rank import label
from llm.rank.features import NAMES


def candidate(cid: str, **values) -> dict:
    x = {name: 0.0 for name in NAMES}
    x.update(earliest_start=9.0, latest_end=17.0, **values)
    return {"candidate_id": cid, "x": x, "table": label.table_values(x), "text": "周一：没课"}


PERSONA = {"id": "commuter_x", "split": "train", "focus": "campus_days", "text": "我住得远，想少来几天。",
           "conditions": {"cares": ["campus_days"]}}


class LabelRuleTests(unittest.TestCase):
    def test_near_equal_main_concern_is_decided_by_the_program(self):
        a = candidate("a", campus_days=2.0, gap_h=1.0)
        b = candidate("b", campus_days=2.1, gap_h=3.0)     # b waits two more hours a week
        c = candidate("c", campus_days=2.1, gap_h=0.0, single_class_days=1.0)
        self.assertTrue(label.program_tie(PERSONA, a, b))
        with mock.patch.object(label, "ask") as ask:
            dominated = label.judge("m", PERSONA, a, b)
            mixed = label.judge("m", PERSONA, a, c)
            strict = label.judge("m", PERSONA, a, b, ties="strict")
        ask.assert_not_called()
        self.assertEqual((dominated["label"], dominated["source"]), ("A", "program_dominance"))
        self.assertEqual((mixed["label"], mixed["source"]), ("tie", "program"))
        self.assertEqual(strict["label"], "tie")

    def test_dominance_needs_a_real_difference(self):
        a = candidate("a", gap_h=1.0)
        self.assertFalse(label.dominates(a, candidate("b", gap_h=1.4)))   # under half an hour
        self.assertTrue(label.dominates(a, candidate("b", gap_h=1.6)))
        self.assertFalse(label.dominates(a, a))

    def test_swapped_answers_are_mapped_back_to_a_and_b(self):
        a, b = candidate("a", campus_days=2.0), candidate("b", campus_days=3.0)
        answers = iter([{"focus": "到校天数", "reason": "", "choice": "红"},    # red = A
                        {"focus": "到校天数", "reason": "", "choice": "蓝"}])   # red = B, so blue = A
        with mock.patch.object(label, "ask", side_effect=lambda *args, **kwargs: next(answers)):
            row = label.judge("m", PERSONA, a, b)
        self.assertEqual((row["label"], row["first"], row["second"]), ("A", "A", "A"))
        self.assertEqual(row["focus_ok"], [True, True])
        flips = iter([{"focus": "到校天数", "reason": "", "choice": "红"}] * 2)
        with mock.patch.object(label, "ask", side_effect=lambda *args, **kwargs: next(flips)):
            self.assertEqual(label.judge("m", PERSONA, a, b)["label"], "flip")

    def test_the_table_uses_the_students_own_hours(self):
        persona = {**PERSONA, "conditions": {"cares": ["outside_hours"],
                                             "preferred_hours": {"weekday": 0, "start_min": 570, "end_min": 960}}}
        text = label.question(persona, candidate("a", outside_h=1.5), candidate("b"))
        self.assertIn("早晚课：09:30 前或 16:00 后（分钟/周） | 90 | 0 |", text)
        self.assertIn("学生情况：我住得远", text)


if __name__ == "__main__":
    unittest.main()
