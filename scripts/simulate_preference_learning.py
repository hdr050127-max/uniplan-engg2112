"""Stress-test the preference-learning design with synthetic students.

No real participant data is used. Each synthetic student has known feature
aversions w ~ Dirichlet(1, 1, 1) over x = (G/300, D/5, O/120) and true utility
u(x) = -w . x. They answer the app's comparison pairs through a logistic
choice model, P(A) = sigmoid(s * (u_A - u_B)), where s is how decisive they are.

Because the truth is known, the script measures what a pilot cannot observe:

* true agreement: share of feasible-profile pairs a method orders the same way
  as the student's true utility (generalisation beyond the 4 test pairs);
* top-1 regret: true utility lost by accepting the method's first
  recommendation instead of the student's best feasible profile;
* test reliability: how well the app's held-out pair accuracy tracks true
  agreement, and how often "learned beats the stronger baseline on the test
  pairs" matches the truth.

Usage:
    python3 scripts/simulate_preference_learning.py --units ENGG2112 AMME2301
    python3 scripts/simulate_preference_learning.py --units ENGG2112 AMME2262 CIVL3206 \\
        --students 400 --out output/simulation.md
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uniplan.arrangement import arrange_timetables  # noqa: E402
from uniplan.catalog import SnapshotCatalog  # noqa: E402
from uniplan.preference import (AXES, PRIOR_STRENGTH, Vector, comparisons_for,  # noqa: E402
                                design_study, fit_scaled, learned_margin, pair_accuracy,
                                pool_spread, vector, weight_prior, weighted_margin)
from uniplan.profile import prepare_student_profile  # noqa: E402
from uniplan.timetable_data import load_timetable_data  # noqa: E402

UI_DEFAULT = {"gap": 0.0, "campus_days": 0.5, "outside_hours": 0.5}
EQUAL = {axis: 1 / 3 for axis in AXES}


def build_pool(units: list[str], year: int, session: str) -> list[dict[str, Any]]:
    """Distinct feasible profiles for the default (teaching) groups of these units."""
    catalog = SnapshotCatalog(ROOT / "data/processed", ROOT / "data/requirements")
    raw = {"year": year, "session_code": session, "unit_codes": units, "unavailable_windows": []}
    prepared = prepare_student_profile(raw, catalog)
    if prepared["snapshot_ref"] is None:
        raise SystemExit("No single local snapshot covers these units: " +
                         "; ".join(item["message"] for item in prepared["blockers"]))
    data = load_timetable_data(prepared["profile"], prepared["snapshot_ref"], catalog)
    groups = {unit["unit_code"]: [group["group_id"] for group in unit["groups"]
                                  if group["default_selected"]]
              for unit in data.summary["units"]}
    ranking = arrange_timetables(data.meetings, groups, prepared["profile"])
    return ranking["_pool"]


def dot(a: Vector, b: Vector) -> float:
    return sum(x * y for x, y in zip(a, b))


def sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


POPULATIONS = {
    # Mean = equal weights: flatters the equal-weight baseline and prior.
    "mixed": (1.0, 1.0, 1.0),
    # Mostly cares about campus days (G, D, O concentrations); a robustness check.
    "commuter": (0.5, 3.0, 1.0),
}


def dirichlet(rng: random.Random, alpha: tuple[float, float, float] = POPULATIONS["mixed"]) -> Vector:
    draws = [rng.gammavariate(a, 1) for a in alpha]
    total = sum(draws)
    return tuple(value / total for value in draws)  # type: ignore[return-value]


def reported_weights(w: Vector, rng: random.Random, sigma: float, hide_gap: bool) -> dict[str, float]:
    """People state weights imprecisely; the current UI also hides G."""
    noisy = [value * math.exp(rng.gauss(0, sigma)) for value in w]
    if hide_gap:
        noisy[0] = 0.0
    total = sum(noisy) or 1.0
    return {axis: value / total for axis, value in zip(AXES, noisy)}


def evaluate_method(utility: Callable[[Vector], float], w: Vector, xs: list[Vector],
                    pairs: list[tuple[int, int]]) -> tuple[float, float]:
    """(true agreement over sampled pairs, top-1 regret) for one ranking rule."""
    agree = scored = 0.0
    for i, j in pairs:
        truth = -dot(w, xs[i]) + dot(w, xs[j])
        if abs(truth) < 1e-12:
            continue
        model = utility(xs[i]) - utility(xs[j])
        scored += 1
        agree += 0.5 if abs(model) < 1e-12 else float((model > 0) == (truth > 0))
    best = max(-dot(w, x) for x in xs)
    top = max(range(len(xs)), key=lambda k: (utility(xs[k]), -k))
    return agree / scored if scored else float("nan"), best - (-dot(w, xs[top]))


def summarise(values: list[float]) -> str:
    clean = [value for value in values if not math.isnan(value)]
    if not clean:
        return "—"
    mean = statistics.fmean(clean)
    half = 1.96 * statistics.pstdev(clean) / math.sqrt(len(clean)) if len(clean) > 1 else 0.0
    return f"{mean:.3f} ± {half:.3f}"


def correlation(a: list[float], b: list[float]) -> float:
    pairs = [(x, y) for x, y in zip(a, b) if not (math.isnan(x) or math.isnan(y))]
    if len(pairs) < 3:
        return float("nan")
    xs, ys = zip(*pairs)
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sum((x - mx) * (y - my) for x, y in pairs) / (sx * sy) if sx and sy else float("nan")


LEARNERS = {
    "learned · proposal (raw x, C=1, prior 0)":
        {"standardise": False, "c": 1.0, "pairs": "tradeoff", "prior": None},
    "learned · standardised x, C=1, prior 0":
        {"standardise": True, "c": 1.0, "pairs": "tradeoff", "prior": None},
    "learned · app default (standardised, equal-weight prior)":
        {"standardise": True, "c": 1.0, "pairs": "tradeoff", "prior": "equal"},
    "learned · app default with random pairs":
        {"standardise": True, "c": 1.0, "pairs": "random", "prior": "equal"},
}
PROPOSAL = "learned · proposal (raw x, C=1, prior 0)"
APP_DEFAULT = "learned · app default (standardised, equal-weight prior)"


def simulate(pool: list[dict[str, Any]], students: int, decisiveness: float, seed: int,
             weight_noise: float, population: str = "mixed") -> dict[str, Any]:
    rng = random.Random(seed)
    xs = [vector(entry["features"]) for entry in pool]
    all_pairs = [(i, j) for i in range(len(xs)) for j in range(i + 1, len(xs))]
    sampled = rng.sample(all_pairs, min(3000, len(all_pairs)))
    spread = pool_spread(pool)
    metrics: dict[str, dict[str, list[float]]] = {}

    def record(name: str, key: str, value: float) -> None:
        metrics.setdefault(name, {}).setdefault(key, []).append(value)

    for _ in range(students):
        w = dirichlet(rng, POPULATIONS[population])
        student_seed = rng.randrange(1 << 30)
        reported = reported_weights(w, rng, weight_noise, hide_gap=False)
        reported_ui = reported_weights(w, rng, weight_noise, hide_gap=True)
        baselines = {"baseline · equal weights": EQUAL,
                     "baseline · UI default (D 50% / O 50%)": UI_DEFAULT,
                     "baseline · self-reported weights": reported,
                     "baseline · self-reported, G hidden (current UI)": reported_ui}
        test_scores: dict[str, float] = {}
        for name, weights in baselines.items():
            wv = tuple(weights[axis] for axis in AXES)
            agreement, regret = evaluate_method(lambda x, wv=wv: -dot(wv, x), w, xs, sampled)
            record(name, "agreement", agreement)
            record(name, "regret", regret)
        designs: dict[str, tuple[Any, dict[int, str]]] = {}
        for name, config in LEARNERS.items():
            if config["pairs"] not in designs:
                design = design_study(pool, student_seed, pair_strategy=config["pairs"])
                if design is None:
                    raise SystemExit("Too few distinct feasible profiles for a study.")
                answer_rng = random.Random(student_seed)
                answers: dict[int, str] = {}
                for pair in design.pairs:
                    xa, xb = design.schedules[pair.left]["x"], design.schedules[pair.right]["x"]
                    p_a = sigmoid(decisiveness * (dot(w, xb) - dot(w, xa)))
                    answers[pair.pair_id] = "A" if answer_rng.random() < p_a else "B"
                designs[config["pairs"]] = (design, answers)
            design, answers = designs[config["pairs"]]
            train = comparisons_for(design, answers, "train")
            test = comparisons_for(design, answers, "test")
            prior = weight_prior(EQUAL, PRIOR_STRENGTH) if config["prior"] == "equal" else None
            beta = fit_scaled(train, spread if config["standardise"] else None, config["c"], prior)
            agreement, regret = evaluate_method(lambda x, beta=beta: dot(beta, x), w, xs, sampled)
            record(name, "agreement", agreement)
            record(name, "regret", regret)
            test_acc = pair_accuracy(learned_margin(beta), test)["accuracy"]
            record(name, "test_accuracy", float("nan") if test_acc is None else test_acc)
            if config["pairs"] == "tradeoff":
                for base_name, weights in (("equal", EQUAL), ("self-reported", reported)):
                    base = pair_accuracy(weighted_margin(weights), test)["accuracy"]
                    test_scores[f"{name}|{base_name}"] = (test_acc or 0) - (base or 0)
        stronger_true = max(metrics[b]["agreement"][-1] for b in (
            "baseline · equal weights", "baseline · self-reported weights"))
        for label, learner in (("proposal", PROPOSAL), ("app", APP_DEFAULT)):
            truly = metrics[learner]["agreement"][-1] > stronger_true
            on_test = min(test_scores[f"{learner}|equal"], test_scores[f"{learner}|self-reported"]) > 0
            record("reliability", f"{label}_beats_baselines_truth", float(truly))
            record("reliability", f"{label}_test_verdict_matches_truth", float(on_test == truly))

    rows = []
    for name, values in metrics.items():
        if name == "reliability":
            continue
        rows.append({"method": name, "agreement": summarise(values["agreement"]),
                     "regret": summarise(values["regret"]),
                     "test_accuracy": summarise(values.get("test_accuracy", [])),
                     "test_vs_truth_r": (f"{correlation(values['test_accuracy'], values['agreement']):.2f}"
                                         if "test_accuracy" in values else "—")})
    reliability = metrics["reliability"]
    return {
        "decisiveness": decisiveness, "students": students, "profiles": len(pool),
        "rows": rows,
        "reliability": {key: statistics.fmean(values) for key, values in reliability.items()},
    }


def to_markdown(units: list[str], results: list[dict[str, Any]], args: argparse.Namespace) -> str:
    lines = [f"# Preference-learning simulation: {' + '.join(units)}", "",
             f"{results[0]['profiles']} distinct feasible profiles · {args.students} synthetic students "
             f"per setting · population `{args.population}` (Dirichlet α = "
             f"{POPULATIONS[args.population]} over G, D, O) · weight-report noise σ = "
             f"{args.weight_noise} · seed {args.seed}.",
             "Values are means ± 95% CI half-widths across students. Agreement is over 3,000 "
             "sampled profile pairs; regret is in x units (0 = picked the student's best).", ""]
    for result in results:
        lines += [f"## Decisiveness s = {result['decisiveness']}", "",
                  "| Method | True agreement | Top-1 regret | 4-pair test acc. | r(test, truth) |",
                  "| --- | --- | --- | --- | --- |"]
        lines += [f"| {row['method']} | {row['agreement']} | {row['regret']} | "
                  f"{row['test_accuracy']} | {row['test_vs_truth_r']} |" for row in result["rows"]]
        rel = result["reliability"]
        lines += ["", "Stronger baseline = better of equal weights and self-reported weights "
                      "(with G), judged per student by true agreement.", ""]
        for label, name in (("proposal", "Proposal learner"), ("app", "App-default learner")):
            lines.append(f"- {name} truly beats the stronger baseline for "
                         f"{rel[f'{label}_beats_baselines_truth']:.0%} of students; the held-out "
                         f"pair verdict matches that truth for "
                         f"{rel[f'{label}_test_verdict_matches_truth']:.0%}.")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--units", nargs="+", default=["ENGG2112", "AMME2301"])
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--session", default="S2C")
    parser.add_argument("--students", type=int, default=300)
    parser.add_argument("--decisiveness", type=float, nargs="+", default=[5.0, 10.0, 20.0])
    parser.add_argument("--weight-noise", type=float, default=0.5,
                        help="log-normal σ applied to true weights when students self-report")
    parser.add_argument("--population", choices=sorted(POPULATIONS), default="mixed")
    parser.add_argument("--seed", type=int, default=2112)
    parser.add_argument("--out", type=Path, help="write the Markdown report here")
    parser.add_argument("--json", type=Path, help="also write raw results as JSON")
    args = parser.parse_args(argv)
    units = [unit.upper() for unit in args.units]
    pool = build_pool(units, args.year, args.session.upper())
    results = [simulate(pool, args.students, s, args.seed, args.weight_noise, args.population)
               for s in args.decisiveness]
    report = to_markdown(units, results, args)
    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report + "\n", encoding="utf-8")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
