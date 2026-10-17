"""The parsing block's classifiers and scoring helpers (no model server needed)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from llm.parse import classify, linear
from llm.parse.evaluate import joined_sentences
from llm.parse.labels import parse_label
from llm.parse.metrics import classification, field_accuracy


def tiny_model(path: Path) -> None:
    """Two labels, two features: 'gap' pushes towards prefer_less_waiting."""
    path.write_text(json.dumps({
        "labels": ["other", "prefer_less_waiting"], "ngram_range": [3, 3], "sublinear_tf": True,
        "vocabulary": {"gap": 0, "abc": 1}, "idf": [1.0, 1.0],
        "coef": [[-1.0, 1.0], [2.0, -1.0]], "intercept": [0.0, 0.0]}))


class LinearTests(unittest.TestCase):
    def test_plain_python_scorer(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model.json"
            tiny_model(path)
            model = linear.LinearModel(json.loads(path.read_text()))
        self.assertEqual(model("I hate gaps"), "prefer_less_waiting")
        self.assertEqual(model("abc"), "other")
        self.assertAlmostEqual(sum(model.probabilities("gap").values()), 1.0)

    def test_ngrams_pad_and_normalise(self):
        self.assertEqual(linear.ngrams("Ab", 1, 2), [" ", "a", "b", " ", " a", "ab", "b "])


class ClassifierTests(unittest.TestCase):
    def test_model_reply_is_read_as_a_label(self):
        self.assertEqual(parse_label("prefer_less_waiting"), "prefer_less_waiting")
        self.assertEqual(parse_label('{"label": "lunch"}'), "lunch")
        self.assertEqual(parse_label("I think it is max_daily_hours."), "max_daily_hours")
        self.assertEqual(parse_label("no idea"), "other")

    def test_constrained_ollama_classifier(self):
        with mock.patch("llm.ollama.chat", return_value='{"label": "max_days"}') as chat:
            self.assertEqual(classify.ollama_classifier("qwen2.5:7b")("一周最多三天"), "max_days")
        self.assertEqual(chat.call_args.kwargs["schema"]["properties"]["label"]["enum"][0], "blocked_time")

    def test_unknown_name_is_refused(self):
        with self.assertRaises(ValueError):
            classify.by_name("gpt")


class MetricTests(unittest.TestCase):
    def test_classification_scores(self):
        scores = classification(["lunch", "lunch", "other"], ["lunch", "other", "other"])
        self.assertAlmostEqual(scores["accuracy"], 2 / 3)
        self.assertAlmostEqual(scores["per_label"]["lunch"]["recall"], 0.5)
        self.assertEqual(scores["confusion"]["lunch"]["other"], 1)

    def test_field_accuracy_treats_missing_and_empty_alike(self):
        result = field_accuracy([{"cares": []}, {"max_days_per_week": 3}], [{}, {"max_days_per_week": 4}])
        self.assertEqual(result["cares"], 1.0)
        self.assertEqual(result["max_days_per_week"], 0.5)

    def test_joined_sentences_keep_their_clauses(self):
        rows = [{"text": f"clause {i}", "label": "other", "language": "en"} for i in range(9)]
        for sentence in joined_sentences(rows, count=3):
            self.assertEqual(sentence["sentence"], ", ".join(c["text"] for c in sentence["clauses"]))


if __name__ == "__main__":
    unittest.main()
