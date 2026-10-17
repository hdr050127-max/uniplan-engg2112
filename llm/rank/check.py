"""A second annotator for the ranking labels: Claude (the coordinator window), not Qwen.

There are no human answers in this project (user decision, 2026-10-17). Claude is a
different model from the Qwen teacher, so its answers are an independent check, but they
are AI answers too; the report must say so.

check_pairs.jsonl holds two kinds of question, each exactly what Qwen saw (sentence, table,
weekly routine), red/blue in random order and without Qwen's answer:
- purpose "test_check": 60 pairs from the 20 test personas (3 each: 2 where the main concern
  clearly differs, 1 where it is near-equal). Never used for training or tuning.
- purpose "teacher_audit": 150 random labelled pairs from the full run. Qwen-vs-Claude agreement
  here is the reported label quality; where they disagree, Claude's answer replaces Qwen's
  before the final training.
Claude writes check_answers_claude.jsonl: one {"pair_id": ..., "choice": "红" | "蓝" | "差不多"} per line.

    python3 -m llm.rank.check prepare                                  # the 60 test_check pairs
    python3 -m llm.rank.check audit --labels output/labels_v3_X.jsonl  # add 150 teacher_audit pairs
    python3 -m llm.rank.check score --labels output/labels_v3_X.jsonl  # agreement report
    python3 -m llm.rank.check corrected --labels output/labels_v3_X.jsonl   # -> labels_v3_X_corrected.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llm.rank import model as runtime  # noqa: E402
from llm.rank.label import OUT, SYSTEM, full_jobs, hours_of, program_tie, table_text  # noqa: E402
from llm.rank.personas import load  # noqa: E402

PAIRS = OUT / "check_pairs.jsonl"
KEY = OUT / "check_pairs_key.json"           # pair_id -> persona, candidate ids, which side is red
ANSWERS = OUT / "check_answers_claude.jsonl"
SEED = "check-2112"
CHECK_PER_PERSONA = (2, 1)                   # clear on the main concern, near-equal on it
AUDIT_SIZE = 150
INSTRUCTIONS = (SYSTEM + "（核对说明：你和千问看到的内容完全相同。可以答“红”“蓝”，两份真的分不出时答“差不多”。）")


def clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def question_row(pair_id: str, purpose: str, persona: dict, red: dict, blue: dict) -> dict:
    hours = hours_of(persona["conditions"])
    return {"pair_id": pair_id, "purpose": purpose, "persona": persona["text"],
            "comfortable_hours": f"{clock(hours['start_min'])}–{clock(hours['end_min'])}",
            "table": table_text(persona, red, blue),
            "red": red["text"], "blue": blue["text"], "instructions": INSTRUCTIONS, "synthetic": True}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] \
        if path.exists() else []


def write(rows: list[dict], key: dict) -> None:
    with PAIRS.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    KEY.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")


def prepare() -> None:
    """60 test_check pairs; replaces the file (only before Claude has answered)."""
    if read_jsonl(ANSWERS):
        raise SystemExit("check_answers_claude.jsonl already has answers; the check pairs are frozen.")
    jobs, _ = full_jobs()
    rng = random.Random(SEED)
    by_persona = defaultdict(list)
    for persona, a, b in jobs:
        if persona["split"] == "test":
            by_persona[persona["id"]].append((persona, a, b))
    rows, key = [], {}
    total_pairs = sum(CHECK_PER_PERSONA) * len(by_persona)
    sides = [True] * (total_pairs // 2) + [False] * (total_pairs - total_pairs // 2)
    rng.shuffle(sides)    # exactly half the answers sit on the red side
    for pid in sorted(by_persona):
        pairs = by_persona[pid]
        clear = [p for p in pairs if not program_tie(*p)]
        near = [p for p in pairs if program_tie(*p)]
        total = sum(CHECK_PER_PERSONA)
        take_clear = min(len(clear), max(CHECK_PER_PERSONA[0], total - len(near)))
        chosen = rng.sample(clear, take_clear) + rng.sample(near, total - take_clear)
        for persona, a, b in chosen:
            pair_id = f"t{len(rows) + 1:03d}"
            red_is_a = sides[len(rows)]
            red, blue = (a, b) if red_is_a else (b, a)
            rows.append(question_row(pair_id, "test_check", persona, red, blue))
            key[pair_id] = {"purpose": "test_check", "persona": pid, "a_id": a["candidate_id"],
                            "b_id": b["candidate_id"], "red": "A" if red_is_a else "B",
                            "near_equal_focus": program_tie(persona, a, b)}
    rng.shuffle(rows)   # personas interleaved, so no answer is read next to its neighbours
    write(rows, key)
    print(f"wrote {len(rows)} test_check pairs to {PAIRS.relative_to(ROOT)}")


def audit(labels: Path) -> None:
    """Add 150 random teacher-decided pairs (A or B) from the full run."""
    rows, key = read_jsonl(PAIRS), json.loads(KEY.read_text(encoding="utf-8"))
    if any(k["purpose"] == "teacher_audit" for k in key.values()):
        raise SystemExit("teacher_audit pairs already exist.")
    jobs, _ = full_jobs()
    candidates = {(p["id"], a["candidate_id"], b["candidate_id"]): (p, a, b) for p, a, b in jobs}
    used = {(k["persona"], k["a_id"], k["b_id"]) for k in key.values()}
    decided = [r for r in read_jsonl(labels) if r["label"] in ("A", "B")
               and (r["persona"], r["a_id"], r["b_id"]) not in used]
    rng = random.Random(SEED + ":audit")
    new = []
    for r in rng.sample(decided, min(AUDIT_SIZE, len(decided))):
        persona, a, b = candidates[(r["persona"], r["a_id"], r["b_id"])]
        pair_id = f"a{len(new) + 1:03d}"
        red_is_a = rng.random() < 0.5
        red, blue = (a, b) if red_is_a else (b, a)
        new.append(question_row(pair_id, "teacher_audit", persona, red, blue))
        key[pair_id] = {"purpose": "teacher_audit", "persona": r["persona"], "a_id": r["a_id"],
                        "b_id": r["b_id"], "red": "A" if red_is_a else "B",
                        "near_equal_focus": program_tie(persona, a, b)}
    rng.shuffle(new)
    write(rows + new, key)
    print(f"added {len(new)} teacher_audit pairs to {PAIRS.relative_to(ROOT)}")


def claude_answers() -> dict[str, str]:
    """pair_id -> A, B or tie, in terms of the key's original A/B."""
    key = json.loads(KEY.read_text(encoding="utf-8"))
    result = {}
    for row in read_jsonl(ANSWERS):
        info = key[row["pair_id"]]
        choice = row["choice"].strip()
        if choice == "差不多":
            result[row["pair_id"]] = "tie"
        else:
            red = info["red"]
            result[row["pair_id"]] = red if choice == "红" else ("B" if red == "A" else "A")
    return result


