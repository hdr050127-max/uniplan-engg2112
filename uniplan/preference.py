"""Module four: learn one student's timetable preferences from comparisons.

This implements proposal step 3. Hard constraints have already removed every
infeasible schedule; nothing here can bring one back.

1. Farthest-point sampling picks up to ten feasible schedules with distinct
   normalised feature vectors x = (G/300, D/5, O/120).
2. A seeded split reserves six for training and four for testing *before*
   pairing, so no test schedule appears in a training comparison.
3. Twelve training pairs favour opposing trade-offs (neither schedule is at
   least as good on every feature); four test pairs are sampled uniformly.
   Pair order and left/right placement are randomised.
4. A per-student L2-regularised logistic model without intercept,
   P(A preferred) = sigmoid(beta . (x_A - x_B)) with C = 1, is fitted on
   mirrored training pairs. Candidates are ranked by utility beta . x.
5. Held-out pair accuracy is compared with both rule baselines and chance.
   A predicted tie earns half credit; pairs the student called a tie are
   reported and excluded from binary accuracy.

The model is deliberately tiny: three coefficients a student can read.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Callable, Iterable, Sequence

from .ranking import EQUAL_WEIGHTS, scaled_features


AXES = ("gap", "campus_days", "outside_hours")
Vector = tuple[float, float, float]
Comparison = tuple[Vector, Vector, str]  # (x_A, x_B, "A" | "B" | "tie")

N_SCHEDULES = 10
N_TRAIN = 6
N_TRAIN_PAIRS = 12
N_TEST_PAIRS = 4
MIN_SCHEDULES = 5
MIN_TRAIN_RESPONSES = 6
REGULARISATION_C = 1.0
PRIOR_STRENGTH = 10.0
TIE_EPS = 1e-12

# Deviation from the proposal, chosen on synthetic students before any pilot
# data (scripts/simulate_preference_learning.py): differences are divided by
# the pool's per-feature spread and shrunk toward equal weights rather than
# toward zero. The stored raw choices let the proposal model be refitted.
MODEL_SPEC = {"standardise": True, "c": REGULARISATION_C,
              "prior": "equal_weights", "prior_strength": PRIOR_STRENGTH}


def vector(features: dict[str, float]) -> Vector:
    scaled = scaled_features(features)
    return tuple(scaled[axis] for axis in AXES)  # type: ignore[return-value]


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _sub(a: Sequence[float], b: Sequence[float]) -> Vector:
    return tuple(x - y for x, y in zip(a, b))  # type: ignore[return-value]


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def farthest_point_sample(vectors: Sequence[Vector], k: int, rng: random.Random) -> list[int]:
    """Greedy max-min selection from a seeded start. Vectors must be distinct."""
    n = len(vectors)
    if k >= n:
        return list(range(n))
    chosen = [rng.randrange(n)]
    nearest = [_distance(item, vectors[chosen[0]]) for item in vectors]
    while len(chosen) < k:
        # Ties go to the lower index so the sample depends only on the seed.
        following = max(range(n), key=lambda index: (nearest[index], -index))
        chosen.append(following)
        for index, item in enumerate(vectors):
            nearest[index] = min(nearest[index], _distance(item, vectors[following]))
    return chosen


def tradeoff_strength(a: Vector, b: Vector, eps: float = 1e-9) -> float:
    """How much each schedule wins somewhere; 0 when one is never worse."""
    diff = _sub(a, b)
    gain = sum(value for value in diff if value > eps)
    loss = -sum(value for value in diff if value < -eps)
    return min(gain, loss)


@dataclass(frozen=True)
class PairSpec:
    pair_id: int
    left: int  # index into StudyDesign.schedules; shown as A
    right: int  # shown as B
    split: str  # "train" or "test"


@dataclass(frozen=True)
class StudyDesign:
    seed: int
    schedules: tuple[dict[str, Any], ...]  # pool entries plus "x" and "split"
    pairs: tuple[PairSpec, ...]  # display order
    complete: bool  # the full 10 / 6+4 / 12+4 design was reached


def design_study(
    pool: Sequence[dict[str, Any]], seed: int, *,
    n_schedules: int = N_SCHEDULES, n_train: int = N_TRAIN,
    n_train_pairs: int = N_TRAIN_PAIRS, n_test_pairs: int = N_TEST_PAIRS,
    min_schedules: int = MIN_SCHEDULES, pair_strategy: str = "tradeoff",
) -> StudyDesign | None:
    """Sample, split before pairing, then pair. None if too few distinct schedules.

    ``pair_strategy="random"`` drops the trade-off priority; it exists so the
    simulation script can measure what that priority buys.
    """
    if pair_strategy not in {"tradeoff", "random"}:
        raise ValueError("pair_strategy must be 'tradeoff' or 'random'")
    if len(pool) < min_schedules:
        return None
    rng = random.Random(seed)
    # Sort first so the design does not depend on search order.
    ordered = sorted(pool, key=lambda entry: entry["candidate_id"])
    vectors = [vector(entry["features"]) for entry in ordered]
    picked = farthest_point_sample(vectors, n_schedules, rng)
    rng.shuffle(picked)
    count = len(picked)
    train_count = n_train if count >= n_schedules else round(count * n_train / n_schedules)
    train_count = max(3, min(train_count, count - 2))
    splits = ["train"] * train_count + ["test"] * (count - train_count)
    # Present schedules in a neutral order so position never reveals the split.
    schedules = tuple(sorted(({**ordered[index], "x": vectors[index], "split": split}
                              for index, split in zip(picked, splits)),
                             key=lambda item: item["candidate_id"]))

    train_ids = [i for i, item in enumerate(schedules) if item["split"] == "train"]
    test_ids = [i for i, item in enumerate(schedules) if item["split"] == "test"]
    if pair_strategy == "random":
        train_pool = list(combinations(train_ids, 2))
        rng.shuffle(train_pool)
    else:
        train_pool = sorted(combinations(train_ids, 2), key=lambda pair: (
            tradeoff_strength(schedules[pair[0]]["x"], schedules[pair[1]]["x"]) <= 0,
            -tradeoff_strength(schedules[pair[0]]["x"], schedules[pair[1]]["x"]),
            rng.random(),
        ))
    train_pairs = train_pool[:n_train_pairs]
    test_pool = list(combinations(test_ids, 2))
    test_pairs = rng.sample(test_pool, min(n_test_pairs, len(test_pool)))
    raw = [(a, b, "train") for a, b in train_pairs] + [(a, b, "test") for a, b in test_pairs]
    rng.shuffle(raw)
    pairs = []
    for pair_id, (a, b, split) in enumerate(raw):
        if rng.random() < 0.5:
            a, b = b, a
        pairs.append(PairSpec(pair_id, a, b, split))
    complete = (count == n_schedules and len(train_pairs) == n_train_pairs and
                len(test_pairs) == n_test_pairs)
    return StudyDesign(seed, schedules, tuple(pairs), complete)


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    exp_z = math.exp(z)
    return exp_z / (1 + exp_z)


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting for the 3x3 Newton step."""
    n = len(rhs)
    aug = [row[:] + [value] for row, value in zip(matrix, rhs)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(aug[row][col]))
        aug[col], aug[pivot] = aug[pivot], aug[col]
        for row in range(col + 1, n):
            factor = aug[row][col] / aug[col][col]
            for k in range(col, n + 1):
                aug[row][k] -= factor * aug[col][k]
    solution = [0.0] * n
    for row in reversed(range(n)):
        solution[row] = (aug[row][n] - sum(aug[row][k] * solution[k]
                                           for k in range(row + 1, n))) / aug[row][row]
    return solution


