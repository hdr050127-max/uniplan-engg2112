"""How often the closest-timetable fallback (uniplan.nearest, docs/DESIGN.md 10.1) replaces a dead end.

Scenarios: every sentence of a frozen test set (default the final exam, llm/parse/exam/exam.csv;
written by Claude, NOT real students) with its hand-written answers as the confirmed conditions,
planned on one of four course combinations from the committed snapshots, exactly as
scripts/evaluate_explain.py does. A sentence whose strict search finds nothing is planned again
with the fallback on. No model is called (reasons are templates).

    python3 scripts/evaluate_nearest.py
    python3 scripts/evaluate_nearest.py --test-file llm/parse/data/test_claude_v2.csv

Writes output/pipeline/nearest_eval_<test set>.json (every scenario) and .md (summary).
The fallback was added after the final exam; it never changes a timetable that fits.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_explain import UNIT_SETS, base_profile, conditions_from, sentences, tracked_catalog  # noqa: E402
from llm.explain import allowed_for, check_reason, facts_of  # noqa: E402
from uniplan.advisor import conditions_of, hard_violations, merge_conditions  # noqa: E402
from uniplan.main import main  # noqa: E402
from uniplan.nearest import soften  # noqa: E402
from uniplan.ranking import SCALES, axes_name  # noqa: E402

EXAM = ROOT / "llm/parse/exam/exam.csv"
OUT = ROOT / "output/pipeline"


def run_one(index: int, sentence_id: str, sentence: str, rows: list[dict[str, str]], catalog, groups) -> dict:
    units = UNIT_SETS[index % len(UNIT_SETS)]
    conditions = conditions_from(rows)
    profile = merge_conditions(base_profile(units), conditions)
    record = {"sentence_id": sentence_id, "sentence": sentence, "units": units}
    strict = main(profile, catalog, selected_groups=groups[tuple(units)], student_text=sentence,
                  cares=conditions["cares"])
    record["strict"] = strict["status"]
    if strict["status"] != "no_feasible":
        return record
    started = time.monotonic()
    result = main(profile, catalog, selected_groups=groups[tuple(units)], student_text=sentence,
                  cares=conditions["cares"], nearest=True)
    record["seconds"] = round(time.monotonic() - started, 2)
    record["status"] = result["status"]
    if result["status"] != "nearest":
        record["why"] = (result.get("blockers") or [{"message": ""}])[0]["message"]
        return record
    ranking = result["ranking_result"]
    axes = axes_name(tuple(axis for axis in SCALES if axis in (conditions["cares"] or SCALES)))
    menu = ranking["recommendation"]["menus"][axes]
    picks = [ranking["shortlist"]["items"][cid] for cid in menu["picks"]]
    confirmed = conditions_of(result["profile"], axes.split(","), conditions["cares"])
    relaxed = soften(result["profile"])
    record["watch"] = ranking["nearest"]["watch"]
    record["picks"] = []
    pool = ranking["recommendation"]["_candidates"][axes]  # the list rank() saw, as the reasons used
    for position, (pick, reason) in enumerate(zip(picks, menu["reasons"])):
        facts = facts_of(position, picks, confirmed, pool)
        record["picks"].append({
            "candidate_id": pick["candidate_id"], "pattern": pick["pattern"],
            "limits_broken": len(pick["breaks"]), "amount": round(sum(item["amount"] for item in pick["breaks"]), 1),
            "kinds": [item["kind"] for item in pick["breaks"]], "broken": pick["broken"],
            "clashes": hard_violations(pick["meetings"], relaxed), "reason": reason,
            "reason_passes": check_reason(reason, facts, allowed_for(facts), first=position == 0) is None,
        })
    return record


def summary(records: list[dict], test_set: str) -> str:
    dead = [record for record in records if record["strict"] == "no_feasible"]
    saved = [record for record in dead if record.get("status") == "nearest"]
    firsts = [record["picks"][0] for record in saved]
    picks = [pick for record in saved for pick in record["picks"]]
    by_count = Counter(pick["limits_broken"] for pick in firsts)
    kinds = Counter(kind for pick in firsts for kind in pick["kinds"])
    seconds = [record["seconds"] for record in dead if "seconds" in record]

    def rate(part: int, whole: int) -> str:
        return f"{part} / {whole} ({part / whole:.0%})" if whole else "0 / 0"

    lines = [
        "# Closest timetables when nothing fits", "",
        f"Sentences: `{test_set}`, written by Claude (Opus 5.5), **not real student data**. Conditions are the "
        "file's hand-written answers; timetables come from the committed 2026 S2C snapshots. The fallback "
        "(`uniplan/nearest.py`, docs/DESIGN.md 10.1) was added after the final exam and only runs when the "
        "strict search finds nothing.", "",
        "| | |", "| --- | --- |",
        f"| Sentences | {len(records)} |",
        f"| No timetable under the strict conditions | {len(dead)} |",
        f"| — now given the closest timetables | {rate(len(saved), len(dead))} |",
        f"| — of those, by watching one lecture as a recording | {sum(bool(record['watch']) for record in saved)} |",
        f"| — still a dead end | {len(dead) - len(saved)} |",
        f"| Pick 1: limits broken (mean) | {statistics.mean(pick['limits_broken'] for pick in firsts):.2f} |"
        if firsts else "| Pick 1: limits broken (mean) | none |",
        f"| Pick 1: limits broken, how often | {', '.join(f'{count}: {n}' for count, n in sorted(by_count.items()))} |",
        f"| Pick 1: amount broken, minutes a week (median, mean) | "
        f"{statistics.median(pick['amount'] for pick in firsts):.0f}, {statistics.mean(pick['amount'] for pick in firsts):.0f} |"
        if firsts else "| Pick 1: amount broken | none |",
        f"| Pick 1: which limits | {', '.join(f'{kind} {n}' for kind, n in kinds.most_common())} |",
        f"| Recommended timetables with a real clash | {sum(bool(pick['clashes']) for pick in picks)} / {len(picks)} |",
        f"| Template reasons passing the fact check | {rate(sum(pick['reason_passes'] for pick in picks), len(picks))} |",
    ]
    if seconds:
        lines.append(f"| Seconds for the fallback plan (median, max) | {statistics.median(seconds):.2f}, {max(seconds):.2f} |")
    lines += ["", "Amounts are minutes a week: class time inside avoided times, class time over a daily limit, "
              "missed lunch breaks; one extra campus day counts as 180 min and one class with too few seats as "
              "60 min (uniplan/nearest.py). Pick 1 is the closest: fewest limits broken, then the least amount, "
              "then the ranking model.", "", "## Examples (first 12)", "",
              "| id | units | pick 1 says |", "| --- | --- | --- |"]
    for record in saved[:12]:
        lines.append(f"| {record['sentence_id']} | {' '.join(record['units'])} | {record['picks'][0]['reason']} |")
    left = [record for record in dead if record.get("status") != "nearest"]
    if left:
        lines += ["", "## Still a dead end", "", "| id | units | why |", "| --- | --- | --- |"]
        lines += [f"| {record['sentence_id']} | {' '.join(record['units'])} | {record.get('why', '')} |" for record in left]
    return "\n".join(lines) + "\n"


def main_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--test-file", type=Path, default=EXAM)
    args = parser.parse_args(argv)
    test_file = args.test_file.resolve()
    records = []
    with tempfile.TemporaryDirectory() as temp:
        catalog = tracked_catalog(Path(temp))
        groups = {}
        for units in UNIT_SETS:
            data = main(base_profile(units), catalog)["module_two_result"]
            groups[tuple(units)] = {unit["unit_code"]: [group["group_id"] for group in unit["groups"]
                                                        if group["default_selected"]] for unit in data["units"]}
        for index, (sentence_id, sentence, rows) in enumerate(sentences(test_file)):
            records.append(run_one(index, sentence_id, sentence, rows, catalog, groups))
            print(sentence_id, records[-1]["strict"], records[-1].get("status", ""), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    name = f"nearest_eval_{test_file.stem}"
    test_set = str(test_file.relative_to(ROOT))
    (OUT / f"{name}.json").write_text(json.dumps({"test_set": test_set, "data_note": "Sentences written by Claude; "
                                                  "not real student data.", "records": records},
                                                 ensure_ascii=False, indent=1) + "\n")
    (OUT / f"{name}.md").write_text(summary(records, test_set))
    print(f"wrote {OUT / name}.json and .md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
