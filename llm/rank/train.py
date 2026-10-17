"""Train and compare rankers on the teacher labels; write the chosen model to model.json.

SYNTHETIC: the training labels come from an LLM playing synthetic personas (llm/rank/label.py).
The test personas never appear in training (fixed split in personas.json).

Compared, on the 20 test personas:
- equal weights over days / waiting / early-late (z-scores within the student's list);
- the student's cares only (the placeholder rank());
- pairwise logistic regression on the 13 features, without and with student interaction terms;
- random forest and a small neural network on (x_A - x_B, student terms);
- Qwen judging directly, when llm/rank/direct.py has been run (single pass, no swap check).
Metrics: pairwise accuracy on the teacher's consistent non-tie answers, top-3 hit rate against
the teacher's round-robin order of each test persona's 8 candidates, and time per student.

    /usr/local/bin/python3 -m llm.rank.train --labels llm/rank/output/labels_v3_qwen2.5_14b.jsonl
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llm.rank import model as runtime  # noqa: E402
from llm.rank.features import NAMES  # noqa: E402
from llm.rank.metrics import membership, teacher_order  # noqa: E402
from llm.rank.personas import load as load_personas  # noqa: E402

OUT = ROOT / "llm" / "rank" / "output"
SEED = 2112
BASE = ("campus_days", "gap_h", "outside_h")
CARE_FEATURE = {"campus_days": "campus_days", "gap": "gap_h", "outside_hours": "outside_h"}


# ------------------------------------------------------------------ data
def load_rows(path: Path) -> list[dict]:
    personas = {p["id"]: p for p in load_personas()}
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        persona = personas[row["persona"]]
        row["prefs"] = {"cares": persona["conditions"]["cares"],
                        "preferred_hours": persona["conditions"].get("preferred_hours")}
        row["s"] = runtime.student_terms(row["prefs"])
        rows.append(row)
    return rows


def decided(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row["label"] in ("A", "B")]


def spec_from(rows: list[dict]) -> dict:
    """Centre and scale of each feature over the training candidates."""
    xs = [row[side] for row in rows for side in ("a_x", "b_x")]
    center = {n: float(np.mean([x[n] for x in xs])) for n in NAMES}
    scale = {n: float(np.std([x[n] for x in xs])) or 1.0 for n in NAMES}
    return {"features": list(NAMES), "student_terms": list(runtime.STUDENT_TERMS),
            "center": center, "scale": scale}


def z(x: dict, spec: dict) -> np.ndarray:
    return np.array([(x[n] - spec["center"][n]) / spec["scale"][n] for n in spec["features"]])


# ------------------------------------------------------------------ models
class SetBaseline:
    """Minus the sum of z-scores within the student's own list (the placeholder rank())."""

    def __init__(self, use_cares: bool):
        self.use_cares = use_cares
        self.name = "按 cares 打分（基准）" if use_cares else "等权打分"

    def fit(self, rows, spec):
        return self

    def keys(self, prefs):
        cares = [CARE_FEATURE[c] for c in prefs.get("cares") or ()] if self.use_cares else []
        return cares or list(BASE)

    def scores(self, xs, prefs, s, stats_from=None):
        keys = self.keys(prefs)
        base = stats_from or xs
        stats = {k: (np.mean([x[k] for x in base]), np.std([x[k] for x in base]) or 1.0) for k in keys}
        return [-sum((x[k] - stats[k][0]) / stats[k][1] for k in keys) for x in xs]

    def prob(self, xa, xb, prefs, s, context):
        """Compare A and B within the student's own list (z-scores depend on the list)."""
        pool = list(context) or [xa, xb]
        scores = self.scores(pool + [xa, xb], prefs, s, stats_from=pool)
        a, b = scores[-2:]
        return 0.5 if a == b else float(a > b)


