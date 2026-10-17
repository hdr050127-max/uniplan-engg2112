"""How often local Qwen's rewritten reasons pass the fact check in llm/explain.py.

Scenarios: every sentence in a test set (default llm/parse/data/test_claude.csv, v1; written by Claude, NOT real
students) with its hand-written answers as the confirmed conditions, planned on one of
four course combinations from the committed timetable snapshots. The answers are used
instead of parse() so that this measures the reasons alone.

    python3 scripts/evaluate_explain.py                        # all sentences, qwen2.5:7b
    python3 scripts/evaluate_explain.py --limit 8 --model none # template only, no model calls
    python3 scripts/evaluate_explain.py --test-file llm/parse/data/test_claude_v2.csv   # another frozen set
    python3 scripts/evaluate_explain.py --recheck output/explain/explain_eval_qwen2.5-7b_test_claude.json
        # the saved model sentences, checked again with the current rules (no model calls)

While it calls the model it holds the GPU lock of the machine llm/ollama.py uses
(llm/gpu_lock.py). Temperature 0 and seed 0 are fixed in llm/explain.py. Writes
output/explain/explain_eval_<model>[_<tag>]_<test set>.json (every scenario) and .md (summary).
"""

from __future__ import annotations

import argparse
import csv
import re
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from llm import explain as explainer  # noqa: E402
from llm import ollama  # noqa: E402
from llm.explain import allowed_values, check_reason, explain_detailed, fact_lines, facts_of  # noqa: E402
from llm.contracts import preferences_of  # noqa: E402
from llm.gpu_lock import gpu_lock, target_of_ollama  # noqa: E402
from llm.rank import contributions  # noqa: E402
from uniplan.advisor import conditions_of, hard_violations, merge_conditions  # noqa: E402
from uniplan.catalog import SnapshotCatalog  # noqa: E402
from uniplan.main import main  # noqa: E402
from uniplan.ranking import SCALES, axes_name  # noqa: E402

TEST_SET = ROOT / "llm/parse/data/test_claude.csv"  # v1; the default everywhere
OUT = ROOT / "output/explain"
UNIT_SETS = (["ENGG2112", "AMME2301"], ["ENGG2112", "CIVL3206"], ["AMME2301", "CIVL3206", "ENGG2112"],
             ["AMME2262", "AMME2301", "CIVL3206", "ENGG2112"])
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# Words that name each ranking feature (llm/rank/features.py), most specific first.
FEATURE_WORDS = (("single_class_days", r"一节课"), ("building_changes", r"换.{0,2}楼"), ("friday_free", r"周五"),
                 ("earliest_start", r"最早"), ("latest_end", r"最晚|下课"),
                 ("longest_day_h", r"最久|最长的一天|在校.{0,6}一天"), ("heaviest_day_h", r"课最多的一天"),
                 ("outside_h", r"早晚课|以外的课"), ("early_h", r"早课"), ("late_h", r"晚课"),
                 ("gap_h", r"等|空档"), ("campus_days", r"到校|来学校|天数"), ("online_share", r"线上"))
ROUTINE = re.compile(r"每周固定|平时不用到校")


def main_feature(text: str | None) -> str | None:
    """The feature a reason names first, before its description of the weekly routine."""
    if not text:
        return None
    head = ROUTINE.split(text, maxsplit=1)[0]
    found = [(match.start(), name) for name, words in FEATURE_WORDS for match in [re.search(words, head)] if match]
    return min(found)[1] if found else None


def biggest_difference(picks: list[dict], conditions: dict, sentence: str, pool: list[dict]) -> list[tuple[str, float]]:
    """Pick 1's contributions minus pick 2's (llm.rank.contributions), biggest first."""
    prefs = preferences_of(conditions, sentence)
    first, second = (contributions(pick, prefs, pool) for pick in picks[:2])
    return sorted(((name, first[name] - second[name]) for name in first), key=lambda item: -item[1])


CARE_OF = {"prefer_fewer_days": "campus_days", "prefer_less_waiting": "gap", "prefer_no_early_late": "outside_hours"}


def _minutes(text: str) -> int:
    hour, minute = text.split(":")
    return int(hour) * 60 + int(minute)


def _span(text: str) -> tuple[int, int]:
    start, end = text.split("-")
    return _minutes(start), _minutes(end)


def _days(text: str) -> list[int]:
    days = []
    for part in text.split(","):
        first, _, last = part.partition("-")
        days += range(DAYS.index(first) + 1, DAYS.index(last or first) + 2)
    return days