def fit_pairwise_logistic(
    diffs: Sequence[Sequence[float]], labels: Sequence[int], *,
    c: float = REGULARISATION_C, max_iter: int = 100, tol: float = 1e-10,
    prior: Sequence[float] | None = None,
) -> Vector:
    """Minimise 0.5|b - prior|^2 + C * logloss on mirrored pairs, without intercept.

    Mirroring (-d, 1-y) makes the fit independent of which schedule was shown
    first. With no prior this matches scikit-learn's LogisticRegression(C=1,
    fit_intercept=False). A prior moves the shrinkage target from "no
    preference" to a starting belief, e.g. the student's typed weights, so a
    few comparisons refine it instead of starting from nothing. Newton's
    method converges because the L2 term keeps the Hessian positive definite.
    """
    if len(diffs) != len(labels):
        raise ValueError("diffs and labels must have the same length")
    if any(label not in (0, 1) for label in labels):
        raise ValueError("labels must be 0 or 1")
    rows = [(tuple(d), y) for d, y in zip(diffs, labels)]
    rows += [(tuple(-value for value in d), 1 - y) for d, y in rows]
    dim = len(AXES)
    centre = list(prior) if prior is not None else [0.0] * dim

    def loss(b: Sequence[float]) -> float:
        total = 0.5 * sum((v - m) ** 2 for v, m in zip(b, centre))
        for d, y in rows:
            z = _dot(b, d)
            # log(1 + e^z) - y z, computed stably.
            total += c * ((max(z, 0) + math.log1p(math.exp(-abs(z)))) - y * z)
        return total

    beta = centre[:]
    current = loss(beta)
    for _ in range(max_iter):
        grad = [b - m for b, m in zip(beta, centre)]
        hess = [[1.0 if i == j else 0.0 for j in range(dim)] for i in range(dim)]
        for d, y in rows:
            p = _sigmoid(_dot(beta, d))
            for i in range(dim):
                grad[i] += c * (p - y) * d[i]
                for j in range(dim):
                    hess[i][j] += c * p * (1 - p) * d[i] * d[j]
        step = _solve(hess, grad)
        # Halve the Newton step until the loss does not increase.
        scale = 1.0
        while True:
            trial = [b - scale * s for b, s in zip(beta, step)]
            value = loss(trial)
            if value <= current + 1e-12 or scale < 1e-8:
                break
            scale /= 2
        moved = max(abs(scale * s) for s in step)
        beta, current = trial, value
        if moved < tol:
            break
    return tuple(beta)  # type: ignore[return-value]