class PairwiseLR:
    def __init__(self, interactions: bool, C: float = 1.0, use_focus: bool = True):
        self.interactions, self.C, self.use_focus = interactions, C, use_focus
        self.name = ("成对逻辑回归（只用课表特征）" if not interactions else
                     "成对逻辑回归 + 学生交叉项" if use_focus else "成对逻辑回归 + 交叉项（不看 cares 顺序）")

    def features(self, x, s):
        zx = z(x, self.spec)
        if not self.use_focus:      # which cares only, not which comes first
            s = [0.0, 0.0, 0.0] + list(s[3:])
        return np.concatenate([zx, np.outer(s, zx).ravel()]) if self.interactions else zx

    def fit(self, rows, spec):
        self.spec = spec
        d = np.array([self.features(r["a_x"], r["s"]) - self.features(r["b_x"], r["s"]) for r in rows])
        y = np.array([r["label"] == "A" for r in rows], dtype=int)
        X, Y = np.vstack([d, -d]), np.concatenate([y, 1 - y])
        self.lr = LogisticRegression(C=self.C, fit_intercept=False, max_iter=5000).fit(X, Y)
        self.w = self.lr.coef_[0]
        return self

    def utility(self, x, s):
        return float(self.features(x, s) @ self.w)

    def scores(self, xs, prefs, s):
        return [self.utility(x, s) for x in xs]

    def prob(self, xa, xb, prefs, s, context):
        return 1 / (1 + np.exp(-(self.utility(xa, s) - self.utility(xb, s))))

    def export(self) -> dict:
        n = len(self.spec["features"])
        weights = list(map(float, self.w)) + ([] if self.interactions else [0.0] * n * len(runtime.STUDENT_TERMS))
        return {**self.spec, "weights": weights, "C": self.C}


class PairClassifier:
    """A classifier on (z_A - z_B, student terms); antisymmetric by averaging both orders.
    Ranking a list uses each candidate's mean win probability against the others."""

    def __init__(self, kind: str, **params):
        self.kind, self.params = kind, params
        self.name = {"rf": "随机森林", "mlp": "小型神经网络"}[kind]

    def inputs(self, xa, xb, s):
        return np.concatenate([z(xa, self.spec) - z(xb, self.spec), s])

    def fit(self, rows, spec):
        self.spec = spec
        X = np.array([self.inputs(r["a_x"], r["b_x"], r["s"]) for r in rows] +
                     [self.inputs(r["b_x"], r["a_x"], r["s"]) for r in rows])
        y = np.array([r["label"] == "A" for r in rows] + [r["label"] == "B" for r in rows], dtype=int)
        if self.kind == "rf":
            self.clf = RandomForestClassifier(random_state=SEED, n_jobs=-1, **self.params)
        else:
            self.clf = MLPClassifier(random_state=SEED, max_iter=2000, early_stopping=False, **self.params)
        self.clf.fit(X, y)
        return self

    def prob(self, xa, xb, prefs, s, context=()):
        both = self.clf.predict_proba(np.array([self.inputs(xa, xb, s), self.inputs(xb, xa, s)]))[:, 1]
        return float((both[0] + 1 - both[1]) / 2)

    def scores(self, xs, prefs, s):
        pairs = [(i, j) for i in range(len(xs)) for j in range(len(xs)) if i != j]
        if not pairs:
            return [0.0] * len(xs)
        p = self.clf.predict_proba(np.array([self.inputs(xs[i], xs[j], s) for i, j in pairs]))[:, 1]
        wins = defaultdict(float)
        for (i, j), value in zip(pairs, p):
            wins[i] += value / 2
            wins[j] += (1 - value) / 2
        return [wins[i] for i in range(len(xs))]


# ------------------------------------------------------------------ evaluation
def pairwise_accuracy(model, rows, sets) -> tuple[float, dict]:
    hits = defaultdict(list)
    for r in decided(rows):
        context = [c["x"] for c in sets.get(r["persona"], [])]
        p = model.prob(r["a_x"], r["b_x"], r["prefs"], r["s"], context)
        hits[r["persona"]].append(0.5 if p == 0.5 else float((p > 0.5) == (r["label"] == "A")))
    flat = [h for values in hits.values() for h in values]
    return (float(np.mean(flat)) if flat else float("nan")), hits