def model_choice(spec: dict | None, persona: dict, xa: dict, xb: dict) -> str:
    prefs = {"cares": persona["conditions"]["cares"], "preferred_hours": persona["conditions"].get("preferred_hours")}
    if spec is None:
        return "tie"
    s = runtime.student_terms(prefs)
    margin = runtime.utility(xa, s, spec) - runtime.utility(xb, s, spec)
    return "A" if margin > 0 else "B" if margin < 0 else "tie"


def agreement(pairs: list[tuple[str, str]]) -> dict:
    """Share of pairs where both gave the same A/B answer; pairs where either said tie are left out."""
    both = [(x, y) for x, y in pairs if x in ("A", "B") and y in ("A", "B")]
    same = sum(x == y for x, y in both)
    return {"agree": same, "compared": len(both), "rate": round(same / len(both), 3) if both else None,
            "left_out_ties": len(pairs) - len(both)}


def score(labels: Path) -> dict:
    key, answers = json.loads(KEY.read_text(encoding="utf-8")), claude_answers()
    teacher = {(r["persona"], r["a_id"], r["b_id"]): r for r in read_jsonl(labels)}
    personas = {p["id"]: p for p in load()}
    sets = json.loads((OUT / "candidate_sets.json").read_text(encoding="utf-8"))["sets"]
    xs = {(pid, c["candidate_id"]): c["x"] for pid, entries in sets.items() for c in entries}
    spec = runtime.load()
    report = {"note": "核对者是 Claude（总控窗口），不是真人；千问老师和 Claude 都是 AI。画像是合成的。",
              "answered": len(answers), "labels": str(labels)}
    for purpose in ("test_check", "teacher_audit"):
        ids = [pid for pid, info in key.items() if info["purpose"] == purpose and pid in answers]
        if not ids:
            continue
        rows = []
        for pair_id in ids:
            info = key[pair_id]
            row = teacher.get((info["persona"], info["a_id"], info["b_id"]))
            qwen = row["label"] if row else "missing"
            persona = personas[info["persona"]]
            mine = model_choice(spec, persona, xs[(info["persona"], info["a_id"])], xs[(info["persona"], info["b_id"])])
            rows.append({"pair_id": pair_id, "claude": answers[pair_id], "qwen": qwen, "model": mine,
                         "near": info["near_equal_focus"]})
        clear = [r for r in rows if not r["near"]]
        near = [r for r in rows if r["near"]]
        report[purpose] = {
            "pairs": len(rows),
            "claude_answers": dict(Counter(r["claude"] for r in rows)),
            "qwen_labels": dict(Counter(r["qwen"] for r in rows)),
            "qwen_vs_claude": agreement([(r["qwen"], r["claude"]) for r in rows]),
            "model_vs_claude": agreement([(r["model"], r["claude"]) for r in rows]),
            "model_vs_qwen": agreement([(r["model"], r["qwen"]) for r in rows]),
            "main_concern_clear": {"pairs": len(clear),
                                   "qwen_vs_claude": agreement([(r["qwen"], r["claude"]) for r in clear]),
                                   "model_vs_claude": agreement([(r["model"], r["claude"]) for r in clear])},
            "main_concern_near_equal": {"pairs": len(near),
                                        "claude_said_tie": sum(r["claude"] == "tie" for r in near),
                                        "qwen_vs_claude": agreement([(r["qwen"], r["claude"]) for r in near]),
                                        "model_vs_claude": agreement([(r["model"], r["claude"]) for r in near])},
            "rows": rows,
        }
    (OUT / "check_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def corrected(labels: Path) -> Path:
    """The labels with Claude's audit answers where they differ from Qwen's (tie if Claude said 差不多)."""
    key, answers = json.loads(KEY.read_text(encoding="utf-8")), claude_answers()
    fixes = {(info["persona"], info["a_id"], info["b_id"]): answers[pid]
             for pid, info in key.items() if info["purpose"] == "teacher_audit" and pid in answers}
    out = labels.with_name(labels.stem + "_corrected.jsonl")
    changed = 0
    with out.open("w", encoding="utf-8") as handle:
        for row in read_jsonl(labels):
            fix = fixes.get((row["persona"], row["a_id"], row["b_id"]))
            if fix is not None and fix != row["label"]:
                row = {**row, "label": fix, "qwen_label": row["label"], "corrected_by": "claude"}
                changed += 1
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{changed} of {len(fixes)} audited labels replaced by Claude's answer -> {out.relative_to(ROOT)}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("prepare", "audit", "score", "corrected"))
    parser.add_argument("--labels", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare()
    elif args.labels is None:
        parser.error("--labels is required")
    elif args.mode == "audit":
        audit(args.labels)
    elif args.mode == "score":
        report = score(args.labels)
        print(json.dumps({k: ({kk: vv for kk, vv in v.items() if kk != "rows"} if isinstance(v, dict) else v)
                          for k, v in report.items()}, ensure_ascii=False, indent=1))
    else:
        corrected(args.labels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
