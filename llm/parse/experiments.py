"""Train the character n-gram models with scikit-learn and save their predictions.

    /usr/local/bin/python3 -m llm.parse.experiments

Models: TF-IDF + logistic regression, TF-IDF + naive Bayes, TF-IDF + a small neural network.
Hyper-parameters are picked on the SYNTHETIC validation split only (the test set is
never read here). The chosen logistic regression is refitted on train + val and exported to
output/linear_model.json, which llm/parse/linear.py scores in plain Python at run time.
Predictions go to output/predictions/ for llm/parse/evaluate.py to score with the others.
"""
from __future__ import annotations

import itertools
import json
import pickle
import platform
import time

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import ComplementNB
from sklearn.neural_network import MLPClassifier

from llm.parse.evaluate import OUTPUT, PREDICTIONS, SEED, data_sets, synthetic, texts_needed
from llm.parse.linear import MODEL_PATH, load, ngrams

GRIDS = {
    "tfidf+logreg": (LogisticRegression, [{"C": c, "max_iter": 3000} for c in (1, 3, 10, 30)]),
    "tfidf+naive_bayes": (ComplementNB, [{"alpha": a} for a in (0.03, 0.1, 0.3, 1.0)]),
    "tfidf+mlp": (MLPClassifier, [{"hidden_layer_sizes": (h,), "alpha": a, "max_iter": 300, "random_state": SEED}
                                  for h, a in itertools.product((64, 256), (1e-4, 1e-2))]),
}
NGRAMS = ((1, 3), (1, 4), (2, 5))
MIN_DF = (1, 2)


def vectorizer(low: int, high: int, min_df: int) -> TfidfVectorizer:
    return TfidfVectorizer(analyzer=lambda text: ngrams(text, low, high), sublinear_tf=True, min_df=min_df)


def search(name, model_class, grid, train, val):
    """Best (val accuracy, settings) over n-gram range, min_df and the model's own grid."""
    best = None
    for (low, high), min_df in itertools.product(NGRAMS, MIN_DF):
        vec = vectorizer(low, high, min_df)
        x_train = vec.fit_transform([r["text"] for r in train])
        x_val = vec.transform([r["text"] for r in val])
        for params in grid:
            model = model_class(**params).fit(x_train, [r["label"] for r in train])
            accuracy = (model.predict(x_val) == [r["label"] for r in val]).mean()
            if best is None or accuracy > best[0]:
                best = (accuracy, {"ngram_range": (low, high), "min_df": min_df, **params})
    print(f"{name}: best val accuracy {best[0]:.3f} with {best[1]}")
    return best


def export_linear(vec: TfidfVectorizer, model: LogisticRegression, settings: dict) -> None:
    vocab = {gram: int(index) for gram, index in vec.vocabulary_.items()}
    data = {
        "note": "TF-IDF character n-grams + logistic regression, trained on SYNTHETIC clauses "
                "(llm/parse/output/synthetic_clauses.jsonl). Scored by llm/parse/linear.py.",
        "labels": [str(label) for label in model.classes_],
        "ngram_range": list(settings["ngram_range"]), "sublinear_tf": True,
        "settings": {key: value for key, value in settings.items() if key != "ngram_range"},
        "vocabulary": vocab,
        "idf": [round(float(v), 5) for v in vec.idf_],
        "coef": [[round(float(v), 5) for v in row] for row in model.coef_],
        "intercept": [round(float(v), 5) for v in model.intercept_],
        "date": time.strftime("%Y-%m-%d"),
    }
    MODEL_PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def save_predictions(name: str, predict_one, texts: list[str], size_mb: float, note: str) -> None:
    predict_one(texts[0])
    predictions = {}
    for text in texts:
        started = time.perf_counter()
        label = predict_one(text)
        predictions[text] = {"label": str(label), "ms": round((time.perf_counter() - started) * 1000, 2)}
    PREDICTIONS.mkdir(parents=True, exist_ok=True)
    (PREDICTIONS / f"{name}.json").write_text(json.dumps(
        {"model": name, "machine": f"{platform.machine()} Mac CPU", "size_mb": round(size_mb, 2), "note": note,
         "predictions": predictions}, ensure_ascii=False, indent=1))


def main() -> int:
    train, val = synthetic("train"), synthetic("val")
    texts = texts_needed(data_sets(with_test=False))
    summary = {}
    for name, (model_class, grid) in GRIDS.items():
        accuracy, settings = search(name, model_class, grid, train, val)
        params = {k: v for k, v in settings.items() if k not in ("ngram_range", "min_df")}
        vec = vectorizer(*settings["ngram_range"], settings["min_df"])
        model = model_class(**params).fit(vec.fit_transform([r["text"] for r in train]), [r["label"] for r in train])
        size = len(pickle.dumps((vec.vocabulary_, vec.idf_, model))) / 1e6
        note = f"n-gram {settings['ngram_range']}, min_df {settings['min_df']}, " + \
               ", ".join(f"{k}={v}" for k, v in params.items() if k not in ("max_iter", "random_state"))
        if name == "tfidf+logreg":
            export_linear(vec, model, settings)
            runtime = load.__wrapped__(MODEL_PATH)
            agree = sum(runtime(t) == p for t, p in zip(texts, model.predict(vec.transform(texts))))
            print(f"  plain-Python scorer agrees with scikit-learn on {agree}/{len(texts)} texts")
            save_predictions("linear", runtime, texts, MODEL_PATH.stat().st_size / 1e6,
                             note + " (plain-Python scorer, trained on train only)")
            # The run-time model: same settings, refitted on train + val.
            both = train + val
            vec_all = vectorizer(*settings["ngram_range"], settings["min_df"])
            final = model_class(**params).fit(vec_all.fit_transform([r["text"] for r in both]),
                                              [r["label"] for r in both])
            export_linear(vec_all, final, settings)
        else:
            save_predictions(name, lambda t: model.predict(vec.transform([t]))[0], texts, size, note)
        summary[name] = {"val_accuracy": round(float(accuracy), 4), "settings": {
            k: (list(v) if isinstance(v, tuple) else v) for k, v in settings.items()}}
    (OUTPUT / "experiments_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