def top3_metrics(model, test_rows, sets, personas) -> dict:
    hit, best, ceiling, per = [], [], [], {}
    by_persona = defaultdict(list)
    for r in test_rows:
        by_persona[r["persona"]].append(r)
    for pid, rows in by_persona.items():
        candidates = sets[pid]
        ids = [c["candidate_id"] for c in candidates]
        points = teacher_order(rows, ids)
        share = membership(points)
        top = max(points.values())
        winners = [i for i, v in points.items() if v == top]
        prefs = {"cares": personas[pid]["conditions"]["cares"],
                 "preferred_hours": personas[pid]["conditions"].get("preferred_hours")}
        scores = model.scores([c["x"] for c in candidates], prefs, runtime.student_terms(prefs))
        picked = [ids[i] for i in sorted(range(len(ids)), key=lambda i: (-scores[i], ids[i]))[:3]]
        hit.append(sum(share[i] for i in picked) / 3)
        ceiling.append(sum(sorted(share.values(), reverse=True)[:3]) / 3)   # a perfect guess of the teacher
        best.append(sum(i in picked for i in winners) / len(winners))
        per[pid] = round(hit[-1], 3)
    return {"top3_hit": float(np.mean(hit)), "best_in_top3": float(np.mean(best)),
            "top3_ceiling": float(np.mean(ceiling)), "per_persona": per}


def bootstrap(hits: dict[str, list[float]], rounds: int = 2000) -> tuple[float, float]:
    """95% interval for pairwise accuracy, resampling test personas."""
    rng = random.Random(SEED)
    keys = list(hits)
    values = []
    for _ in range(rounds):
        sample = [h for k in (rng.choice(keys) for _ in keys) for h in hits[k]]
        values.append(np.mean(sample))
    return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))


def timing(model, sets, personas, repeats: int = 5) -> float:
    """Milliseconds to score one student's list (features already computed)."""
    started, count = time.perf_counter(), 0
    for _ in range(repeats):
        for pid, candidates in sets.items():
            prefs = {"cares": personas[pid]["conditions"]["cares"],
                     "preferred_hours": personas[pid]["conditions"].get("preferred_hours")}
            model.scores([c["x"] for c in candidates], prefs, runtime.student_terms(prefs))
            count += 1
    return (time.perf_counter() - started) / count * 1000


