"""End-to-end check: sentence -> parse() -> plan -> rank() -> reasons, against hand-written answers.

Sentences: a frozen test set, default llm/parse/data/test_claude.csv (v1; written by Claude, NOT real students). Each sentence
is planned twice on the same courses (the four committed combinations of scripts/evaluate_explain.py):
with its hand-written conditions, and with what parse() reads from the sentence. Reported:

1. sentences whose parsed conditions equal the hand-written ones (and per field);
2. among sentences planned from parsed conditions, picks that break a hand-written hard condition;
3. whether the first pick is the same under parsed and hand-written conditions;
4. seconds from sentence to recommendation (parse + plan + rank + template reasons; the Qwen
   rewrite is asynchronous on the page and not included).

    python3 scripts/evaluate_pipeline.py                                   # parse() as main runs it
    python3 scripts/evaluate_pipeline.py --linear-from claude/cool-bun-40355d
        # the plain-Python linear classifier committed on that ref, for comparison
    python3 scripts/evaluate_pipeline.py --ranker rule   # rank() without llm/rank/model.json
    python3 scripts/evaluate_pipeline.py --test-file llm/parse/data/test_claude_v2.csv
    python3 scripts/evaluate_pipeline.py --compare output/pipeline/A.json output/pipeline/B.json

Runs on this Mac only: llm/ollama.py is pointed at 127.0.0.1 unless --configured-server is given.
Writes output/pipeline/pipeline_eval_<classifier>_<ranker>_<test set>.json and .md.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

if "--configured-server" not in sys.argv:
    os.environ["UNIPLAN_OLLAMA_URL"] = "http://127.0.0.1:11434"  # before llm.ollama reads it

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import llm.parse as parsing  # noqa: E402
from evaluate_explain import TEST_SET, UNIT_SETS, base_profile, conditions_from, sentences, tracked_catalog  # noqa: E402
from llm import ollama  # noqa: E402
from llm.contracts import to_profile_fields  # noqa: E402
from llm.gpu_lock import gpu_lock  # noqa: E402
from llm.parse import linear  # noqa: E402
from llm.rank import model as rank_model  # noqa: E402
from uniplan.advisor import hard_violations, merge_conditions  # noqa: E402
from uniplan.main import main  # noqa: E402
from uniplan.profile import check_condition_fields, normalize_student_input  # noqa: E402
from uniplan.ranking import SCALES, axes_name  # noqa: E402

OUT = ROOT / "output/pipeline"
FIELDS = ("unavailable_windows", "max_days_per_week", "max_daily_minutes", "max_daily_span", "lunch",
          "in_person_only", "preferred_hours", "cares")


def normalised(conditions: dict) -> dict:
    """Comparable form: windows merged per day (a whole day ends at 1440), cares in order."""
    windows = sorted((w["weekday"], w["start_min"], 1440 if w["end_min"] >= 1439 else w["end_min"])
                     for w in conditions.get("unavailable_windows") or [])
    merged: list[list[int]] = []
    for day, start, end in windows:
        if merged and merged[-1][0] == day and start <= merged[-1][2]:
            merged[-1][2] = max(merged[-1][2], end)
        else:
            merged.append([day, start, end])
    hours = conditions.get("preferred_hours")
    lunch = conditions.get("lunch")
    return {"unavailable_windows": merged,
            "max_days_per_week": conditions.get("max_days_per_week"),
            "max_daily_minutes": conditions.get("max_daily_minutes"),
            "max_daily_span": conditions.get("max_daily_span"),
            "lunch": [lunch["start_min"], lunch["end_min"], lunch["minutes"]] if lunch else None,
            "in_person_only": bool(conditions.get("in_person_only")),
            "preferred_hours": [hours["start_min"], hours["end_min"]] if hours else None,
            "cares": list(conditions.get("cares") or [])}


def planned(conditions: dict, units: list[str], catalog, groups: dict, text: str) -> dict:
    """Plan as the page does after the student confirms everything; the shown menu and its picks."""
    result = main(merge_conditions(base_profile(units), conditions), catalog, selected_groups=groups,
                  student_text=text, cares=conditions.get("cares") or [])
    if result["status"] != "ready":
        message = (result["blockers"] or result.get("errors") or [{"message": ""}])[0]["message"]
        return {"status": result["status"], "why": message}
    ranking = result["ranking_result"]
    cares = conditions.get("cares") or list(SCALES)
    axes = axes_name(tuple(axis for axis in SCALES if axis in cares))
    menu = ranking["recommendation"]["menus"][axes]
    return {"status": "ready", "axes": axes, "picks": menu["picks"],
            "meetings": [ranking["shortlist"]["items"][cid]["meetings"] for cid in menu["picks"]]}


def run_one(index: int, sentence_id: str, text: str, rows: list[dict], catalog, groups: dict,
            classify) -> dict:
    units = UNIT_SETS[index % len(UNIT_SETS)]
    gold = conditions_from(rows)
    started = time.monotonic()
    parsed_result = parsing.parse(text, classify)
    parse_seconds = time.monotonic() - started
    # What the page applies: fields the form would accept, plus the cares in the sentence's order.
    fields, problems = check_condition_fields(to_profile_fields(parsed_result["conditions"]))
    parsed = {**fields, "cares": list(parsed_result["conditions"].get("cares") or [])}
    from_parse = planned(parsed, units, catalog, groups[tuple(units)], text)
    total_seconds = time.monotonic() - started
    from_gold = planned(gold, units, catalog, groups[tuple(units)], text)

    want, got = normalised(gold), normalised(parsed)
    record = {
        "sentence_id": sentence_id, "sentence": text, "units": units,
        "labels": [clause["label"] for clause in parsed_result["clauses"]],
        "gold_labels": [row["label"] for row in rows],
        "gold": want, "parsed": got, "dropped_by_form_rules": len(problems),
        "exact": want == got, "fields_wrong": [key for key in FIELDS if want[key] != got[key]],
        "parse_seconds": round(parse_seconds, 4), "total_seconds": round(total_seconds, 3),
        "status_parsed": from_parse["status"], "status_gold": from_gold["status"],
    }
    if from_parse["status"] == "ready":
        gold_profile, errors = normalize_student_input(merge_conditions(base_profile(units), gold))
        record["picks_parsed"] = from_parse["picks"]
        record["violations"] = ([hard_violations(meetings, gold_profile)[:3] for meetings in from_parse["meetings"]]
                                if gold_profile else None)
        if errors:
            record["gold_invalid"] = [error["message"] for error in errors]
    if from_gold["status"] == "ready":
        record["picks_gold"] = from_gold["picks"]
    return record


def rate(part: int, whole: int) -> str:
    return f"{part}/{whole} ({part / whole:.0%})" if whole else "0/0"


def stats(records: list[dict]) -> dict:
    planned_parsed = [record for record in records if record["status_parsed"] == "ready"]
    checked = [record for record in planned_parsed if record.get("violations") is not None]
    both = [record for record in records if "picks_parsed" in record and "picks_gold" in record]
    seconds = [record["total_seconds"] for record in records]
    return {
        "exact": sum(record["exact"] for record in records), "sentences": len(records),
        "checked": checked, "broken": [record for record in checked if any(record["violations"])],
        "picks": [pick for record in checked for pick in record["violations"]],
        "both": both,
        "same_first": sum(record["picks_parsed"][0] == record["picks_gold"][0] for record in both),
        "same_set": sum(set(record["picks_parsed"]) == set(record["picks_gold"]) for record in both),
        "seconds": (statistics.median(seconds), max(seconds)),
        "parse_seconds": [record["parse_seconds"] for record in records],
        "feasibility": Counter((record["status_gold"] == "ready", record["status_parsed"] == "ready")
                               for record in records),
        "wrong_fields": Counter(field for record in records for field in record["fields_wrong"]),
    }


def summary(records: list[dict], classifier: str, ranker: str, test_set: str) -> str:
    numbers = stats(records)
    exact, checked, broken, picks, both = (numbers[key] for key in ("exact", "checked", "broken", "picks", "both"))
    same_first, same_set, seconds = numbers["same_first"], numbers["same_set"], numbers["seconds"]
    parse_seconds, feasibility, wrong_fields = numbers["parse_seconds"], numbers["feasibility"], numbers["wrong_fields"]
    lines = [
        f"# End-to-end pipeline evaluation (classifier: {classifier})", "",
        f"Sentences: `{test_set}`, written by Claude (Opus 5.5) — **not real student data**. "
        "Each sentence is planned twice on the same courses: with its hand-written conditions and with what "
        "`parse()` reads. Run on this Mac only.", "",
        f"- Clause classifier: {classifier}",
        f"- Ranker: {ranker}",
        "- Reasons: template (the page asks local Qwen afterwards; not timed here)", "",
        "| | |", "| --- | --- |",
        f"| Sentences | {len(records)} |",
        f"| 1. Parsed conditions equal the hand-written ones | {rate(exact, len(records))} |",
        f"| Plannable: hand-written / parsed / both / neither | {feasibility[(True, False)] + feasibility[(True, True)]} / "
        f"{feasibility[(False, True)] + feasibility[(True, True)]} / {feasibility[(True, True)]} / {feasibility[(False, False)]} |",
        f"| 2. Planned from parsed conditions, some pick breaks a hand-written hard condition | {rate(len(broken), len(checked))} |",
        f"| — picks that break one | {rate(sum(bool(pick) for pick in picks), len(picks))} |",
        f"| 3. Same first pick (both plannable) | {rate(same_first, len(both))}; same set of picks {rate(same_set, len(both))} |",
        f"| 4. Seconds from sentence to recommendation (median, max) | {seconds[0]:.2f}, {seconds[1]:.2f} |",
        f"| — of which parse() (median, max) | {statistics.median(parse_seconds):.3f}, {max(parse_seconds):.3f} |",
        "", "Fields that differ (sentences): " + (", ".join(f"{field} {count}" for field, count in wrong_fields.most_common()) or "none"),
        "", "\"Breaks a hard condition\" is checked by `uniplan.advisor.hard_violations` (clashes, avoided times, "
        "daily class minutes, time on campus, lunch, days per week); \"only in-person classes\" is not re-checked.",
        "", "## Sentences whose picks break a hand-written hard condition", "",
        "| id | sentence | parsed vs hand-written | first problem |", "| --- | --- | --- | --- |"]
    for record in broken:
        problem = next(pick[0] for pick in record["violations"] if pick)
        lines.append(f"| {record['sentence_id']} | {record['sentence']} | {', '.join(record['fields_wrong'])} | {problem} |")
    lines += ["", "## Parsed conditions that differ (first 40)", "", "| id | fields | sentence |", "| --- | --- | --- |"]
    for record in [record for record in records if not record["exact"]][:40]:
        lines.append(f"| {record['sentence_id']} | {', '.join(record['fields_wrong'])} | {record['sentence']} |")
    return "\n".join(lines) + "\n"


def comparison(first: Path, second: Path) -> str:
    """Two saved runs side by side, plus how often their first picks differ on the same conditions."""
    runs = [json.loads(path.read_text()) for path in (first, second)]
    numbers = [stats(run["records"]) for run in runs]
    rows = [
        ("Clause classifier", *[run["classifier"] for run in runs]),
        ("Ranker", *[run["ranker"] for run in runs]),
        ("Parsed conditions equal the hand-written ones", *[rate(n["exact"], n["sentences"]) for n in numbers]),
        ("Planned from parsed conditions, some pick breaks a hand-written hard condition",
         *[rate(len(n["broken"]), len(n["checked"])) for n in numbers]),
        ("Picks that break one", *[rate(sum(bool(p) for p in n["picks"]), len(n["picks"])) for n in numbers]),
        ("Same first pick as with the hand-written conditions", *[rate(n["same_first"], len(n["both"])) for n in numbers]),
        ("Same three picks", *[rate(n["same_set"], len(n["both"])) for n in numbers]),
        ("Seconds, sentence to recommendation (median, max)",
         *[f"{n['seconds'][0]:.2f}, {n['seconds'][1]:.2f}" for n in numbers]),
    ]
    by_id = [{record["sentence_id"]: record for record in run["records"]} for run in runs]
    shared = [sid for sid in by_id[0] if "picks_gold" in by_id[0][sid] and "picks_gold" in by_id[1].get(sid, {})]
    moved = sum(by_id[0][sid]["picks_gold"][0] != by_id[1][sid]["picks_gold"][0] for sid in shared)
    lines = ["# Pipeline evaluation: two runs compared", "",
             f"Sentences: `{runs[0].get('test_set')}` (written by Claude; not real student data).", "",
             f"| | `{first.name}` | `{second.name}` |", "| --- | --- | --- |"]
    lines += [f"| {name} | {a} | {b} |" for name, a, b in rows]
    lines += ["", f"With the same hand-written conditions, the two runs put a different timetable first in "
                  f"{rate(moved, len(shared))} of the sentences both could plan."]
    return "\n".join(lines) + "\n"


def main_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--linear-from", metavar="REF",
                        help="use llm/parse/output/linear_model.json as committed on this git ref")
    parser.add_argument("--configured-server", action="store_true",
                        help="let llm/ollama.py use ~/.config/uniplan/ollama_url instead of this Mac")
    parser.add_argument("--ranker", choices=("model", "rule"), default="model",
                        help="rank() with llm/rank/model.json, or the z-score rule it falls back to")
    parser.add_argument("--compare", nargs=2, type=Path, metavar="JSON", help="compare two saved runs")
    parser.add_argument("--limit", type=int, default=0, help="only the first N sentences")
    parser.add_argument("--test-file", type=Path, default=TEST_SET,
                        help="a frozen test set with the columns of test_claude.csv (default: v1)")
    args = parser.parse_args(argv)
    if args.compare:
        target = OUT / f"compare_{args.compare[0].stem}_vs_{args.compare[1].stem}.md"
        target.write_text(comparison(*args.compare))
        print(f"wrote {target}")
        return 0

    classify, classifier, name = None, "", "runtime"
    if args.linear_from:
        blob = subprocess.run(["git", "-C", str(ROOT), "show", f"{args.linear_from}:llm/parse/output/linear_model.json"],
                              capture_output=True, text=True, check=True).stdout
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", args.linear_from],
                                capture_output=True, text=True, check=True).stdout.strip()
        classify = linear.LinearModel(json.loads(blob))
        classifier, name = f"linear model from {args.linear_from} ({commit})", "linear"
    elif parsing.RUNTIME.startswith("ollama"):
        classifier = f"{parsing.RUNTIME} via {ollama.base_url()} (linear model, then keywords, if it fails)"
    else:
        try:
            linear.load()
            classifier = "linear model (llm/parse/output/linear_model.json)"
        except (OSError, ValueError, KeyError):
            classifier = "keyword rules (llm/parse/output/linear_model.json is missing, so parse() falls back)"
        name = "keywords" if classifier.startswith("keyword") else "linear"
    trained = rank_model.load() is not None and args.ranker == "model"
    ranker = ("trained pairwise model (llm/rank/model.json)" if trained else
              "rule: minus the sum of z-scores of the cared-about features" +
              ("" if args.ranker == "rule" else " (llm/rank/model.json is missing)"))
    name += "_model" if trained else "_rule"
    rule_only = mock.patch.object(rank_model, "load", return_value=None) if args.ranker == "rule" else nullcontext()

    test_file = args.test_file.resolve()
    test_set = str(test_file.relative_to(ROOT))
    name += f"_{test_file.stem}"
    chosen = sentences(test_file)[:args.limit or None]
    records = []
    lock = gpu_lock("scripts/evaluate_pipeline.py", "mac") if parsing.RUNTIME.startswith("ollama") and not args.linear_from \
        else nullcontext()
    with tempfile.TemporaryDirectory() as temp, lock, rule_only:
        catalog = tracked_catalog(Path(temp))
        groups = {}
        for units in UNIT_SETS:
            data = main(base_profile(units), catalog)["module_two_result"]
            groups[tuple(units)] = {unit["unit_code"]: [group["group_id"] for group in unit["groups"]
                                                        if group["default_selected"]] for unit in data["units"]}
        for index, (sentence_id, text, rows) in enumerate(chosen):
            records.append(run_one(index, sentence_id, text, rows, catalog, groups, classify))
            print(f"{sentence_id} exact={records[-1]['exact']} parsed={records[-1]['status_parsed']}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"pipeline_eval_{name}.json").write_text(json.dumps({
        "classifier": classifier, "ranker": ranker, "test_set": test_set,
        "data_note": "Sentences written by Claude; not real student data.", "records": records,
    }, ensure_ascii=False, indent=1) + "\n")
    (OUT / f"pipeline_eval_{name}.md").write_text(summary(records, classifier, ranker, test_set))
    print(f"wrote {OUT}/pipeline_eval_{name}.json and .md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