def preference_probability(beta: Vector, a: Vector, b: Vector) -> float:
    return _sigmoid(_dot(beta, _sub(a, b)))


Margin = Callable[[Vector, Vector], float]


def learned_margin(beta: Vector) -> Margin:
    """Positive when the model prefers A (higher utility beta . x)."""
    return lambda a, b: _dot(beta, _sub(a, b))


def weighted_margin(weights: dict[str, float]) -> Margin:
    """Positive when A has the lower weighted rule score (the baseline's choice)."""
    w = tuple(weights[axis] for axis in AXES)
    return lambda a, b: _dot(w, _sub(b, a))


def pair_accuracy(margin: Margin, comparisons: Iterable[Comparison]) -> dict[str, Any]:
    """Binary accuracy; predicted ties earn half credit, student ties are excluded."""
    credit, scored, ties = 0.0, 0, 0
    for a, b, choice in comparisons:
        if choice == "tie":
            ties += 1
            continue
        scored += 1
        value = margin(a, b)
        if abs(value) < TIE_EPS:
            credit += 0.5
        elif (value > 0) == (choice == "A"):
            credit += 1
    return {"accuracy": credit / scored if scored else None, "scored": scored, "ties": ties}


def interpret(beta: Vector) -> dict[str, Any]:
    """Readable coefficients: share of influence, direction and implied weights.

    Negative beta means the student prefers less of that feature (all three are
    costs in the rule baseline). Implied weights exist only when every
    coefficient points that way, so they compare directly with typed weights.
    """
    total = sum(abs(value) for value in beta)
    items = [{
        "axis": axis,
        "coefficient": value,
        "share": abs(value) / total if total > 0 else 0.0,
        "direction": "less" if value < -TIE_EPS else "more" if value > TIE_EPS else "neutral",
    } for axis, value in zip(AXES, beta)]
    implied = ({axis: -value / total for axis, value in zip(AXES, beta)}
               if total > 0 and all(value <= TIE_EPS for value in beta) else None)
    return {"informative": total > TIE_EPS, "axes": items, "implied_weights": implied}


