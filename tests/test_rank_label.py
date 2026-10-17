"""The labelling rules: program ties, dominance, swapped answers and the shown table."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from llm.rank import check, label
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


class ResumeTests(unittest.TestCase):
    def test_stop_file_pauses_after_the_pair_in_progress_and_a_rerun_continues(self):
        jobs = [(PERSONA, candidate(f"a{i}", campus_days=2.0), candidate(f"b{i}", campus_days=4.0)) for i in range(4)]
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            out, stop = folder / "labels.jsonl", folder / "STOP"
            calls = []

            def fake_judge(model, persona, a, b, ties):
                calls.append(a["candidate_id"])
                if len(calls) == 2:
                    stop.touch()                     # someone asks to pause while pair 2 runs
                return {"persona": persona["id"], "a_id": a["candidate_id"], "b_id": b["candidate_id"],
                        "label": "A", "source": "model"}

            with mock.patch.object(label, "STOP", stop), mock.patch.object(label, "judge", fake_judge):
                with self.assertRaises(SystemExit) as stopped:
                    label.run_jobs("m", jobs, out, workers=1)
                self.assertEqual(stopped.exception.code, 3)
                self.assertEqual(len(out.read_text().splitlines()), 2)    # pair 2 finished and was saved
                with out.open("a") as handle:
                    handle.write('{"persona": "commuter_x", "a_id": "a2"')   # a line cut by a hard kill
                stop.unlink()
                rows = label.run_jobs("m", jobs, out, workers=1)
            self.assertEqual(calls, ["a0", "a1", "a2", "a3"])               # nothing done twice
            self.assertEqual([row["a_id"] for row in rows], ["a0", "a1", "a2", "a3"])


class CheckTests(unittest.TestCase):
    def test_answers_map_back_and_corrections_replace_qwen(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            key = {"t1": {"purpose": "test_check", "persona": "p", "a_id": "x", "b_id": "y", "red": "B",
                          "near_equal_focus": False},
                   "a1": {"purpose": "teacher_audit", "persona": "p", "a_id": "x", "b_id": "z", "red": "A",
                          "near_equal_focus": False},
                   "a2": {"purpose": "teacher_audit", "persona": "p", "a_id": "y", "b_id": "z", "red": "A",
                          "near_equal_focus": False}}
            (folder / "key.json").write_text(json.dumps(key))
            (folder / "answers.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in (
                {"pair_id": "t1", "choice": "红"}, {"pair_id": "a1", "choice": "蓝"},
                {"pair_id": "a2", "choice": "差不多"})))
            labels = folder / "labels.jsonl"
            labels.write_text("\n".join(json.dumps(row) for row in (
                {"persona": "p", "a_id": "x", "b_id": "z", "label": "A"},
                {"persona": "p", "a_id": "y", "b_id": "z", "label": "B"},
                {"persona": "p", "a_id": "x", "b_id": "y", "label": "B"})))
            with mock.patch.object(check, "KEY", folder / "key.json"), \
                    mock.patch.object(check, "ANSWERS", folder / "answers.jsonl"), \
                    mock.patch.object(check, "ROOT", folder):
                self.assertEqual(check.claude_answers(), {"t1": "B", "a1": "B", "a2": "tie"})
                out = check.corrected(labels)
            rows = [json.loads(line) for line in out.read_text().splitlines()]
        self.assertEqual([row["label"] for row in rows], ["B", "tie", "B"])
        self.assertEqual(rows[0]["qwen_label"], "A")
        self.assertNotIn("corrected_by", rows[2])        # not audited: unchanged

    def test_agreement_leaves_ties_out(self):
        self.assertEqual(check.agreement([("A", "A"), ("A", "B"), ("tie", "A"), ("B", "B")]),
                         {"agree": 2, "compared": 3, "rate": 0.667, "left_out_ties": 1})


if __name__ == "__main__":
    unittest.main()
