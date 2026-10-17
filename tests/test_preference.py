import math
import random
import tempfile
import unittest
from itertools import combinations
from pathlib import Path

from uniplan.preference import (AXES, design_study, evaluate_design, farthest_point_sample,
                                fit_pairwise_logistic, fit_scaled, interpret, pair_accuracy,
                                pool_spread, rank_by_utility, tradeoff_strength, vector,
                                weight_prior, weighted_margin, learned_margin)
from uniplan.ranking import EQUAL_WEIGHTS
from uniplan.store import ProfileStore


def features(gap, days, outside):
    return {"gap_min": gap, "campus_days": days, "outside_min": outside}


def synthetic_pool(n=40, seed=3):
    rng = random.Random(seed)
    pool, seen = [], set()
    while len(pool) < n:
        item = features(rng.randrange(0, 600, 15), rng.randrange(10, 50) / 10, rng.randrange(0, 240, 15))
        key = tuple(item.values())
        if key in seen:
            continue
        seen.add(key)
        pool.append({"key": key, "features": item, "count": 1,
                     "candidate_id": f"c{len(pool):03d}", "option_ids": (f"o{len(pool)}",)})
    return pool


def answers_for(design, beta):
    """A perfectly consistent student with utility beta . x."""
    answers = {}
    for pair in design.pairs:
        a, b = design.schedules[pair.left]["x"], design.schedules[pair.right]["x"]
        margin = sum(w * (x - y) for w, x, y in zip(beta, a, b))
        answers[pair.pair_id] = "A" if margin > 0 else "B"
    return answers


class SamplingTests(unittest.TestCase):
    def test_farthest_point_sample_is_distinct_seeded_and_spreads_out(self):
        vectors = [vector(entry["features"]) for entry in synthetic_pool()]
        first = farthest_point_sample(vectors, 10, random.Random(7))
        self.assertEqual(first, farthest_point_sample(vectors, 10, random.Random(7)))
        self.assertEqual(len(set(first)), 10)
        self.assertEqual(farthest_point_sample(vectors[:4], 10, random.Random(7)), [0, 1, 2, 3])
        # Max-min spacing beats a random draw of the same size.
        def spacing(indices):
            return min(math.dist(vectors[i], vectors[j]) for i, j in combinations(indices, 2))
        random_draw = random.Random(1).sample(range(len(vectors)), 10)
        self.assertGreater(spacing(first), spacing(random_draw))

    def test_design_splits_before_pairing_and_keeps_counts(self):
        design = design_study(synthetic_pool(), seed=11)
        self.assertTrue(design.complete)
        splits = [item["split"] for item in design.schedules]
        self.assertEqual((splits.count("train"), splits.count("test")), (6, 4))
        train = [pair for pair in design.pairs if pair.split == "train"]
        test = [pair for pair in design.pairs if pair.split == "test"]
        self.assertEqual((len(train), len(test)), (12, 4))
        for pair in design.pairs:
            self.assertEqual({design.schedules[pair.left]["split"],
                              design.schedules[pair.right]["split"]}, {pair.split})
        unordered = {frozenset((pair.left, pair.right)) for pair in design.pairs}
        self.assertEqual(len(unordered), 16)
        # Neutral display order: position never reveals the split.
        ids = [item["candidate_id"] for item in design.schedules]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual([pair.pair_id for pair in design.pairs], list(range(16)))

    def test_training_pairs_prefer_tradeoffs(self):
        design = design_study(synthetic_pool(), seed=5)
        train_ids = [i for i, item in enumerate(design.schedules) if item["split"] == "train"]
        chosen = {frozenset((p.left, p.right)) for p in design.pairs if p.split == "train"}
        skipped = [pair for pair in combinations(train_ids, 2) if frozenset(pair) not in chosen]
        weakest_chosen = min(tradeoff_strength(design.schedules[p.left]["x"], design.schedules[p.right]["x"])
                             for p in design.pairs if p.split == "train")
        for a, b in skipped:
            self.assertLessEqual(tradeoff_strength(design.schedules[a]["x"], design.schedules[b]["x"]),
                                 weakest_chosen + 1e-12)

    def test_small_pool_scales_down_and_tiny_pool_has_no_study(self):
        self.assertIsNone(design_study(synthetic_pool(4), seed=1))
        design = design_study(synthetic_pool(7), seed=1)
        self.assertFalse(design.complete)
        splits = [item["split"] for item in design.schedules]
        self.assertGreaterEqual(splits.count("train"), 3)
        self.assertGreaterEqual(splits.count("test"), 2)
        with self.assertRaises(ValueError):
            design_study(synthetic_pool(), seed=1, pair_strategy="best")


