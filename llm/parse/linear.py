"""Character n-gram TF-IDF + a linear classifier, scored in plain Python.

Training happens in llm/parse/experiments.py with scikit-learn; it saves the vocabulary,
idf values and weights to JSON so the running app needs only the standard library.
The analyser below is the one scikit-learn is given, so both sides see the same features.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from llm.parse.text import normalize

MODEL_PATH = Path(__file__).resolve().parent / "output" / "linear_model.json"


def ngrams(text: str, low: int = 1, high: int = 4) -> list[str]:
    """Character n-grams of the normalised clause, with a space added at both ends."""
    padded = f" {' '.join(normalize(text).split())} "
    return [padded[i:i + n] for n in range(low, high + 1) for i in range(len(padded) - n + 1)]


class LinearModel:
    def __init__(self, data: dict):
        self.labels: list[str] = data["labels"]
        self.low, self.high = data["ngram_range"]
        self.sublinear = data.get("sublinear_tf", True)
        self.vocab: dict[str, int] = data["vocabulary"]
        self.idf: list[float] = data["idf"]
        self.coef: list[list[float]] = data["coef"]
        self.intercept: list[float] = data["intercept"]

    def scores(self, text: str) -> list[float]:
        counts: dict[int, int] = {}
        for gram in ngrams(text, self.low, self.high):
            if (index := self.vocab.get(gram)) is not None:
                counts[index] = counts.get(index, 0) + 1
        weights = {i: ((1 + math.log(c)) if self.sublinear else c) * self.idf[i] for i, c in counts.items()}
        norm = math.sqrt(sum(w * w for w in weights.values())) or 1.0
        return [b + sum(row[i] * w for i, w in weights.items()) / norm for row, b in zip(self.coef, self.intercept)]

    def probabilities(self, text: str) -> dict[str, float]:
        scores = self.scores(text)
        top = max(scores)
        exp = [math.exp(s - top) for s in scores]
        total = sum(exp)
        return {label: value / total for label, value in zip(self.labels, exp)}

    def __call__(self, text: str) -> str:
        scores = self.scores(text)
        return self.labels[scores.index(max(scores))]


@lru_cache(maxsize=1)
def load(path: str | Path = MODEL_PATH) -> LinearModel:
    return LinearModel(json.loads(Path(path).read_text()))