def rank_by_utility(pool: Sequence[dict[str, Any]], beta: Vector,
                    limit: int = 3) -> list[dict[str, Any]]:
    """Highest utility first; equal utility falls back to the stable candidate id."""
    scored = [(_dot(beta, vector(entry["features"])), entry) for entry in pool]
    scored.sort(key=lambda item: (-item[0], item[1]["candidate_id"]))
    return [{**entry, "utility": utility} for utility, entry in scored[:limit]]


def required_train_responses(train_pairs: int) -> int:
    """Non-tie training answers needed to fit: 6 for the full design, fewer for
    scaled-down designs (at least 3) because the prior keeps small fits stable."""
    return min(MIN_TRAIN_RESPONSES, max(3, train_pairs // 2))


def comparisons_for(design: StudyDesign, answers: dict[int, str], split: str) -> list[Comparison]:
    """answers maps pair_id to "A" (left), "B" (right) or "tie"."""
    return [(design.schedules[pair.left]["x"], design.schedules[pair.right]["x"], answers[pair.pair_id])
            for pair in design.pairs if pair.split == split and pair.pair_id in answers]


def pool_spread(pool: Sequence[dict[str, Any]]) -> Vector:
    """Per-axis standard deviation of x over the feasible profiles (1 if constant).

    Dividing differences by this spread puts the three features on comparable
    scales before regularisation, so C = 1 shrinks each coefficient alike.
    Uses no labels, so the held-out test stays untouched.
    """
    spread = []
    for axis in range(len(AXES)):
        values = [vector(entry["features"])[axis] for entry in pool]
        mean = sum(values) / len(values) if values else 0.0
        sd = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values)) if values else 0.0
        spread.append(sd if sd > 1e-9 else 1.0)
    return tuple(spread)  # type: ignore[return-value]


def weight_prior(weights: dict[str, float], strength: float) -> Vector:
    """Utility coefficients implied by rule weights: lower weighted cost is better."""
    return tuple(-strength * weights[axis] for axis in AXES)  # type: ignore[return-value]


def fit_scaled(train: Sequence[Comparison], scale: Vector | None = None,
               c: float = REGULARISATION_C, prior: Vector | None = None) -> Vector:
    """Fit on (optionally standardised) differences; return beta in raw x units.

    ``prior`` is given in raw x units and converted to the fitting scale.
    """
    labelled = [(a, b, choice) for a, b, choice in train if choice != "tie"]
    divisor = scale or (1.0,) * len(AXES)
    diffs = [tuple(value / sd for value, sd in zip(_sub(a, b), divisor)) for a, b, _ in labelled]
    scaled_prior = (tuple(value * sd for value, sd in zip(prior, divisor))
                    if prior is not None else None)
    beta = fit_pairwise_logistic(diffs, [1 if choice == "A" else 0 for _, _, choice in labelled],
                                 c=c, prior=scaled_prior)
    return tuple(value / sd for value, sd in zip(beta, divisor))  # type: ignore[return-value]


def evaluate_design(design: StudyDesign, answers: dict[int, str],
                    student_weights: dict[str, float], *,
                    scale: Vector | None = None, c: float = REGULARISATION_C,
                    prior: Vector | None = None) -> dict[str, Any]:
    """Fit on training answers only, then score every method on held-out pairs."""
    train = comparisons_for(design, answers, "train")
    test = comparisons_for(design, answers, "test")
    labelled = [(a, b, choice) for a, b, choice in train if choice != "tie"]
    report: dict[str, Any] = {
        "train_pairs": len(train), "test_pairs": len(test),
        "train_ties": len(train) - len(labelled),
        "complete_design": design.complete,
        "chance": 0.5,
    }
    report["required_train_responses"] = required_train_responses(len(train))
    if len(labelled) < report["required_train_responses"]:
        report["status"] = "insufficient"
        return report
    beta = fit_scaled(labelled, scale, c, prior)
    report.update({
        "status": "learned",
        "beta": beta,
        "standardised": scale is not None,
        "c": c,
        "prior": list(prior) if prior is not None else None,
        "train_accuracy": pair_accuracy(learned_margin(beta), train),
        "learned": pair_accuracy(learned_margin(beta), test),
        "student_weighted": pair_accuracy(weighted_margin(student_weights), test),
        "equal_weight": pair_accuracy(weighted_margin(EQUAL_WEIGHTS), test),
    })
    return report
