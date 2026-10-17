"""Can a small pilot learn how students trade off waiting, days and hours?

Step 1 builds a library of *real* shortlist menus: for each locally cached
course combination it draws random student constraints (unavailable blocks,
preferred hours, transfer buffer), runs the full search and keeps the Pareto
menu. Step 2 simulates pilots: synthetic students with heterogeneous weights
choose from a few menus each, and the pooled conditional logit is judged by

* leave-one-participant-out top-1 accuracy against equal weights, "fewest
  campus days" and random guessing;
* how precisely it recovers the population trade-off (gap hours accepted per
  campus day saved), using a 4,000-student fit as the reference value.

Usage:
    python3 scripts/simulate_menu_choices.py                  # builds/reuses output/menu_library.json
    python3 scripts/simulate_menu_choices.py --rebuild --draws 40
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uniplan.arrangement import arrange_timetables  # noqa: E402
from uniplan.catalog import SnapshotCatalog  # noqa: E402
from uniplan.choice_model import (MenuChoice, bootstrap, choice_probabilities,  # noqa: E402
                                  fit_population, implied_weights,
                                  leave_one_participant_out, natural_row, percentile_interval)
from uniplan.profile import prepare_student_profile  # noqa: E402
from uniplan.ranking import pareto_front  # noqa: E402
from uniplan.schedule import SearchLimitError  # noqa: E402
from uniplan.timetable_data import load_timetable_data  # noqa: E402

SCENARIOS = (("ENGG2112", "AMME2301"), ("CIVL3206", "ENGG2112"),
             ("ENGG2112", "AMME2262", "CIVL3206"), ("ENGG2112", "AMME1362"))
POPULATIONS = {"mixed": (1.0, 1.0, 1.0), "commuter": (0.5, 3.0, 1.0)}


def random_constraints(rng: random.Random) -> dict[str, Any]:
    windows = []
    for _ in range(rng.choice((0, 1, 1, 2))):
        start = rng.randrange(8, 17) * 60
        windows.append({"weekday": rng.randrange(1, 6), "start_min": start,
                        "end_min": start + rng.choice((120, 180, 240))})
    return {"unavailable_windows": windows, "transition_min": rng.choice((0, 0, 10)),
            "preferred_hours": {"start_min": rng.choice((480, 540, 600)),
                                "end_min": rng.choice((1020, 1080, 1140))}}


def build_library(draws: int, seed: int) -> list[dict[str, Any]]:
    catalog = SnapshotCatalog(ROOT / "data/processed", ROOT / "data/requirements")
    rng = random.Random(seed)
    library = []
    for units in SCENARIOS:
        base = {"year": 2026, "session_code": "S2C", "unit_codes": list(units)}
        prepared = prepare_student_profile({**base, "unavailable_windows": []}, catalog)
        if prepared["snapshot_ref"] is None:
            print(f"skip {units}: no single snapshot", file=sys.stderr)
            continue
        data = load_timetable_data(prepared["profile"], prepared["snapshot_ref"], catalog)
        groups = {unit["unit_code"]: [group["group_id"] for group in unit["groups"]
                                      if group["default_selected"]]
                  for unit in data.summary["units"]}
        for _ in range(draws):
            profile = prepare_student_profile({**base, **random_constraints(rng)}, catalog)["profile"]
            try:
                ranking = arrange_timetables(data.meetings, groups, profile)
            except SearchLimitError:
                continue
            if not ranking["feasible_count"]:
                continue
            menu = [natural_row(entry["features"]["gap_min"], entry["features"]["campus_days"],
                                entry["features"]["outside_min"])
                    for entry in pareto_front(ranking["_pool"])]
            library.append({"units": list(units), "feasible": ranking["feasible_count"],
                            "profiles": ranking["distinct_profile_count"], "menu": menu})
        print(f"{'+'.join(units)}: {sum(item['units'] == list(units) for item in library)} menus",
              file=sys.stderr)
    return library


def true_beta(weights: tuple[float, float, float], decisiveness: float) -> tuple[float, float, float]:
    """Natural-unit utility matching the rule scales x = (G/300, D/5, O/120), G and O in minutes."""
    return (-decisiveness * weights[0] * 60 / 300, -decisiveness * weights[1] / 5,
            -decisiveness * weights[2] * 60 / 120)


def simulate_pilot(menus: list[list], participants: int, per_person: int, alpha, decisiveness: float,
                   rng: random.Random) -> list[MenuChoice]:
    choices = []
    for person in range(participants):
        draws = [rng.gammavariate(a, 1) for a in alpha]
        beta = true_beta(tuple(value / sum(draws) for value in draws), decisiveness)
        for menu in rng.sample(menus, per_person):
            menu = tuple(tuple(row) for row in menu)
            pick, chosen = rng.random(), len(menu) - 1
            for index, prob in enumerate(choice_probabilities(beta, menu)):
                pick -= prob
                if pick < 0:
                    chosen = index
                    break
            choices.append(MenuChoice(f"p{person}", menu, chosen))
    return choices


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulate pilots of the pooled menu-choice model")
    parser.add_argument("--library", type=Path, default=ROOT / "output/menu_library.json")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--draws", type=int, default=30, help="constraint draws per course combination")
    parser.add_argument("--population", choices=sorted(POPULATIONS), default="mixed")
    parser.add_argument("--decisiveness", type=float, default=10.0)
    parser.add_argument("--reps", type=int, default=40, help="simulated pilots per setting")
    parser.add_argument("--seed", type=int, default=2112)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    if args.rebuild or not args.library.exists():
        library = build_library(args.draws, args.seed)
        args.library.parent.mkdir(parents=True, exist_ok=True)
        args.library.write_text(json.dumps(library), encoding="utf-8")
    library = json.loads(args.library.read_text(encoding="utf-8"))
    menus = [item["menu"] for item in library if len(item["menu"]) >= 2]
    sizes = [len(item["menu"]) for item in library]
    alpha = POPULATIONS[args.population]
    rng = random.Random(args.seed)

    def days_share(sample: list[MenuChoice]) -> float | None:
        weights = implied_weights(fit_population(sample))
        return weights["campus_days"] if weights else None

    reference = days_share(simulate_pilot(menus, 4000, 1, alpha, args.decisiveness, rng))
    true_mean = alpha[1] / sum(alpha)
    lines = [
        "# Menu-choice pilot simulation", "",
        f"Menu library: {len(library)} shortlists from {len(SCENARIOS)} course combinations under "
        f"random constraints. Menu size: median {statistics.median(sizes):.0f}, "
        f"range {min(sizes)}–{max(sizes)}; {sum(size == 1 for size in sizes)} of {len(sizes)} "
        "have a single plan (no choice needed) and are excluded below.",
        f"Population `{args.population}` (Dirichlet α = {alpha}), decisiveness s = {args.decisiveness}, "
        f"{args.reps} simulated pilots per row, seed {args.seed}.",
        f"Estimand: the pooled model's signed influence share on campus days D (rule scales). "
        f"Reference from a 4,000-student fit: {reference:.2f} (population mean weight "
        f"{true_mean:.2f}; the pooled fit also reflects how decisively each group chooses).", "",
        "Pooled logit = conditional logit shrunk toward equal weights (λ = 1). Accuracy = leave-one-participant-out top-1 accuracy predicting the plan chosen from a menu.", "",
        "| Participants × menus each | Pooled logit | Equal weights | Fewest days | Random | "
        "D weight 95% CI (median half-width) | CI covers reference |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for participants, per_person in ((16, 1), (16, 3), (40, 3), (100, 3)):
        accuracy: dict[str, list[float]] = {}
        widths, covers = [], []
        for _ in range(args.reps):
            pilot = simulate_pilot(menus, participants, per_person, alpha, args.decisiveness, rng)
            for name, value in leave_one_participant_out(pilot)["accuracy"].items():
                accuracy.setdefault(name, []).append(value)
            interval = percentile_interval(bootstrap(
                pilot, days_share, reps=200, seed=rng.randrange(1 << 30)))
            if interval:
                widths.append(interval[1] - interval[0])
                covers.append(interval[0] <= reference <= interval[1])
        cells = [f"{statistics.fmean(accuracy[name]):.2f}" for name in
                 ("pooled logit", "equal weights", "fewest campus days", "random guess")]
        width = f"± {statistics.median(widths) / 2:.2f}" if widths else "—"
        cover = f"{statistics.fmean(covers):.0%}" if covers else "—"
        lines.append(f"| {participants} × {per_person} | {' | '.join(cells)} | {width} | {cover} |")
    report = "\n".join(lines)
    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