def conditions_from(rows: list[dict[str, str]]) -> dict:
    """The hand-written answers for one sentence, in the llm.contracts.Conditions shape."""
    conditions: dict = {"unavailable_windows": [], "cares": []}
    for row in rows:
        for part in filter(None, row["block"].split("; ")):
            day_text, time_text = part.split(" ")
            start, end = (0, 1440) if time_text == "all" else _span(time_text)
            conditions["unavailable_windows"] += [{"weekday": day, "start_min": start, "end_min": end}
                                                  for day in _days(day_text)]
        if row["max_days"]:
            conditions["max_days_per_week"] = int(row["max_days"])
        if row["max_class_hours"]:
            conditions["max_daily_minutes"] = round(float(row["max_class_hours"]) * 60)
        if row["max_campus_hours"]:
            conditions["max_daily_span"] = round(float(row["max_campus_hours"]) * 60)
        if row["lunch"]:
            window, need = row["lunch"].split(" ")
            start, end = _span(window)
            conditions["lunch"] = {"start_min": start, "end_min": end, "minutes": int(need)}
        if row["label"] == "in_person_only":
            conditions["in_person_only"] = True
        if row["prefer_hours"]:
            start, end = _span(row["prefer_hours"])
            conditions["preferred_hours"] = {"weekday": 1, "start_min": start, "end_min": end}
        care = CARE_OF.get(row["label"])
        if care and care not in conditions["cares"]:
            conditions["cares"].append(care)
    return conditions


def sentences(test_file: Path = TEST_SET) -> list[tuple[str, str, list[dict[str, str]]]]:
    """(sentence_id, sentence, clause rows); a row without an id continues the sentence above."""
    found: list[tuple[str, str, list[dict[str, str]]]] = []
    with test_file.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["sentence_id"]:
                found.append((row["sentence_id"], row["sentence"], []))
            found[-1][2].append(row)
    return found


def tracked_catalog(folder: Path) -> SnapshotCatalog:
    """Only the committed snapshots, so every machine plans on the same data."""
    names = subprocess.run(["git", "-C", str(ROOT), "ls-files", "data/processed"],
                           capture_output=True, text=True, check=True).stdout.split()
    (folder / "processed").mkdir()
    for name in names:
        shutil.copy(ROOT / name, folder / "processed")
    return SnapshotCatalog(folder / "processed", folder / "requirements")


def base_profile(units: list[str]) -> dict:
    return {"schema_version": 1, "year": 2026, "session_code": "S2C", "unit_codes": units, "unavailable_windows": []}


def run_one(index: int, sentence_id: str, sentence: str, rows: list[dict[str, str]], catalog: SnapshotCatalog,
            groups: dict, model: str | None, saved: dict | None = None) -> dict:
    """Plan one scenario and explain its picks; with ``saved``, reuse that run's model sentences."""
    units = UNIT_SETS[index % len(UNIT_SETS)]
    conditions = conditions_from(rows)
    record = {"sentence_id": sentence_id, "sentence": sentence, "units": units, "conditions": conditions}
    result = main(merge_conditions(base_profile(units), conditions), catalog,
                  selected_groups=groups[tuple(units)], student_text=sentence, cares=conditions["cares"])
    record["status"] = result["status"]
    if result["status"] != "ready":
        record["why"] = (result["blockers"] or result.get("errors") or [{"message": ""}])[0]["message"]
        return record
    ranking = result["ranking_result"]
    items = ranking["shortlist"]["items"]
    axes = axes_name(tuple(axis for axis in SCALES if axis in (conditions["cares"] or SCALES)))
    menu = ranking["recommendation"]["menus"][axes]
    picks = [items[cid] for cid in menu["picks"]]
    confirmed = conditions_of(result["profile"], axes.split(","), conditions["cares"])
    pool = ranking["recommendation"]["_candidates"][axes]
    started = time.monotonic()
    texts = [pick.get("model_text") for pick in (saved or {}).get("picks", [])]
    same_picks = saved is not None and [pick["candidate_id"] for pick in saved.get("picks", [])] == menu["picks"]
    if saved is None:
        written = explain_detailed(sentence, confirmed, picks, model=model, candidates=pool)
    elif same_picks and texts and all(texts):
        # The planner is deterministic, so these are the same picks the model wrote about.
        with mock.patch.object(explainer, "ask_model", return_value=texts):
            written = explain_detailed(sentence, confirmed, picks, model=model, candidates=pool)
    else:
        written = explain_detailed(sentence, confirmed, picks, model=None, candidates=pool)
        written["status"] = "not rechecked" if not same_picks else saved.get("explain_status", "template")
    seconds = saved.get("seconds", 0) if saved else round(time.monotonic() - started, 2)
    record.update(axes=axes, candidates=len(menu["candidates"]), seconds=seconds,
                  explain_status=written["status"], picks=[])
    if len(picks) > 1:
        differences = biggest_difference(picks, confirmed, sentence, pool)
        record["differences"] = [[name, round(value, 3)] for name, value in differences[:3]]
        record["main_feature"] = differences[0][0]
        record["template_feature"] = main_feature(menu["reasons"][0])
        record["shown_feature"] = main_feature(written["reasons"][0])
    for position, (pick, template) in enumerate(zip(picks, menu["reasons"])):
        facts = facts_of(position, picks, confirmed, pool)
        allowed = allowed_values([f"{facts['count']} 份", *fact_lines(facts)])
        record["picks"].append({
            "candidate_id": pick["candidate_id"], "pattern": pick["pattern"],
            "violations": hard_violations(pick["meetings"], result["profile"]),
            "features": {key: round(value, 1) for key, value in pick["features"].items()},
            "facts": fact_lines(facts), "template": template,
            "template_passes": check_reason(template, facts, allowed, first=position == 0) is None,
            "model_text": written["rejected"].get(position, {}).get("text") or (
                written["reasons"][position] if written["by"][position] != "template" else None),
            "model_passed": written["by"][position] != "template",
            "rejected_why": written["rejected"].get(position, {}).get("why"),
        })
    return record


