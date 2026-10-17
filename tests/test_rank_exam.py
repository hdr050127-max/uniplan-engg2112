"""The final-exam script on a two-persona dummy exam (never the real one, and no LLM)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from llm.rank import exam


class ExamTests(unittest.TestCase):
    def test_prepare_then_score_once(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "personas.json").write_text(json.dumps({"personas": [
                {"id": "d1", "text": "我住得远，想少来几天。", "units": ["ENGG2112", "AMME2301"],
                 "conditions": {"cares": ["campus_days"]}},
                {"id": "d2", "text": "我讨厌课间干等。", "units": ["ENGG2112", "AMME2301"],
                 "conditions": {"cares": ["gap"], "preferred_hours": {"weekday": 0, "start_min": 600, "end_min": 1080}}},
            ]}, ensure_ascii=False))
            summary = exam.prepare(folder)
            self.assertEqual(summary["personas"], 2)
            self.assertEqual(summary["questions"], 2 * 28)
            questions = [json.loads(line) for line in (folder / "questions.jsonl").read_text().splitlines()]
            self.assertTrue(all({"pair_id", "persona", "table", "red", "blue"} <= set(q) for q in questions))
            self.assertFalse(any("a_id" in q or "label" in q for q in questions))       # no key, no answers
            key = json.loads((folder / "key.json").read_text())
            self.assertEqual(sum(info["red"] == "A" for info in key.values()), len(key) // 2)
            # A dummy annotator: the lower main-concern number wins.
            bundle = json.loads((folder / "candidates.json").read_text())
            x = {(pid, c["candidate_id"]): c["x"] for pid, cs in bundle["candidates"].items() for c in cs}
            feature = {"d1": "campus_days", "d2": "gap_h"}
            with (folder / "answers.jsonl").open("w") as handle:
                for pair_id, info in key.items():
                    a, b = x[(info["persona"], info["a_id"])], x[(info["persona"], info["b_id"])]
                    f = feature[info["persona"]]
                    winner = "tie" if abs(a[f] - b[f]) < 1e-9 else ("A" if a[f] < b[f] else "B")
                    choice = "差不多" if winner == "tie" else ("红" if winner == info["red"] else "蓝")
                    handle.write(json.dumps({"pair_id": pair_id, "choice": choice}, ensure_ascii=False) + "\n")
            with mock.patch.object(exam, "OUT", folder / "out"):
                report = exam.score(folder)
                with self.assertRaises(SystemExit):
                    exam.score(folder)                                   # one sitting only
            rows = {row["method"]: row for row in report["results"]}
            self.assertEqual(rows["按 cares 打分（原占位版）"]["pairwise_accuracy"], 1.0)   # same rule as the annotator
            self.assertTrue(0 <= rows["定稿模型（model.json，逻辑回归）"]["pairwise_accuracy"] <= 1)
            self.assertEqual(len(report["model_json_sha256"]), 64)
            self.assertTrue((folder / "out" / "exam_report.md").exists())

    def test_bad_personas_are_rejected(self):
        with self.assertRaises(ValueError):
            exam.check_persona({"id": "z", "text": "x", "units": ["ENGG2112"], "conditions": {"cares": ["weather"]}})


if __name__ == "__main__":
    unittest.main()
