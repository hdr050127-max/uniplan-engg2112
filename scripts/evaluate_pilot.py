"""Evaluate the consented pilot exactly as proposal step 4 describes.

Reads only `choices` and `outcomes` rows saved with consent in
data/private/profiles.sqlite3. For every completed study it refits the learner
on that student's training pairs, then scores the held-out pairs for:

* the learned model (app default and the proposal's exact specification),
* the student's own typed weights,
* equal weights,
* chance (50%).

Ties chosen by the student are excluded; predicted ties earn half credit.
Means are taken across participants, with participant-bootstrap 95% CIs, so
each student counts once however many pairs they answered. First-use times
come from `outcomes`.

Usage:
    python3 scripts/evaluate_pilot.py
    python3 scripts/evaluate_pilot.py --db data/private/profiles.sqlite3 --out output/pilot.md
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uniplan.preference import (PRIOR_STRENGTH, fit_scaled, learned_margin,  # noqa: E402
                                pair_accuracy, required_train_responses, weight_prior,
                                weighted_margin)
from uniplan.ranking import EQUAL_WEIGHTS  # noqa: E402
from uniplan.store import ProfileStore  # noqa: E402

METHODS = ("learned (app default)", "learned (proposal spec)", "typed weights", "equal weights")


def study_scores(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Held-out accuracy of every method for one study, or None if unscorable."""
    train = [(tuple(row["x_a"]), tuple(row["x_b"]), row["choice"])
             for row in rows if row["split"] == "train"]
    test = [(tuple(row["x_a"]), tuple(row["x_b"]), row["choice"])
            for row in rows if row["split"] == "test"]
    if sum(choice != "tie" for *_, choice in train) < required_train_responses(len(train)):
        return None
    typed = rows[0]["baseline_weights"]
    spread = rows[0]["fit_scale"]  # the exact per-feature spread the app used
    learners = {
        "learned (app default)": fit_scaled(
            train, tuple(spread), 1.0, weight_prior(EQUAL_WEIGHTS, PRIOR_STRENGTH)),
        "learned (proposal spec)": fit_scaled(train, None, 1.0, None),
    }
    scores = {name: pair_accuracy(learned_margin(beta), test) for name, beta in learners.items()}
    scores["typed weights"] = pair_accuracy(weighted_margin(typed), test)
    scores["equal weights"] = pair_accuracy(weighted_margin(EQUAL_WEIGHTS), test)
    scores["train accuracy (app default)"] = pair_accuracy(
        learned_margin(learners["learned (app default)"]), train)
    return scores


def bootstrap_ci(values: list[float], rng: random.Random, reps: int = 5000) -> tuple[float, float]:
    if len(values) < 2:
        return (float("nan"), float("nan"))
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(reps))
    return means[int(0.025 * reps)], means[int(0.975 * reps) - 1]


def evaluate(store: ProfileStore, seed: int) -> str:
    choices = store.load_choices()
    by_study: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in choices:
        by_study[row["study_id"]].append(row)
    # One study per participant (a person may have several linked profiles):
    # keep each participant's most complete study.
    by_profile: dict[str, list[dict[str, Any]]] = {}
    for rows in by_study.values():
        current = by_profile.get(rows[0]["participant_id"])
        if current is None or len(rows) > len(current):
            by_profile[rows[0]["participant_id"]] = rows
    per_student = {profile: study_scores(rows) for profile, rows in by_profile.items()}
    scored = {profile: result for profile, result in per_student.items() if result}
    lines = ["# UniPlan pilot evaluation", "",
             f"Consented studies: {len(by_study)} · participants: {len(by_profile)} · "
             f"scorable (enough non-tie training answers): {len(scored)}.", ""]
    if not scored:
        lines.append("No scorable participants yet. Recruitment shortfall should be reported as such.")
        return "\n".join(lines)
    rng = random.Random(seed)
    lines += ["| Method | Mean held-out accuracy | 95% participant-bootstrap CI | Participants |",
              "| --- | --- | --- | --- |"]
    for method in (*METHODS, "train accuracy (app default)"):
        values = [result[method]["accuracy"] for result in scored.values()
                  if result[method]["accuracy"] is not None]
        if not values:
            continue
        low, high = bootstrap_ci(values, rng)
        lines.append(f"| {method} | {statistics.fmean(values):.3f} | [{low:.3f}, {high:.3f}] | {len(values)} |")
    lines.append("| chance | 0.500 | — | — |")
    def mean_of(method: str) -> float:
        values = [result[method]["accuracy"] for result in scored.values()
                  if result[method]["accuracy"] is not None]
        return statistics.fmean(values) if values else float("-inf")

    # "Stronger baseline" is chosen on group means, then compared participant by participant.
    stronger = max(("typed weights", "equal weights"), key=mean_of)
    diffs = [result["learned (app default)"]["accuracy"] - result[stronger]["accuracy"]
             for result in scored.values()
             if result["learned (app default)"]["accuracy"] is not None
             and result[stronger]["accuracy"] is not None]
    if diffs:
        low, high = bootstrap_ci(diffs, rng)
        disagree = sum(abs(diff) > 1e-12 for diff in diffs)
        lines += ["", f"Learned minus the stronger baseline ({stronger}), paired by participant: mean "
                      f"{statistics.fmean(diffs):+.3f}, 95% CI [{low:+.3f}, {high:+.3f}]; the two "
                      f"differ for {disagree} of {len(diffs)} participants. The proposal's criterion "
                      "is a positive mean; a CI spanning 0 means the pilot cannot distinguish them."]
    ties = sum(result["learned (app default)"]["ties"] for result in scored.values())
    lines += ["", f"Student ties on held-out pairs (excluded from accuracy): {ties}."]
    outcomes = store.load_outcomes()
    study_times = [item["elapsed_ms"] / 1000 for item in outcomes
                   if item["event"] == "study_completed" and item["elapsed_ms"] is not None]
    accept_times = defaultdict(list)
    for item in outcomes:
        if item["event"] == "accepted" and item["elapsed_ms"] is not None:
            accept_times[item["detail"].get("method", "?")].append(item["elapsed_ms"] / 1000)
    if study_times or accept_times:
        lines += ["", "## First-use time", ""]
        if study_times:
            lines.append(f"- Comparison task: median {statistics.median(study_times):.0f} s "
                         f"(n = {len(study_times)}).")
        for method, times in sorted(accept_times.items()):
            lines.append(f"- From first form interaction to accepting a {method} plan: median "
                         f"{statistics.median(times):.0f} s (n = {len(times)}).")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate consented UniPlan pilot data")
    parser.add_argument("--db", type=Path, default=ROOT / "data/private/profiles.sqlite3")
    parser.add_argument("--seed", type=int, default=2112)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    report = evaluate(ProfileStore(args.db), args.seed)
    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