def summary(records: list[dict], model: str | None, note: str = "", test_set: str = "llm/parse/data/test_claude.csv") -> str:
    ready = [record for record in records if record["status"] == "ready"]
    picks = [(position, pick) for record in ready for position, pick in enumerate(record["picks"])]
    asked = [(position, pick) for position, pick in picks if pick["model_text"] is not None]
    passed = [(position, pick) for position, pick in asked if pick["model_passed"]]
    template_ok = sum(pick["template_passes"] for _, pick in picks)
    statuses = Counter(record["explain_status"] for record in ready)
    reasons = Counter(pick["rejected_why"] for _, pick in asked if not pick["model_passed"])
    seconds = [record["seconds"] for record in ready if record["explain_status"] not in ("template",)]
    compared = [record for record in ready if record.get("main_feature")]

    def rate(part: int, whole: int) -> str:
        return f"{part}/{whole} ({part / whole:.0%})" if whole else "0/0"

    lines = [
        f"# Reason fact-check evaluation ({model or 'template only'})", "",
        f"Sentences: `{test_set}`, written by Claude (Opus 5.5) — **not real student data**. "
        "Conditions are the file's hand-written answers (not `parse()` output); timetables come from the "
        "committed 2026 S2C snapshots. Model output was produced with temperature 0 and seed 0." + note, "",
        "| | |", "| --- | --- |",
        f"| Sentences | {len(records)} |",
        f"| Planned (feasible) | {len(ready)}; not planned: {dict(Counter(r['status'] for r in records if r['status'] != 'ready'))} |",
        f"| Recommended timetables | {len(picks)}; with a time clash or a broken hard condition: "
        f"{sum(bool(pick['violations']) for _, pick in picks)} |",
        f"| Template reasons passing the checker | {rate(template_ok, len(picks))} |",
        f"| Pick 1: main reason = the model's biggest difference from pick 2, template | "
        f"{rate(sum(r['template_feature'] == r['main_feature'] for r in compared), len(compared))} |",
        f"| — the reason shown (model rewrite if it passed, else template) | "
        f"{rate(sum(r['shown_feature'] == r['main_feature'] for r in compared), len(compared))} |",
        f"| Model sentences returned | {len(asked)} (requests by status: {dict(statuses)}) |",
        f"| Model sentences that passed and were shown | {rate(len(passed), len(asked))} |",
    ]
    for position in range(3):
        mine = [pick for spot, pick in asked if spot == position]
        lines.append(f"| — pick {position + 1} | {rate(sum(pick['model_passed'] for pick in mine), len(mine))} |")
    if seconds:
        lines.append(f"| Seconds per request (median, max) | {statistics.median(seconds):.1f}, {max(seconds):.1f} |")
    lines += ["", "Rejected, by first failed check: " + (", ".join(f"{why} {count}" for why, count in reasons.most_common())
                                                     or "none"), "",
              "The checker's rules were refined after spot-checking earlier runs on these same sentences, "
              "so this pass rate is in-sample and likely optimistic for new sentences.", "",
              "Passing means every claim the checker can read (weekdays, clock times, amounts with units, "
              "best-of-picks and comparison words, topics it has no facts for) matched the timetable. "
              "Claims it cannot read are not verified, so the passed sentences below should be spot-checked by a person.", "",
              "## Passed model sentences (first 20)", "", "| id | pick | model sentence | template it rewrote |", "| --- | --- | --- | --- |"]
    shown = 0
    for record in ready:
        for position, pick in enumerate(record["picks"]):
            if pick["model_passed"] and shown < 20:
                lines.append(f"| {record['sentence_id']} | {position + 1} | {pick['model_text']} | {pick['template']} |")
                shown += 1
    lines += ["", "## Rejected model sentences (first 30)", "", "| id | pick | why | model sentence |", "| --- | --- | --- | --- |"]
    shown = 0
    for record in ready:
        for position, pick in enumerate(record["picks"]):
            if pick["model_text"] is not None and not pick["model_passed"] and shown < 30:
                lines.append(f"| {record['sentence_id']} | {position + 1} | {pick['rejected_why']} | {pick['model_text']} |")
                shown += 1
    return "\n".join(lines) + "\n"


