"""The final exam for the ranking block: new personas, new answers, frozen models, one sitting.

A fresh annotator (a new sub-agent, not Qwen and not the coordinator) writes new test personas
and answers pairwise questions about their timetables. Nothing here trains or tunes anything:
the shipped llm/rank/model.json and the rule baselines are scored as they are. SYNTHETIC: the
exam personas and answers are AI-written; the report says so.

1. The annotator writes exam/personas.json:
       {"personas": [{"id": "x01", "text": "one sentence", "units": ["ENGG2112", "AMME2301"],
                      "conditions": {..., "cares": ["gap", ...], "preferred_hours": {...}}}, ...]}
   ``conditions`` uses the llm.contracts.Conditions format; ``cares`` is ordered, most important first.
2. Questions (no answers anywhere; the key only says which timetable is shown as red):
       python3 -m llm.rank.exam prepare
   -> exam/questions.jsonl (give this to the annotator), exam/key.json, exam/candidates.json
3. The annotator writes exam/answers.jsonl: one {"pair_id": ..., "choice": "红" | "蓝" | "差不多"} per line.
4. Score once (the 14B part needs the Windows GPU, so wrap it in the lock):
       python3 -m llm.gpu_lock -- python3 -m llm.rank.exam score --llm qwen2.5:14b
   -> llm/rank/output/exam_report.json and exam_report.md. Scoring refuses to run twice unless
      --again is given (and the report then records that it was rerun).
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, pstdev

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llm.rank import model as runtime  # noqa: E402
from llm.rank.metrics import membership, teacher_order  # noqa: E402

EXAM = ROOT / "llm" / "rank" / "exam"
OUT = ROOT / "llm" / "rank" / "output"
SEED = "exam-2112"
PER_PERSONA = 8            # candidates per persona; every pair among them is a question
CARE_FEATURE = {"campus_days": "campus_days", "gap": "gap_h", "outside_hours": "outside_h"}
BASE = ("campus_days", "gap_h", "outside_h")
CONDITION_KEYS = {"unavailable_windows", "max_days_per_week", "max_daily_minutes", "max_daily_span", "lunch",
                  "in_person_only", "preferred_hours", "cares"}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check_persona(raw: dict) -> dict:
    """Validate one exam persona and give it the fields the labelling code expects."""
    if not isinstance(raw.get("id"), str) or not raw.get("text") or not raw.get("units"):
        raise ValueError(f"persona needs id, text and units: {raw}")
    conditions = raw.get("conditions") or {}
    unknown = set(conditions) - CONDITION_KEYS
    cares = conditions.get("cares") or []
    if unknown or not cares or any(care not in CARE_FEATURE for care in cares):
        raise ValueError(f"{raw['id']}: bad conditions (unknown {sorted(unknown)}, cares {cares})")
    return {"id": f"exam:{raw['id']}", "exam_id": raw["id"], "type": raw.get("type", "exam"), "text": raw["text"],
            "units": list(raw["units"]), "conditions": conditions, "focus": cares[0], "split": "exam",
            "synthetic": True}


def prepare(folder: Path = EXAM) -> dict:
    """Build the questions from the annotator's personas. Needs uniplan (the scheduler)."""
    from llm.rank import pool
    from llm.rank.label import SYSTEM, prepare as attach, table_text
    personas = [check_persona(p) for p in json.loads((folder / "personas.json").read_text(encoding="utf-8"))["personas"]]
    if len({p["exam_id"] for p in personas}) != len(personas):
        raise ValueError("persona ids must be unique")
    questions, key, candidates_out, skipped = [], {}, {}, []
    pending = []
    for persona in personas:
        try:
            chosen = pool.candidate_set(persona, random.Random(f"{SEED}:{persona['exam_id']}"))[:PER_PERSONA]
        except Exception as error:  # noqa: BLE001 - an unschedulable persona is reported, not fatal
            skipped.append({"persona": persona["exam_id"], "reason": f"{type(error).__name__}: {error}"})
            continue
        if len(chosen) < 3:
            skipped.append({"persona": persona["exam_id"], "reason": f"only {len(chosen)} distinct timetables"})
            continue
        attach(chosen, persona)
        candidates_out[persona["exam_id"]] = [{"candidate_id": c["candidate_id"], "x": c["x"], "table": c["table"],
                                               "text": c["text"], "option_ids": c["option_ids"]} for c in chosen]
        pending += [(persona, a, b) for a, b in itertools.combinations(chosen, 2)]
    rng = random.Random(SEED)
    sides = [True] * (len(pending) // 2) + [False] * (len(pending) - len(pending) // 2)
    rng.shuffle(sides)
    order = list(range(len(pending)))
    rng.shuffle(order)                                   # personas interleaved
    for number, index in enumerate(order, start=1):
        persona, a, b = pending[index]
        red, blue = (a, b) if sides[index] else (b, a)
        pair_id = f"x{number:04d}"
        hours = persona["conditions"].get("preferred_hours") or {"start_min": 540, "end_min": 1080}
        questions.append({"pair_id": pair_id, "persona_id": persona["exam_id"], "persona": persona["text"],
                          "comfortable_hours": f"{hours['start_min'] // 60:02d}:{hours['start_min'] % 60:02d}–"
                                               f"{hours['end_min'] // 60:02d}:{hours['end_min'] % 60:02d}",
                          "table": table_text(persona, red, blue), "red": red["text"], "blue": blue["text"],
                          "instructions": SYSTEM + "（可以答“红”“蓝”；两份真的分不出时答“差不多”。）",
                          "synthetic": True})
        key[pair_id] = {"persona": persona["exam_id"], "a_id": a["candidate_id"], "b_id": b["candidate_id"],
                        "red": "A" if sides[index] else "B"}
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "questions.jsonl").write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in questions),
                                            encoding="utf-8")
    (folder / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    (folder / "candidates.json").write_text(json.dumps(
        {"note": "合成考卷：画像由新的子代理撰写；候选课表由排课程序从真实课表快照排出。",
         "personas": {p["exam_id"]: p for p in personas if p["exam_id"] in candidates_out},
         "candidates": candidates_out, "skipped": skipped}, ensure_ascii=False), encoding="utf-8")
    summary = {"personas": len(candidates_out), "questions": len(questions), "skipped": skipped}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary


# ------------------------------------------------------------------ the methods (all frozen)
def prefs_of(persona: dict) -> dict:
    return {"cares": persona["conditions"]["cares"], "preferred_hours": persona["conditions"].get("preferred_hours")}


def rule_scores(xs: list[dict], keys: list[str]) -> list[float]:
    stats = {k: (mean(x[k] for x in xs), pstdev([x[k] for x in xs]) or 1.0) for k in keys}
    return [-sum((x[k] - stats[k][0]) / stats[k][1] for k in keys) for x in xs]


def method_scores(persona: dict, candidates: list[dict], spec: dict) -> dict[str, list[float]]:
    xs = [c["x"] for c in candidates]
    s = runtime.student_terms(prefs_of(persona))
    cared = [CARE_FEATURE[c] for c in persona["conditions"]["cares"]]
    return {"定稿模型（model.json，逻辑回归）": [runtime.utility(x, s, spec) for x in xs],
            "等权打分": rule_scores(xs, list(BASE)),
            "按 cares 打分（原占位版）": rule_scores(xs, cared)}


def choice(scores: list[float], ids: list[str], a: str, b: str) -> str:
    sa, sb = scores[ids.index(a)], scores[ids.index(b)]
    return "A" if sa > sb else "B" if sb > sa else "tie"


def bootstrap(hits: dict[str, list[float]], rounds: int = 2000) -> list[float] | None:
    keys = [k for k in hits if hits[k]]
    if not keys:
        return None
    rng = random.Random(SEED)
    values = sorted(mean([h for k in (rng.choice(keys) for _ in keys) for h in hits[k]]) for _ in range(rounds))
    return [values[int(0.025 * rounds)], values[int(0.975 * rounds) - 1]]


def answers_as_ab(folder: Path, key: dict) -> dict[str, str]:
    result = {}
    for row in read_jsonl(folder / "answers.jsonl"):
        info = key[row["pair_id"]]
        picked = row["choice"].strip()
        if picked == "差不多":
            result[row["pair_id"]] = "tie"
        elif picked in ("红", "蓝"):
            result[row["pair_id"]] = info["red"] if picked == "红" else ("B" if info["red"] == "A" else "A")
        else:
            raise ValueError(f"{row['pair_id']}: choice must be 红, 蓝 or 差不多, not {picked!r}")
    missing = set(key) - set(result)
    if missing:
        raise ValueError(f"{len(missing)} questions have no answer, e.g. {sorted(missing)[:3]}")
    return result


def llm_answers(model: str, folder: Path, key: dict, personas: dict, candidates: dict) -> tuple[dict, dict, float]:
    """14B judging directly: each pair once (shown exactly as in the exam), and top 3 of each list.
    Cached in exam/llm_<model>.jsonl so a broken connection can resume."""
    from llm.rank.direct import listwise
    from llm.rank.label import ask, free_other_models
    cache_path = folder / f"llm_{model.replace(':', '_')}.jsonl"
    cache = {(r["kind"], r["id"]): r for r in read_jsonl(cache_path)} if cache_path.exists() else {}
    free_other_models(model)
    by_id = {pid: {c["candidate_id"]: c for c in cs} for pid, cs in candidates.items()}
    with cache_path.open("a", encoding="utf-8") as handle:
        for pair_id, info in key.items():
            if ("pair", pair_id) in cache:
                continue
            a, b = by_id[info["persona"]][info["a_id"]], by_id[info["persona"]][info["b_id"]]
            red, blue = (a, b) if info["red"] == "A" else (b, a)
            started = time.time()
            reply = ask(model, personas[info["persona"]], red, blue)
            picked = info["red"] if reply["choice"] == "红" else ("B" if info["red"] == "A" else "A")
            row = {"kind": "pair", "id": pair_id, "choice": picked, "seconds": round(time.time() - started, 2)}
            cache[("pair", pair_id)] = row
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
        for pid, cs in candidates.items():
            if ("top3", pid) in cache:
                continue
            picked, seconds = listwise(model, personas[pid], cs)
            row = {"kind": "top3", "id": pid, "picked": picked, "seconds": round(seconds, 2)}
            cache[("top3", pid)] = row
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
    pairs = {k[1]: r["choice"] for k, r in cache.items() if k[0] == "pair"}
    tops = {k[1]: r["picked"] for k, r in cache.items() if k[0] == "top3"}
    seconds = mean(r["seconds"] for r in cache.values()) if cache else 0.0
    return pairs, tops, seconds


def score(folder: Path = EXAM, llm: str | None = None, again: bool = False) -> dict:
    report_path = OUT / "exam_report.json"
    if report_path.exists() and not again:
        raise SystemExit("exam_report.json already exists: the exam is sat once. Use --again only if you must, "
                         "and say so in the report.")
    spec_bytes = runtime.PATH.read_bytes()
    spec = json.loads(spec_bytes)
    key = json.loads((folder / "key.json").read_text(encoding="utf-8"))
    bundle = json.loads((folder / "candidates.json").read_text(encoding="utf-8"))
    personas, candidates = bundle["personas"], bundle["candidates"]
    answers = answers_as_ab(folder, key)

    per_method_choices: dict[str, dict[str, str]] = defaultdict(dict)
    per_method_top3: dict[str, dict[str, list[str]]] = defaultdict(dict)
    timings: dict[str, float] = {}
    for pid, cs in candidates.items():
        ids = [c["candidate_id"] for c in cs]
        started = time.perf_counter()
        scores = method_scores(personas[pid], cs, spec)
        elapsed = (time.perf_counter() - started) * 1000
        for name, values in scores.items():
            timings[name] = timings.get(name, 0.0) + elapsed / len(scores) / len(candidates)
            per_method_top3[name][pid] = [ids[i] for i in sorted(range(len(ids)), key=lambda i: (-values[i], ids[i]))[:3]]
        for pair_id, info in key.items():
            if info["persona"] == pid:
                for name, values in scores.items():
                    per_method_choices[name][pair_id] = choice(values, ids, info["a_id"], info["b_id"])
    llm_seconds = None
    if llm:
        pairs, tops, llm_seconds = llm_answers(llm, folder, key, personas, candidates)
        per_method_choices[f"千问 {llm} 直接判断（每对一次）"] = pairs
        per_method_top3[f"千问 {llm} 直接挑前 3"] = tops

    # The annotator's own order of each persona's candidates (round robin; 差不多 = half a point each).
    rows_by_persona = defaultdict(list)
    for pair_id, info in key.items():
        rows_by_persona[info["persona"]].append({"a_id": info["a_id"], "b_id": info["b_id"], "label": answers[pair_id]})
    shares, winners, ceilings = {}, {}, []
    for pid, cs in candidates.items():
        points = teacher_order(rows_by_persona[pid], [c["candidate_id"] for c in cs])
        shares[pid] = membership(points)
        top = max(points.values())
        winners[pid] = [i for i, v in points.items() if v == top]
        ceilings.append(sum(sorted(shares[pid].values(), reverse=True)[:3]) / 3)

    results = []
    for name in sorted(set(per_method_choices) | set(per_method_top3)):
        row = {"method": name}
        chosen = per_method_choices.get(name)
        if chosen:
            hits = defaultdict(list)
            for pair_id, truth in answers.items():
                if truth == "tie" or pair_id not in chosen:
                    continue
                hits[key[pair_id]["persona"]].append(0.5 if chosen[pair_id] == "tie" else float(chosen[pair_id] == truth))
            flat = [h for values in hits.values() for h in values]
            row.update(pairwise_accuracy=mean(flat) if flat else None, pairs_scored=len(flat), ci95=bootstrap(hits))
        tops = per_method_top3.get(name)
        if tops:
            row["top3_hit"] = mean(sum(shares[pid][i] for i in tops[pid]) / 3 for pid in tops)
            row["best_in_top3"] = mean(sum(i in tops[pid] for i in winners[pid]) / len(winners[pid]) for pid in tops)
        if name in timings:
            row["ms_per_student"] = timings[name]
        results.append(row)
    sizes = [len(cs) for cs in candidates.values()]
    report = {
        "note": "期末考卷（合成）：画像和答案由一个新的子代理撰写，不是真实学生；模型和规则都是定稿版本，没有重训或调参。",
        "model_json_sha256": hashlib.sha256(spec_bytes).hexdigest(), "model_trained_on": spec.get("trained_on"),
        "personas": len(candidates), "questions": len(key),
        "answers": dict(Counter("红/蓝" if a != "tie" else "差不多" for a in answers.values())),
        "random_baseline": {"pairwise_accuracy": 0.5, "top3_hit": mean(3 / n for n in sizes)},
        "top3_ceiling": mean(ceilings), "llm_seconds_per_call": llm_seconds, "rerun": again,
        "results": results,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "exam_report.md").write_text(markdown(report), encoding="utf-8")
    print(markdown(report))
    return report


def markdown(report: dict) -> str:
    lines = ["# 期末考卷：打分排序", "", f"> {report['note']}", "",
             f"{report['personas']} 个新画像，{report['questions']} 道二选一（答案：{report['answers']}）。"
             f"model.json 的 sha256：`{report['model_json_sha256'][:16]}…`" + ("（重考）" if report["rerun"] else ""), "",
             "| 方法 | 二选一准确率（95% 区间） | 前 3 命中 | 第一名进前 3 |", "| --- | --- | --- | --- |",
             f"| 随机 | 50% | {report['random_baseline']['top3_hit']:.2f} | |"]
    for row in report["results"]:
        acc, ci = row.get("pairwise_accuracy"), row.get("ci95")
        acc_text = "—" if acc is None else f"{acc:.1%}" + (f"（{ci[0]:.1%}–{ci[1]:.1%}）" if ci else "")
        top = f"{row['top3_hit']:.2f}" if "top3_hit" in row else "—"
        best = f"{row['best_in_top3']:.2f}" if "best_in_top3" in row else "—"
        lines.append(f"| {row['method']} | {acc_text} | {top} | {best} |")
    lines += ["", f"前 3 命中的上限（完全按答题者自己的排名）是 {report['top3_ceiling']:.2f}。"]
    if report.get("llm_seconds_per_call"):
        lines.append(f"千问每次调用平均 {report['llm_seconds_per_call']:.1f} 秒。")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("prepare", "score"))
    parser.add_argument("--dir", type=Path, default=EXAM, help="folder with personas.json / answers.jsonl")
    parser.add_argument("--llm", help="also let this Ollama model judge directly, e.g. qwen2.5:14b")
    parser.add_argument("--again", action="store_true", help="score a second time (recorded in the report)")
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args.dir)
    else:
        score(args.dir, args.llm, args.again)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
