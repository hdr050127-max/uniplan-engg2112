"""Population trade-off model: a pooled conditional logit on menu choices.

The shortlist turns each student's decision into a choice from a small menu
of non-dominated plans. Pooling those choices across students estimates how
the group trades the three costs against each other:

    P(choose i | menu) = exp(beta . z_i) / sum_j exp(beta . z_j)

with z = (gap hours/week, campus days/week, hours/week outside preferred
times). In natural units the ratios are directly readable, e.g.
beta_D / beta_G = hours of waiting per week a student would accept to save
one campus day per week (a marginal rate of substitution).

Pairwise comparisons are menus of two, so both kinds of data share one model.
Evaluation is leave-one-participant-out: every prediction for a student comes
from a model that never saw that student.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

from .preference import _solve


NAMES = ("gap_hours", "campus_days", "outside_hours")
Row = tuple[float, float, float]
# Natural units -> rule scale x = (G/300 min, D/5, O/120 min): x_G = z_G/5, x_D = z_D/5, x_O = z_O/2.
RULE_SCALE = (5.0, 5.0, 2.0)


@dataclass(frozen=True)
class MenuChoice:
    participant: str
    menu: tuple[Row, ...]  # natural units, see NAMES
    chosen: int


def natural_row(gap_min: float, campus_days: float, outside_min: float) -> Row:
    return (gap_min / 60.0, float(campus_days), outside_min / 60.0)


def from_scaled(x: Sequence[float]) -> Row:
    """Undo the rule-ranking scaling x = (G/300, D/5, O/120)."""
    return natural_row(x[0] * 300.0, x[1] * 5.0, x[2] * 120.0)


def _softmax(scores: Sequence[float]) -> list[float]:
    top = max(scores)
    exps = [math.exp(score - top) for score in scores]
    total = sum(exps)
    return [value / total for value in exps]


def _objective(beta: Sequence[float], choices: Sequence[MenuChoice],
               centre: Sequence[float], l2: float) -> float:
    value = -0.5 * l2 * sum((b - m) ** 2 for b, m in zip(beta, centre))
    for choice in choices:
        scores = [sum(b * z for b, z in zip(beta, row)) for row in choice.menu]
        top = max(scores)
        value += scores[choice.chosen] - top - math.log(sum(math.exp(score - top) for score in scores))
    return value


def fit_conditional_logit(choices: Sequence[MenuChoice], *, l2: float = 0.01,
                          prior: Sequence[float] | None = None,
                          max_iter: int = 100, tol: float = 1e-10) -> tuple[float, ...]:
    """Maximise sum log P(chosen) - l2/2 |beta - prior|^2 by damped Newton steps.

    The L2 term keeps the fit finite when one plan always wins (perfect
    separation is common with few, decisive participants); a prior moves the
    shrinkage target from "no preference" to a starting belief. Each step is
    halved until the objective improves, so the fit cannot run away.
    """
    usable = [choice for choice in choices if len(choice.menu) >= 2]
    dim = len(NAMES)
    centre = list(prior) if prior is not None else [0.0] * dim
    beta = centre[:]
    current = _objective(beta, usable, centre, l2)
    for _ in range(max_iter):
        grad = [-l2 * (b - m) for b, m in zip(beta, centre)]
        hess = [[l2 if i == j else 0.0 for j in range(dim)] for i in range(dim)]
        for choice in usable:
            probs = _softmax([sum(b * z for b, z in zip(beta, row)) for row in choice.menu])
            mean = [sum(p * row[k] for p, row in zip(probs, choice.menu)) for k in range(dim)]
            chosen = choice.menu[choice.chosen]
            for i in range(dim):
                grad[i] += chosen[i] - mean[i]
                for j in range(dim):
                    second = sum(p * row[i] * row[j] for p, row in zip(probs, choice.menu))
                    hess[i][j] += second - mean[i] * mean[j]
        step = _solve(hess, grad)  # ascent direction: H is the negated Hessian
        scale = 1.0
        while True:
            trial = [b + scale * d for b, d in zip(beta, step)]
            value = _objective(trial, usable, centre, l2)
            if value >= current - 1e-12 or scale < 1e-8:
                break
            scale /= 2
        moved = max(abs(scale * d) for d in step)
        beta, current = trial, value
        if moved < tol:
            break
    return tuple(beta)


# Same starting belief as the per-student learner: equal weights on the rule
# scales with strength 10, here in natural units. lambda = 1 was chosen on
# synthetic pilots (scripts/simulate_menu_choices.py): it stops a 16-person
# pilot from over-fitting and changes little once data accumulate.
POPULATION_L2 = 1.0


def equal_prior(strength: float = 10.0) -> tuple[float, float, float]:
    return tuple(-strength / 3 / scale for scale in RULE_SCALE)  # type: ignore[return-value]


def fit_population(choices: Sequence[MenuChoice]) -> tuple[float, ...]:
    """The default pooled fit: shrink toward equal weights rather than toward zero."""
    return fit_conditional_logit(choices, l2=POPULATION_L2, prior=equal_prior())


def choice_probabilities(beta: Sequence[float], menu: Sequence[Row]) -> list[float]:
    return _softmax([sum(b * z for b, z in zip(beta, row)) for row in menu])


def trade_offs(beta: Sequence[float]) -> dict[str, float | None]:
    """Rates of substitution, defined only when waiting is a cost (beta_G < 0)."""
    gap, days, outside = beta
    if gap >= -1e-9:
        return {"gap_hours_per_campus_day": None, "gap_hours_per_outside_hour": None}
    return {"gap_hours_per_campus_day": days / gap, "gap_hours_per_outside_hour": outside / gap}


def implied_weights(beta: Sequence[float]) -> dict[str, float] | None:
    """Signed share of influence on the rule scales, comparable with typed weights.

    Positive = a cost (less is better); negative = students preferred more of
    it. Shares of |beta| always sum to 1, so a feature that barely matters
    gives a small share instead of an exploding rate of substitution.
    """
    costs = [-b * scale for b, scale in zip(beta, RULE_SCALE)]
    total = sum(abs(cost) for cost in costs)
    if total <= 1e-12:
        return None
    return {name: cost / total for name, cost in zip(("gap", "campus_days", "outside_hours"), costs)}


Predictor = Callable[[Sequence[Row]], int]


def rule_predictor(weights: Sequence[float]) -> Predictor:
    """Pick the lowest weighted cost in natural units (ties: first listed)."""
    return lambda menu: min(range(len(menu)), key=lambda i: (
        sum(w * z for w, z in zip(weights, menu[i])), i))


def logit_predictor(beta: Sequence[float]) -> Predictor:
    return lambda menu: max(range(len(menu)), key=lambda i: (
        sum(b * z for b, z in zip(beta, menu[i])), -i))


def leave_one_participant_out(
    choices: Sequence[MenuChoice], *,
    fit: Callable[[Sequence[MenuChoice]], tuple[float, ...]] = fit_population,
) -> dict[str, Any]:
    """Top-1 accuracy predicting each participant's choices from everyone else's.

    Baselines need no training: equal weights on the rule scales (G/300, D/5,
    O/120 in these units), "fewest campus days", and a uniform random guess
    (expected accuracy 1/|menu|).
    """
    by_person: dict[str, list[MenuChoice]] = defaultdict(list)
    for choice in choices:
        if len(choice.menu) >= 2:
            by_person[choice.participant].append(choice)
    equal = rule_predictor((60 / 300, 1 / 5, 60 / 120))
    fewest_days = rule_predictor((1e-6, 1.0, 1e-6))
    hits: dict[str, list[float]] = defaultdict(list)
    per_person: dict[str, dict[str, float]] = {}
    for person, held_out in by_person.items():
        training = [choice for other, rows in by_person.items() if other != person for choice in rows]
        if not training:
            continue
        model = logit_predictor(fit(training))
        scores: dict[str, list[float]] = defaultdict(list)
        for choice in held_out:
            for name, predictor in (("pooled logit", model), ("equal weights", equal),
                                    ("fewest campus days", fewest_days)):
                scores[name].append(float(predictor(choice.menu) == choice.chosen))
            scores["random guess"].append(1 / len(choice.menu))
        per_person[person] = {name: sum(values) / len(values) for name, values in scores.items()}
        for name, value in per_person[person].items():
            hits[name].append(value)
    return {"participants": len(per_person),
            "accuracy": {name: sum(values) / len(values) for name, values in hits.items()},
            "per_participant": per_person}


def bootstrap(choices: Sequence[MenuChoice], statistic: Callable[[list[MenuChoice]], Any],
              *, reps: int = 1000, seed: int = 0) -> list[Any]:
    """Resample whole participants, so each person's choices stay together."""
    by_person: dict[str, list[MenuChoice]] = defaultdict(list)
    for choice in choices:
        by_person[choice.participant].append(choice)
    people = sorted(by_person)
    rng = random.Random(seed)
    results = []
    for _ in range(reps):
        sample = [choice for person in rng.choices(people, k=len(people))
                  for choice in by_person[person]]
        results.append(statistic(sample))
    return results


def percentile_interval(values: Iterable[float | None], level: float = 0.95) -> tuple[float, float] | None:
    clean = sorted(value for value in values if value is not None and math.isfinite(value))
    if len(clean) < 10:
        return None
    low = clean[int((1 - level) / 2 * len(clean))]
    high = clean[min(len(clean) - 1, int((1 + level) / 2 * len(clean)))]
    return low, high