class ModelTests(unittest.TestCase):
    def test_logistic_fit_is_optimal_and_order_symmetric(self):
        rng = random.Random(4)
        diffs = [tuple(rng.uniform(-1, 1) for _ in AXES) for _ in range(12)]
        labels = [rng.randrange(2) for _ in diffs]
        beta = fit_pairwise_logistic(diffs, labels)
        rows = list(zip(diffs, labels)) + [(tuple(-v for v in d), 1 - y) for d, y in zip(diffs, labels)]
        grad = list(beta)
        for d, y in rows:
            p = 1 / (1 + math.exp(-sum(b * v for b, v in zip(beta, d))))
            grad = [g + (p - y) * v for g, v in zip(grad, d)]
        self.assertLess(max(abs(g) for g in grad), 1e-9)
        flipped = fit_pairwise_logistic([tuple(-v for v in d) for d in diffs], [1 - y for y in labels])
        for a, b in zip(beta, flipped):
            self.assertAlmostEqual(a, b, places=9)
        with self.assertRaises(ValueError):
            fit_pairwise_logistic(diffs, [2] * len(diffs))

    def test_prior_is_the_answer_without_evidence(self):
        prior = weight_prior(EQUAL_WEIGHTS, 10)
        self.assertEqual(fit_pairwise_logistic([], [], prior=prior), prior)
        # Scaling the fit space keeps the returned beta in raw x units.
        self.assertEqual(fit_scaled([], (2.0, 0.5, 4.0), prior=prior), prior)

    def test_accuracy_excludes_student_ties_and_halves_predicted_ties(self):
        a, b = (0.0, 0.2, 0.0), (0.0, 0.4, 0.0)
        result = pair_accuracy(weighted_margin(EQUAL_WEIGHTS), [(a, b, "A"), (b, a, "A"), (a, b, "tie")])
        self.assertEqual(result, {"accuracy": 0.5, "scored": 2, "ties": 1})
        flat = pair_accuracy(learned_margin((0.0, 0.0, 0.0)), [(a, b, "A")])
        self.assertEqual(flat["accuracy"], 0.5)

    def test_interpretation_and_implied_weights(self):
        meaning = interpret((-2.0, -1.0, -1.0))
        self.assertAlmostEqual(meaning["implied_weights"]["gap"], 0.5)
        self.assertEqual([axis["direction"] for axis in meaning["axes"]], ["less"] * 3)
        likes_gaps = interpret((1.0, -1.0, 0.0))
        self.assertIsNone(likes_gaps["implied_weights"])
        self.assertEqual(likes_gaps["axes"][0]["direction"], "more")
        self.assertFalse(interpret((0.0, 0.0, 0.0))["informative"])

    def test_learned_model_recovers_a_consistent_student(self):
        pool = synthetic_pool()
        truth = (0.0, -3.0, -0.2)  # cares almost only about campus days
        design = design_study(pool, seed=9)
        report = evaluate_design(design, answers_for(design, truth), EQUAL_WEIGHTS,
                                 scale=pool_spread(pool), prior=weight_prior(EQUAL_WEIGHTS, 10))
        self.assertEqual(report["status"], "learned")
        beta = report["beta"]
        self.assertLess(beta[1], 0)
        self.assertEqual(max(range(3), key=lambda i: abs(beta[i])), 1)
        def true_utility(entry):
            return sum(t * v for t, v in zip(truth, vector(entry["features"])))
        best = max(true_utility(entry) for entry in pool)
        average = sum(true_utility(entry) for entry in pool) / len(pool)
        top = rank_by_utility(pool, beta, limit=1)[0]
        # The first recommendation recovers most of the gap between an average pick and the best.
        self.assertLess(best - true_utility(top), 0.2 * (best - average))

    def test_too_few_training_answers_fall_back(self):
        design = design_study(synthetic_pool(), seed=2)
        answers = {pair.pair_id: "tie" for pair in design.pairs}
        self.assertEqual(evaluate_design(design, answers, EQUAL_WEIGHTS)["status"], "insufficient")


class StoreTests(unittest.TestCase):
    def test_choices_and_outcomes_need_consent_and_withdraw_together(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProfileStore(Path(temp) / "private/db.sqlite3")
            code, study = "a" * 32, "b" * 32
            self.assertFalse(store.record_outcome(code, "accepted", {}, 10))
            store.save({"profile_id": code}, None)
            row = {"pair_index": 0, "split": "train", "candidate_a": "x", "candidate_b": "y",
                   "x_a": [0.1, 0.2, 0.3], "x_b": [0.3, 0.2, 0.1], "choice": "A"}
            store.save_choices(code, study, 7, EQUAL_WEIGHTS, [row], [1.0, 1.0, 1.0])
            store.save_choices(code, study, 7, EQUAL_WEIGHTS, [row], [1.0, 1.0, 1.0])
            self.assertEqual(len(store.load_choices()), 1)
            self.assertTrue(store.record_outcome(code, "accepted", {"rank": 1}, 1234))
            self.assertFalse(store.record_outcome(code, "unknown", {}, None))
            self.assertEqual(store.load_outcomes()[0]["detail"], {"rank": 1})
            self.assertTrue(store.withdraw(code))
            self.assertEqual((store.load_choices(), store.load_outcomes()), ([], []))
            self.assertFalse(store.withdraw(code))


if __name__ == "__main__":
    unittest.main()
