"""Teacher labels: a local Qwen plays a persona and picks the better of two real timetables.

SYNTHETIC: the personas are synthetic and the labels come from an LLM imitating them,
not from real students. Every output file says so.

Prompt version 3 (after the pilot in llm/rank/pilot.py, 22/30 consistent in version 2):
- early/late classes are counted against the persona's own comfortable hours
  (``preferred_hours``), not a fixed 09:00-18:00;
- when the two timetables are almost equal on the persona's main concern (``focus``,
  i.e. ``cares[0]``), the program records a tie and the model is not asked;
- the model must pick red or blue; every pair is asked twice with the sides swapped and
  only answers that agree become labels.

``--ties hint`` is a variant for comparison: a near-equal main concern is no longer a tie by
itself. The program tells the model that this item is a draw and lets it decide on the
rest; only when every row of the table is near-equal does the program call a tie.

    python3 -m llm.rank.label pilot --model qwen2.5:7b      # the pilot's 30 pairs, version 3
    python3 -m llm.rank.label run --model qwen2.5:14b       # ~1,500 pairs over 80 personas

The server comes from llm.ollama (the shared address file, or this Mac). Wrap every batch in
``python3 -m llm.gpu_lock --`` so batches from other windows queue on the same machine.
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
import threading
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llm import ollama  # noqa: E402
from llm.rank.features import hours_of, routine_bounds, teaching_weeks, timetable_features  # noqa: E402
from llm.rank.personas import PILOT_IDS, load  # noqa: E402

OUT = ROOT / "llm" / "rank" / "output"
PROMPT_VERSION = 3
SEED = 2112
DAYS = "一二三四五六日"

# A difference smaller than this on the persona's main concern is a tie, decided by the program.
TIE = {"campus_days": ("campus_days", 0.25), "gap": ("gap_h", 0.5), "outside_hours": ("outside_h", 0.5)}
# "hint" mode: a pair is a program tie only if every table row is this close.
NEAR = {"campus_days": 0.25, "gap_h": 0.5, "outside_h": 0.5, "earliest_start": 0.5, "latest_end": 0.5,
        "longest_day_h": 0.5, "single_class_days": 0.25}
FOCUS_ROW = {"campus_days": "到校天数", "gap": "空等", "outside_hours": "早晚课"}
ROWS = ("到校天数", "空等", "早晚课", "最早上课", "最晚下课", "最长的一天", "只为一节课到校")
SYSTEM = ("你要扮演一位大学生，根据他自己的情况，从“红”“蓝”两份课表里选更适合他的一份。"
          "先说出对这位学生最重要的是哪一项（focus），再对照表格里这一项的数字说理由，最后选红或蓝。"
          "数字越小越好的项：到校天数、空等、早晚课、最长的一天、只为一节课到校。"
          "表格里的早晚课已经按这位学生自己方便的时段算好，直接用表里的数字。")
SCHEMA = {"type": "object", "properties": {
    "focus": {"type": "string", "enum": list(ROWS)},
    # The cap stops a model that keeps writing inside the string (14B looped there without it).
    "reason": {"type": "string", "maxLength": 150}, "choice": {"type": "string", "enum": ["红", "蓝"]}},
    "required": ["focus", "reason", "choice"]}
TRAIN_PAIRS, TEST_SET = 16, 8   # pairs per training persona; candidates per test persona (all 28 pairs)


def clock(minutes: float) -> str:
    minutes = round(minutes)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def table_values(features: dict[str, float]) -> dict[str, str]:
    return {"到校天数": f"{features['campus_days']:.1f}", "空等": f"{features['gap_h']:.1f}",
            "早晚课": f"{features['outside_h'] * 60:.0f}", "最早上课": clock(features["earliest_start"] * 60),
            "最晚下课": clock(features["latest_end"] * 60), "最长的一天": f"{features['longest_day_h']:.1f}",
            "只为一节课到校": f"{features['single_class_days']:.1f}"}


def row_labels(hours: dict[str, int]) -> dict[str, str]:
    return {"到校天数": "到校天数（天/周）", "空等": "课间空等（小时/周）",
            "早晚课": f"早晚课：{clock(hours['start_min'])} 前或 {clock(hours['end_min'])} 后（分钟/周）",
            "最早上课": "最早上课", "最晚下课": "最晚下课", "最长的一天": "最长的一天（在校小时）",
            "只为一节课到校": "只为一节课到校（天/周）"}


def routine_text(meetings: list[dict]) -> str:
    """The weekly routine (classes repeating in at least three weeks), one line per weekday."""
    weeks = Counter((m["weekday"], m["start_min"], m["end_min"], m["unit_code"],
                     m["group_id"].split("|")[-1], m["is_online"]) for m in meetings)
    routine = sorted(key for key, count in weeks.items() if count >= 3)
    lines = []
    for day in range(1, 8):
        today = [slot for slot in routine if slot[0] == day]
        if day > 5 and not today:
            continue
        lessons = "；".join(f"{clock(s)}–{clock(e)} {unit} {activity}{'（线上）' if online else ''}"
                           for _, s, e, unit, activity, online in today)
        lines.append(f"周{DAYS[day - 1]}：{lessons or '没课'}")
    return "\n".join(lines)


def prepare(candidates: list[dict], persona: dict) -> list[dict]:
    """Attach the 13 ranking features (personal hours), table values and routine text."""
    weeks, hours = teaching_weeks(candidates), hours_of(persona["conditions"])
    for candidate in candidates:
        candidate["x"] = timetable_features(candidate["meetings"], weeks, hours)
        candidate["table"] = table_values(candidate["x"])
        candidate["text"] = routine_text(candidate["meetings"])
    return candidates


def program_tie(persona: dict, a: dict, b: dict) -> bool:
    key, threshold = TIE[persona["focus"]]
    return abs(a["x"][key] - b["x"][key]) < threshold


def all_near(a: dict, b: dict) -> bool:
    return all(abs(a["x"][key] - b["x"][key]) < threshold for key, threshold in NEAR.items())


def table_text(persona: dict, red: dict, blue: dict) -> str:
    labels = row_labels(hours_of(persona["conditions"]))
    rows = "\n".join(f"| {labels[row]} | {red['table'][row]} | {blue['table'][row]} |" for row in ROWS)
    return f"| 项目 | 红 | 蓝 |\n| --- | --- | --- |\n{rows}"


def question(persona: dict, red: dict, blue: dict, draw: bool = False) -> str:
    """Exactly what the model is shown about one pair."""
    row = FOCUS_ROW[persona["focus"]]
    note = (f"\n\n注意：两份课表的“{row}”几乎一样（红 {red['table'][row]}，蓝 {blue['table'][row]}），"
            f"这一项分不出高下。请根据这位学生的其他情况和表里的其他项来选，focus 填你据以决定的那一项。"
            if draw else "")
    return (f"学生情况：{persona['text']}\n\n{table_text(persona, red, blue)}{note}\n\n"
            f"红课表（每周固定的课）：\n{red['text']}\n\n蓝课表（每周固定的课）：\n{blue['text']}")


def ask(model: str, persona: dict, red: dict, blue: dict, draw: bool = False) -> dict:
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question(persona, red, blue, draw)}]
    for limit in (500, 1200):   # a long reason can hit the token limit and cut the JSON short
        try:
            return json.loads(ollama.chat(model, messages, schema=SCHEMA,
                                          options={"num_predict": limit, "num_ctx": 4096}))
        except json.JSONDecodeError:
            continue
    raise ValueError(f"{model} gave no complete answer for {persona['id']}")


def judge(model: str, persona: dict, a: dict, b: dict, ties: str = "strict") -> dict:
    """One labelled pair. ``label`` is A, B, tie (program) or flip (the two orders disagree)."""
    record = {"persona": persona["id"], "split": persona["split"], "focus": persona["focus"],
              "a_id": a["candidate_id"], "b_id": b["candidate_id"], "a_x": a["x"], "b_x": b["x"],
              "model": model, "prompt_version": PROMPT_VERSION, "ties": ties, "synthetic": True}
    draw = program_tie(persona, a, b)
    if draw and (ties == "strict" or all_near(a, b)):
        return {**record, "label": "tie", "source": "program"}
    started = time.time()
    forward = ask(model, persona, a, b, draw)    # red = A
    swapped = ask(model, persona, b, a, draw)    # red = B
    first = {"红": "A", "蓝": "B"}[forward["choice"]]
    second = {"红": "B", "蓝": "A"}[swapped["choice"]]
    return {**record, "label": first if first == second else "flip", "source": "model",
            "forward": forward, "swapped": swapped, "first": first, "second": second,
            "draw_hint": draw,
            "focus_ok": [FOCUS_ROW[persona["focus"]] == answer["focus"] for answer in (forward, swapped)],
            "seconds": round(time.time() - started, 2)}


def free_other_models(model: str) -> None:
    """One model per batch: unload any other model the server holds in GPU memory."""
    try:
        with urllib.request.urlopen(f"{ollama.base_url()}/api/ps", timeout=5) as response:
            loaded = [item["name"] for item in json.loads(response.read())["models"]]
    except (OSError, ValueError, KeyError):
        return
    for name in loaded:
        if name != model:
            print(f"unloading {name} to leave the GPU to {model}", flush=True)
            ollama.unload(name)


def run_jobs(model: str, jobs: list[tuple[dict, dict, dict]], path: Path, workers: int,
             ties: str = "strict") -> list[dict]:
    """Judge every (persona, a, b), appending each result to ``path`` as it finishes (resumable)."""
    done = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            done[(row["persona"], row["a_id"], row["b_id"])] = row
    todo = [job for job in jobs if (job[0]["id"], job[1]["candidate_id"], job[2]["candidate_id"]) not in done]
    print(f"{len(jobs)} pairs, {len(jobs) - len(todo)} already labelled, model {model} at {ollama.base_url()}",
          flush=True)
    lock, started, finished = threading.Lock(), time.time(), [0]

    def work(job):
        row = judge(model, *job, ties=ties)
        with lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            done[(row["persona"], row["a_id"], row["b_id"])] = row
            finished[0] += 1
            if finished[0] % 20 == 0 or finished[0] == len(todo):
                rate = (time.time() - started) / finished[0]
                print(f"  {finished[0]}/{len(todo)}  {rate:.1f}s per pair, "
                      f"~{rate * (len(todo) - finished[0]) / 60:.0f} min left", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, todo))
    return [done[(p["id"], a["candidate_id"], b["candidate_id"])] for p, a, b in jobs]


def report(rows: list[dict]) -> dict:
    asked = [row for row in rows if row["source"] == "model"]
    agree = [row for row in asked if row["label"] != "flip"]
    plain = [row for row in asked if not row.get("draw_hint")]
    first = Counter(answer["choice"] for row in asked for answer in (row["forward"], row["swapped"]))
    return {
        "pairs": len(rows), "program_ties": len(rows) - len(asked), "asked_model": len(asked),
        "consistent_all": f"{len(rows) - len(asked) + len(agree)}/{len(rows)}",
        "consistent_rate_all": round((len(rows) - len(asked) + len(agree)) / max(len(rows), 1), 3),
        "consistent_rate_asked": round(len(agree) / max(len(asked), 1), 3),
        "answers_by_position": {"red(first)": first["红"], "blue(second)": first["蓝"]},
        "focus_correct": f"{sum(ok for row in plain for ok in row['focus_ok'])}/{2 * len(plain)}",
        "draw_hint_pairs": f"{sum(r['label'] != 'flip' for r in asked if r.get('draw_hint'))}/"
                           f"{sum(bool(r.get('draw_hint')) for r in asked)} consistent",
        "by_focus": {focus: f"{sum(r['label'] != 'flip' for r in rows if r['focus'] == focus)}/"
                            f"{sum(r['focus'] == focus for r in rows)}"
                     for focus in sorted({r["focus"] for r in rows})},
        "seconds_per_asked_pair": round(sum(r["seconds"] for r in asked) / max(len(asked), 1), 2),
    }


# ---------------------------------------------------------------- pilot, version 3
def pilot_jobs() -> list[tuple[dict, dict, dict]]:
    """The exact 30 pairs of pilot version 2, shown with the version 3 prompt and tie rule."""
    from llm.rank import pool
    personas = {p["id"]: p for p in load()}
    v2 = json.loads((OUT / "rank_pilot_v2.json").read_text(encoding="utf-8"))["records"]
    jobs = []
    for pilot_id, persona_id in PILOT_IDS.items():
        persona = personas[persona_id]
        # Version 2 built the pool with the hard windows only; rebuild it the same way so the
        # candidate ids (hashes of the class lists) match, then measure with personal hours.
        v2_persona = {"id": f"v2:{pilot_id}", "units": persona["units"],
                      "conditions": {"unavailable_windows": persona["conditions"].get("unavailable_windows", []),
                                     "cares": persona["conditions"]["cares"]}}
        entries = {e["candidate_id"]: e for e in pool.persona_pool(v2_persona)}
        records = [r for r in v2 if r["persona"] == pilot_id]
        needed = [entries[i] for i in dict.fromkeys(i for r in records for i in (r["a_id"], r["b_id"]))]
        whole = prepare(pool.materialize(v2_persona, list(entries.values())), persona)
        by_id = {c["candidate_id"]: c for c in whole}
        assert len(needed) == len({i for r in records for i in (r["a_id"], r["b_id"])})
        jobs += [(persona, by_id[r["a_id"]], by_id[r["b_id"]]) for r in records]
    return jobs


# ---------------------------------------------------------------- the full run
def full_jobs(seed: int = SEED) -> tuple[list[tuple[dict, dict, dict]], dict]:
    """Training personas: up to 16 pairs from their candidate set, non-ties first.
    Test personas: every pair among their first 8 candidates, so a teacher top 3 exists."""
    from llm.rank import pool
    jobs, sets = [], {}
    for persona in load():
        rng = random.Random(f"{seed}:{persona['id']}")
        candidates = prepare(pool.candidate_set(persona, rng), persona)
        if persona["split"] == "test":
            chosen = candidates[:TEST_SET]
            pairs = list(itertools.combinations(chosen, 2))
        else:
            chosen = candidates
            pairs = list(itertools.combinations(chosen, 2))
            rng.shuffle(pairs)
            pairs.sort(key=lambda pair: program_tie(persona, *pair))      # stable: non-ties first
            pairs = pairs[:TRAIN_PAIRS]
        pairs = [(a, b) if rng.random() < 0.5 else (b, a) for a, b in pairs]
        jobs += [(persona, a, b) for a, b in pairs]
        sets[persona["id"]] = [{"candidate_id": c["candidate_id"], "option_ids": c["option_ids"],
                                "pattern": c["pattern"], "x": c["x"], "table": c["table"], "text": c["text"]}
                               for c in chosen]
    return jobs, sets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("pilot", "run"))
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--workers", type=int, default=1, help="requests in flight at once")
    parser.add_argument("--ties", choices=("strict", "hint"), default="strict",
                        help="strict: near-equal main concern is a tie; hint: tell the model and let it decide")
    parser.add_argument("--limit", type=int, default=0, help="only the first N pairs (a quick check)")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    tag = args.model.replace(":", "_")
    if args.mode == "pilot":
        jobs, name = pilot_jobs(), f"rank_pilot_v3{'h' if args.ties == 'hint' else ''}_{tag}"
    else:
        jobs, sets = full_jobs()
        name = f"labels_v3{'h' if args.ties == 'hint' else ''}_{tag}"
        (OUT / "candidate_sets.json").write_text(json.dumps(
            {"note": "合成数据：80 个合成画像的候选课表（真实课表快照排出的可行课表）与特征。", "seed": SEED,
             "sets": sets}, ensure_ascii=False), encoding="utf-8")
    if args.limit:
        jobs = jobs[:args.limit]
    free_other_models(args.model)
    rows = run_jobs(args.model, jobs, OUT / f"{name}.jsonl", args.workers, args.ties)
    summary = {"note": "合成标签（SYNTHETIC）：由大模型扮演合成画像给出，不是真实学生的选择。",
               "model": args.model, "server": ollama.base_url(), "prompt_version": PROMPT_VERSION,
               "ties": args.ties,
               "tie_thresholds": {k: v[1] for k, v in TIE.items()}, **report(rows)}
    if args.mode == "pilot":
        summary["by_persona"] = {p: f"{sum(r['label'] != 'flip' for r in rows if r['persona'] == p)}/"
                                    f"{sum(r['persona'] == p for r in rows)}" for p in PILOT_IDS.values()}
    (OUT / f"{name}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
