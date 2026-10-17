"""Teacher-student rounds: Qwen answers, Claude grades, the graded labels train Qwen.

    python3 -m llm.parse.review pool                 # question pool, minus anything close to the test set
    python3 -m llm.gpu_lock -- python3 -m llm.parse.review answer          # qwen2.5:7b, untrained
    python3 -m llm.parse.review sheet --round 1      # output/review_round1.jsonl for Claude to grade
    python3 -m llm.parse.review apply --round 1      # Claude's labels -> training data + round stats
    python3 -m llm.parse.review round2               # round 1 + part-of-day relabels + Claude's round-2 clauses

The pool is the SYNTHETIC clauses written by qwen2.5:7b (source qwen_synth, label = the label they
were generated for) plus Claude's hard training clauses in data/train_claude.csv (source claude_train).
data/test_claude.csv never enters a pool: pool clauses that look like any test clause are removed.
Claude writes its grades to output/review_round<N>_claude.jsonl: one line per id with
"label" (the right label) and "keep" (false when the clause itself is unusable).
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

from llm.parse.gold import clause_key, load
from llm.parse.labels import LABELS, short_messages

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "output"
POOL = OUTPUT / "review_pool.jsonl"
SYNTHETIC = OUTPUT / "synthetic_clauses.jsonl"
TRAIN_CLAUDE = HERE / "data" / "train_claude.csv"
TEST = HERE / "data" / "test_claude.csv"
LORA_DATA = HERE / "windows" / "data"
SEED = 2112
SIMILAR = 0.85          # character similarity at which a pool clause counts as a copy of a test clause
AGREE_SAMPLE = 0.10     # share of clauses both models got "right" that Claude still checks


def _read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _val_share(key: str, share: float = 0.15) -> bool:
    return int(hashlib.sha256(f"{SEED}|{key}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < share


def build_pool() -> dict:
    rows = [{"id": f"syn-{index:04d}", "clause": row["text"], "gen_label": row["label"], "source": "qwen_synth",
             "language": row["language"], "split": row["split"]} for index, row in enumerate(_read(SYNTHETIC))]
    if TRAIN_CLAUDE.exists():
        for sentence in load(TRAIN_CLAUDE):
            split = "val" if _val_share(sentence["id"]) else "train"
            rows += [{"id": f"cl-{sentence['id']}-{number}", "clause": clause["text"], "gen_label": clause["label"],
                      "source": "claude_train", "language": "en", "split": split}
                     for number, clause in enumerate(sentence["clauses"], 1)]
    # Remove anything close to a test clause. Only counts are printed; the test text is never shown.
    test = [clause_key(c["text"]) for s in load(TEST) for c in s["clauses"]] if TEST.exists() else []
    kept, removed = [], Counter()
    for row in rows:
        key = clause_key(row["clause"])
        close = any(difflib.SequenceMatcher(None, key, other).quick_ratio() >= SIMILAR
                    and difflib.SequenceMatcher(None, key, other).ratio() >= SIMILAR for other in test)
        if close:
            removed[row["source"]] += 1
        else:
            kept.append(row)
    _write(POOL, kept)
    stats = {"pool": len(kept), "by_source": dict(Counter(r["source"] for r in kept)),
             "by_split": dict(Counter(r["split"] for r in kept)), "removed_as_close_to_test": dict(removed),
             "similarity_threshold": SIMILAR}
    print(json.dumps(stats, indent=2))
    return stats


def answer(models: list[str]) -> None:
    """Answers from untrained Qwen (7B only since 2026-10-17), cached with the evaluation predictions."""
    from llm import ollama
    from llm.parse.classify import ollama_classifier
    from llm.parse.evaluate import data_sets, predict, texts_needed
    texts = list(dict.fromkeys([row["clause"] for row in _read(POOL)] + texts_needed(data_sets(False))))
    for number, model in enumerate(models):
        if number:
            ollama.unload(models[number - 1])
        predict(f"ollama:{model}", ollama_classifier(model), texts,
                {"machine": ollama.base_url(), "note": "no training, full prompt with rules, constrained to the 9 labels"})


def _predictions(model: str) -> dict:
    path = OUTPUT / "predictions" / f"ollama_{model.replace(':', '_')}.json"
    return json.loads(path.read_text())["predictions"]


def sheet(round_number: int, models: list[str]) -> None:
    pool = _read(POOL)
    answers = {model: _predictions(model) for model in models}
    rng = random.Random(SEED + round_number)
    picked, counts = [], Counter()
    for row in pool:
        preds = {model: answers[model][row["clause"]]["label"] for model in models}
        disagree = any(pred != row["gen_label"] for pred in preds.values())
        if disagree or rng.random() < AGREE_SAMPLE:
            picked.append({"id": row["id"], "clause": row["clause"], "gen_label": row["gen_label"],
                           **{f"pred_{model.split(':')[-1]}": pred for model, pred in preds.items()},
                           "source": row["source"], "split": row["split"]})
            counts["disagree" if disagree else "agree_sample"] += 1
    _write(OUTPUT / f"review_round{round_number}.jsonl", picked)
    stats = {"round": round_number, "pool": len(pool), "to_grade": len(picked), **counts,
             "by_source": dict(Counter(r["source"] for r in picked)),
             "agree_sample_share": AGREE_SAMPLE, "sample_seed": SEED + round_number,
             "zero_shot_accuracy_vs_gen_label": {
                 model: round(sum(answers[model][r["clause"]]["label"] == r["gen_label"] for r in pool) / len(pool), 4)
                 for model in models}}
    (OUTPUT / f"review_round{round_number}_stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats, indent=2))


def grading_stats(round_number: int, graded: dict) -> dict:
    """Who was right on the graded sheet: the generation label, the untrained model, or neither."""
    sheet = _read(OUTPUT / f"review_round{round_number}.jsonl")
    model_keys = [key for key in sheet[0] if key.startswith("pred_")]
    kept = [row for row in sheet if graded[row["id"]].get("keep", True)]
    dropped = [row for row in sheet if not graded[row["id"]].get("keep", True)]
    result = {"graded": len(sheet), "kept": len(kept), "dropped": len(dropped),
              "dropped_by_source": dict(Counter(r["source"] for r in dropped)),
              "graded_and_dropped_by_gen_label": {
                  label: f"{sum(r['gen_label'] == label for r in sheet)}/{sum(r['gen_label'] == label for r in dropped)}"
                  for label in LABELS}}
    for key in model_keys:
        disagree = [r for r in kept if r[key] != r["gen_label"]]
        agree = [r for r in kept if r[key] == r["gen_label"]]
        gen_right = sum(graded[r["id"]]["label"] == r["gen_label"] for r in disagree)
        model_right = sum(graded[r["id"]]["label"] == r[key] for r in disagree)
        result[key] = {"disagreements_kept": len(disagree), "generation_label_right": gen_right,
                       "model_right": model_right, "both_wrong": len(disagree) - gen_right - model_right,
                       "agreements_sampled_kept": len(agree),
                       "agreements_both_right": sum(graded[r["id"]]["label"] == r["gen_label"] for r in agree)}
    return result


def apply(round_number: int) -> None:
    """Training data for this round: Claude's label where graded, the generation label elsewhere."""
    pool = {row["id"]: row for row in _read(POOL)}
    graded = {row["id"]: row for row in _read(OUTPUT / f"review_round{round_number}_claude.jsonl")}
    unknown = [key for key in graded if key not in pool]
    bad = [key for key, row in graded.items() if row.get("keep", True) and row.get("label") not in LABELS]
    if unknown or bad:
        sys.exit(f"grades with unknown ids {unknown[:5]} or labels {bad[:5]}")
    rows, changes = [], Counter()
    for key, row in pool.items():
        grade = graded.get(key)
        if grade is not None and grade.get("keep", True) is False:
            changes[f"dropped_{row['source']}"] += 1
            continue
        label = grade["label"] if grade else row["gen_label"]
        if grade:
            changes[f"graded_{row['source']}"] += 1
            if label != row["gen_label"]:
                changes[f"relabelled_{row['source']}"] += 1
                changes[f"{row['gen_label']} -> {label}"] += 1
        rows.append({"text": row["clause"], "label": label, "label_from": "claude" if grade else "generation",
                     "source": row["source"], "language": row["language"], "split": row["split"], "id": key})
    _write(OUTPUT / f"train_round{round_number}.jsonl", rows)
    LORA_DATA.mkdir(parents=True, exist_ok=True)
    for split, name in (("train", "train"), ("val", "valid")):
        _write(LORA_DATA / f"{name}.jsonl", [
            {"messages": short_messages(r["text"]) + [{"role": "assistant", "content": r["label"]}]}
            for r in rows if r["split"] == split])
    stats = json.loads((OUTPUT / f"review_round{round_number}_stats.json").read_text())
    stats["grading"] = grading_stats(round_number, graded)
    stats["applied"] = {"training_rows": len(rows), "by_split": dict(Counter(r["split"] for r in rows)),
                        "by_source": dict(Counter(r["source"] for r in rows)),
                        "label_from": dict(Counter(r["label_from"] for r in rows)), **dict(changes)}
    (OUTPUT / f"review_round{round_number}_stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats["applied"], indent=2))


TRAIN_CLAUDE_R2 = HERE / "data" / "train_claude_round2.csv"
RELABELS_R2 = OUTPUT / "round2_relabels.jsonl"


def round2() -> None:
    """Round-2 training data: round 1, with the part-of-day relabels (output/round2_relabels.jsonl,
    validation included) and Claude's round-2 clauses (data/train_claude_round2.csv) added to the
    training split only, so the validation set stays comparable with round 1."""
    rows = _read(OUTPUT / "train_round1.jsonl")
    changes = {row["id"]: row for row in _read(RELABELS_R2)}
    result, counts = [], Counter()
    for row in rows:
        change = changes.get(row["id"])
        if change is None:
            result.append(row)
        elif not change["keep"]:
            counts[f"dropped_{row['split']}"] += 1
        else:
            counts[f"relabelled_{row['split']}"] += 1
            result.append({**row, "label": change["new_label"], "label_from": "claude_round2"})
    added = [{"text": clause["text"], "label": clause["label"], "label_from": "claude", "source": "claude_train_r2",
              "language": "zh" if any("\u4e00" <= ch <= "\u9fff" for ch in clause["text"]) else "en",
              "split": "train", "id": f"{sentence['id']}-{number}"}
             for sentence in load(TRAIN_CLAUDE_R2) for number, clause in enumerate(sentence["clauses"], 1)]
    result += added
    _write(OUTPUT / "train_round2.jsonl", result)
    LORA_DATA.mkdir(parents=True, exist_ok=True)
    for split, name in (("train", "train"), ("val", "valid")):
        _write(LORA_DATA / f"{name}.jsonl", [
            {"messages": short_messages(r["text"]) + [{"role": "assistant", "content": r["label"]}]}
            for r in result if r["split"] == split])
    stats = {"round": 2, "from": "train_round1.jsonl", "relabels": len(changes), **dict(counts),
             "claude_round2_clauses_added": len(added),
             "added_by_label": dict(Counter(r["label"] for r in added)),
             "training_rows": len(result), "by_split": dict(Counter(r["split"] for r in result)),
             "by_source": dict(Counter(r["source"] for r in result)),
             "label_from": dict(Counter(r["label_from"] for r in result))}
    (OUTPUT / "review_round2_stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Teacher-student review rounds.")
    parser.add_argument("step", choices=("pool", "answer", "sheet", "apply", "round2"))
    parser.add_argument("models", nargs="*", default=["qwen2.5:7b"])
    parser.add_argument("--round", type=int, default=1)
    args = parser.parse_args(argv)
    if args.step == "pool":
        build_pool()
    elif args.step == "answer":
        answer(args.models)
    elif args.step == "sheet":
        sheet(args.round, args.models)
    elif args.step == "apply":
        apply(args.round)
    else:
        round2()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
