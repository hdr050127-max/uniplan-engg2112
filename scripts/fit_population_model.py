"""Fit the pooled trade-off model to consented pilot choices.

Uses two kinds of consented records from data/private/profiles.sqlite3:

* shortlist choices ("采用此方案" on a shortlist plan): the whole menu of
  non-dominated plans and which one was taken;
* pairwise comparisons from the optional study, as menus of two (ties are
  dropped; both training and held-out pairs count here, because this model
  is evaluated separately, by leave-one-participant-out).

Reports the fitted coefficients, the implied weights on G / D / O with
participant-bootstrap 95% intervals, rates of substitution when defined, and
out-of-sample top-1 accuracy against equal weights, "fewest campus days" and
random guessing.

Usage:
    python3 scripts/fit_population_model.py
    python3 scripts/fit_population_model.py --db data/private/profiles.sqlite3 --out output/population.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uniplan.choice_model import (MenuChoice, bootstrap, fit_population, from_scaled,  # noqa: E402
                                  implied_weights, leave_one_participant_out, natural_row,
                                  percentile_interval, trade_offs)
from uniplan.store import ProfileStore  # noqa: E402


def load_menu_choices(store: ProfileStore) -> tuple[list[MenuChoice], dict[str, int]]:
    choices: list[MenuChoice] = []
    counts = {"shortlist": 0, "pairwise": 0, "pairwise_ties_dropped": 0}
    for outcome in store.load_outcomes():
        detail = outcome["detail"]
        if outcome["event"] != "accepted" or detail.get("method") != "shortlist":
            continue
        menu = tuple(natural_row(*row) for row in detail["menu"])
        if len(menu) >= 2:
            choices.append(MenuChoice(outcome["participant_id"], menu, detail["chosen"]))
            counts["shortlist"] += 1
    for row in store.load_choices():
        if row["choice"] == "tie":
            counts["pairwise_ties_dropped"] += 1
            continue
        menu = (from_scaled(row["x_a"]), from_scaled(row["x_b"]))
        choices.append(MenuChoice(row["participant_id"], menu, 0 if row["choice"] == "A" else 1))
        counts["pairwise"] += 1
    return choices, counts


def report(store: ProfileStore, reps: int, seed: int) -> str:
    choices, counts = load_menu_choices(store)
    people = {choice.participant for choice in choices}
    lines = ["# UniPlan population trade-off model", "",
             f"Consented choices: {counts['shortlist']} shortlist menus and {counts['pairwise']} "
             f"pairwise comparisons ({counts['pairwise_ties_dropped']} ties dropped) from "
             f"{len(people)} participants.", ""]
    if len(people) < 3:
        lines.append("Fewer than 3 participants: too little data to fit or evaluate a pooled model.")
        return "\n".join(lines)
    beta = fit_population(choices)
    weights = implied_weights(beta)
    draws = bootstrap(choices, lambda sample: implied_weights(fit_population(sample)), reps=reps, seed=seed)
    lines += ["Conditional logit shrunk toward equal weights (λ = 1); utility per hour of gap, per "
              "campus day and per hour outside preferred times:", "",
              f"- β = (gap {beta[0]:+.3f}, days {beta[1]:+.3f}, outside {beta[2]:+.3f})", ""]
    if weights:
        lines += ["Influence share on the rule scales (positive = less is better; negative = students "
                  "preferred more of it; absolute shares sum to 1):", "",
                  "| Feature | Influence share | 95% participant-bootstrap interval |", "| --- | --- | --- |"]
        for axis, label in (("gap", "G gap"), ("campus_days", "D campus days"),
                            ("outside_hours", "O outside preferred hours")):
            interval = percentile_interval(draw[axis] if draw else None for draw in draws)
            text = f"[{interval[0]:.2f}, {interval[1]:.2f}]" if interval else "—"
            lines.append(f"| {label} | {weights[axis]:.2f} | {text} |")
    else:
        lines.append("All coefficients are zero; the data show no consistent trade-off.")
    rates = trade_offs(beta)
    if rates["gap_hours_per_campus_day"] is not None:
        lines += ["", f"Students accept about {rates['gap_hours_per_campus_day']:.1f} hours of waiting per "
                      f"week to save one campus day per week, and {rates['gap_hours_per_outside_hour']:.1f} "
                      "hours of waiting to avoid one hour outside preferred times. Ratios are unstable "
                      "when waiting barely matters; prefer the weights above."]
    evaluation = leave_one_participant_out(choices)
    lines += ["", f"## Out-of-sample prediction ({evaluation['participants']} participants, "
                  "leave-one-participant-out)", "",
              "| Predictor | Top-1 accuracy |", "| --- | --- |"]
    for name, value in sorted(evaluation["accuracy"].items(), key=lambda item: -item[1]):
        lines.append(f"| {name} | {value:.3f} |")
    lines += ["", "Simulations (`scripts/simulate_menu_choices.py`) put the ceiling near 0.5 for "
                  "heterogeneous students: a pooled model predicts the typical choice, so the "
                  "shortlist still leaves the final pick to each student."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fit the pooled trade-off model to pilot data")
    parser.add_argument("--db", type=Path, default=ROOT / "data/private/profiles.sqlite3")
    parser.add_argument("--reps", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=2112)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    text = report(ProfileStore(args.db), args.reps, args.seed)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