def main_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default="qwen2.5:7b", help='Ollama model, or "none" for the template only')
    parser.add_argument("--limit", type=int, default=0, help="only the first N sentences")
    parser.add_argument("--recheck", type=Path, help="a saved result file: check its model sentences again")
    parser.add_argument("--tag", default="", help="suffix for the output file names, e.g. before")
    parser.add_argument("--test-file", type=Path, default=TEST_SET,
                        help="a frozen test set with the columns of test_claude.csv (default: v1)")
    args = parser.parse_args(argv)
    model = None if args.model == "none" else args.model
    saved, server, note = {}, None, ""
    if args.recheck:
        previous = json.loads(args.recheck.read_text())
        model, server = previous["model"], previous["server"]
        args.test_file = ROOT / previous.get("test_set", TEST_SET.relative_to(ROOT))  # the sentences it was run on
        saved = {record["sentence_id"]: record for record in previous["records"]}
        note = (f" The model sentences come from an earlier run against {server} and were checked again with "
                "the current rules, without calling the model.")
    elif model and not ollama.available(model):
        print(f"{model} is not available on {ollama.base_url()}; see python3 -m llm.ollama", file=sys.stderr)
        return 1
    test_file = args.test_file.resolve()
    chosen = sentences(test_file)[:args.limit or None]
    records = []
    with tempfile.TemporaryDirectory() as temp:
        catalog = tracked_catalog(Path(temp))
        groups = {}
        for units in UNIT_SETS:
            data = main(base_profile(units), catalog)["module_two_result"]
            groups[tuple(units)] = {unit["unit_code"]: [group["group_id"] for group in unit["groups"]
                                                        if group["default_selected"]] for unit in data["units"]}
        calls_model = model and not args.recheck
        lock = gpu_lock("scripts/evaluate_explain.py", target_of_ollama()) if calls_model else nullcontext()
        with lock:
            for index, (sentence_id, sentence, rows) in enumerate(chosen):
                records.append(run_one(index, sentence_id, sentence, rows, catalog, groups, model,
                                       saved.get(sentence_id) if args.recheck else None))
                print(f"{sentence_id} {records[-1]['status']} {records[-1].get('explain_status', '')}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    name = (f"explain_eval_{(model or 'template').replace(':', '-')}" + (f"_{args.tag}" if args.tag else "") +
            f"_{test_file.stem}")
    if model and not args.recheck:
        server = ollama.base_url()
    (OUT / f"{name}.json").write_text(json.dumps({"model": model, "server": server, "rechecked": bool(args.recheck),
                                                   "test_set": str(test_file.relative_to(ROOT)),
                                                   "data_note": "Sentences written by Claude; not real student data.",
                                                   "records": records}, ensure_ascii=False, indent=1) + "\n")
    (OUT / f"{name}.md").write_text(summary(records, model, note, str(test_file.relative_to(ROOT))))
    print(f"wrote {OUT / name}.json and .md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