def choose(make, grid: list[dict], rows: list[dict], folds: int = 5) -> tuple[dict, float]:
    """Pick hyper-parameters by cross-validation over training personas (grouped by persona)."""
    personas = sorted({r["persona"] for r in rows})
    random.Random(SEED).shuffle(personas)
    fold_of = {p: i % folds for i, p in enumerate(personas)}
    best = (None, -1.0)
    for params in grid:
        accuracies = []
        for k in range(folds):
            train = [r for r in rows if fold_of[r["persona"]] != k]
            held = [r for r in rows if fold_of[r["persona"]] == k]
            spec = spec_from(train)
            accuracies.append(pairwise_accuracy(make(**params).fit(decided(train), spec), held, {})[0])
        score = float(np.mean(accuracies))
        if score > best[1]:
            best = (params, score)
    return best


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--labels", required=True)
    parser.add_argument("--direct", nargs="*", default=[], help="direct.py outputs to include")
    parser.add_argument("--no-export", action="store_true")
    args = parser.parse_args()
    rows = load_rows(Path(args.labels))
    personas = {p["id"]: p for p in load_personas()}
    sets = {pid: entries for pid, entries in
            json.loads((OUT / "candidate_sets.json").read_text(encoding="utf-8"))["sets"].items()}
    train = [r for r in rows if r["split"] == "train"]
    test = [r for r in rows if r["split"] == "test"]
    spec = spec_from(train)
    print(f"train: {len(decided(train))} decided pairs from {len({r['persona'] for r in train})} personas; "
          f"test: {len(decided(test))} decided of {len(test)} pairs from {len({r['persona'] for r in test})} personas")

    candidates = [
        (lambda **p: SetBaseline(False), [{}]),
        (lambda **p: SetBaseline(True), [{}]),
        (lambda **p: PairwiseLR(False, **p), [{"C": c} for c in (0.01, 0.03, 0.1, 0.3, 1, 3)]),
        (lambda **p: PairwiseLR(True, **p), [{"C": c} for c in (0.01, 0.03, 0.1, 0.3, 1, 3)]),
        (lambda **p: PairwiseLR(True, use_focus=False, **p), [{"C": c} for c in (0.01, 0.03, 0.1, 0.3, 1, 3)]),
        (lambda **p: PairClassifier("rf", **p),
         [{"n_estimators": 300, "max_depth": d, "min_samples_leaf": m} for d in (4, 8, None) for m in (1, 5)]),
        (lambda **p: PairClassifier("mlp", **p),
         [{"hidden_layer_sizes": h, "alpha": a} for h in ((16,), (32, 16)) for a in (1e-3, 1e-2, 1e-1)]),
    ]
    results, fitted = [], {}
    for make, grid in candidates:
        params, cv = choose(make, grid, train) if len(grid) > 1 else (grid[0], None)
        model = make(**params).fit(decided(train), spec)
        accuracy, hits = pairwise_accuracy(model, test, sets)
        low, high = bootstrap(hits)
        top = top3_metrics(model, test, sets, personas)
        results.append({"model": model.name, "params": params, "cv_accuracy": cv, "pairwise_accuracy": accuracy,
                        "ci95": [low, high], "top3_hit": top["top3_hit"], "top3_ceiling": top["top3_ceiling"],
                        "best_in_top3": top["best_in_top3"],
                        "ms_per_student": timing(model, {k: sets[k] for k in sorted(sets)[:20]}, personas),
                        "per_persona_top3": top["per_persona"]})
        fitted[model.name] = model
        print(f"{model.name:22s} cv={cv if cv is None else round(cv, 3)} acc={accuracy:.3f} [{low:.3f},{high:.3f}] "
              f"top3={top['top3_hit']:.3f}/{top['top3_ceiling']:.3f} best@3={top['best_in_top3']:.3f} {params}",
              flush=True)
    for path in args.direct:
        results.append(direct_result(Path(path), test))
    random_top3 = 3 / 8
    report = {"note": "合成数据：训练和测试标签都来自大模型扮演的合成画像，不是真实学生。",
              "labels": args.labels, "train_pairs": len(decided(train)), "test_pairs": len(decided(test)),
              "test_personas": len({r["persona"] for r in test}), "random_baseline": {
                  "pairwise_accuracy": 0.5, "top3_hit": random_top3}, "results": results}
    (OUT / "model_comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if not args.no_export:
        best = fitted["成对逻辑回归 + 学生交叉项"]
        export = {**best.export(), "trained_on": args.labels, "synthetic_labels": True,
                  "note": "成对逻辑回归权重；训练标签是合成的（大模型扮演合成画像）。由 llm/rank/train.py 生成。"}
        runtime.PATH.write_text(json.dumps(export, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {runtime.PATH.relative_to(ROOT)}")
    return 0


def direct_result(path: Path, test: list[dict]) -> dict:
    """Accuracy of a single-pass LLM judgement (direct.py output) on the same test pairs."""
    answers = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    pairwise = {(a["persona"], a["a_id"], a["b_id"]): a for a in answers if a["kind"] == "pairwise"}
    labels = {(r["persona"], r["a_id"], r["b_id"]): r["label"] for r in decided(test)}
    scored = [float(pairwise[k]["choice"] == v) for k, v in labels.items() if k in pairwise]
    listwise = [a for a in answers if a["kind"] == "listwise"]
    seconds = [a["seconds"] for a in answers]
    result = {"model": f"千问直接判断（{answers[0]['model']}）", "pairwise_accuracy": float(np.mean(scored)) if scored else None,
              "pairs_scored": len(scored), "seconds_per_call": float(np.mean(seconds)) if seconds else None}
    if listwise:
        result["top3_hit"] = float(np.mean([a["top3_hit"] for a in listwise]))
        result["best_in_top3"] = float(np.mean([a["best_in_top3"] for a in listwise]))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
