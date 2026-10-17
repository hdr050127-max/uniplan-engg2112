"""Two follow-up experiments on the final ranker (CPU only; SYNTHETIC labels, see train.py).

- Learning curve: train on 6, 15, 30, 60, 90 and all training personas (sampled by persona
  from rounds 1 and 2, fixed seeds, 5 draws per size), plus "round 1 only", and score the
  same 20 test personas. Answers "are there enough labels, would more help?". Run twice:
  with the free program pairs of the sampled personas (as shipped) and teacher labels alone.
- Feature ablation: drop one group of features (or the student terms) and retrain.

Both use the shipped setting (pairwise logistic regression with student terms, C from
model.json, free program pairs whose winner is not worse on the main concern) and no tuning.

    /usr/local/bin/python3 -m llm.rank.experiments --labels llm/rank/output/labels_v3d_qwen2.5_14b_corrected.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llm.rank import model as runtime  # noqa: E402
from llm.rank.features import NAMES  # noqa: E402
from llm.rank.personas import load as load_personas  # noqa: E402
from llm.rank.train import (OUT, PairwiseLR, decided, load_rows, pairwise_accuracy, program_pairs,  # noqa: E402
                            spec_from, top3_metrics)

SEED = 2112
COUNTS = (6, 15, 30, 60, 90, 120)
DRAWS = 5
GROUPS = {
    "三个主项（到校天数、空等、早晚课）": ("campus_days", "gap_h", "outside_h"),
    "早课和晚课的细分": ("early_h", "late_h"),
    "最早上课和最晚下课": ("earliest_start", "latest_end"),
    "最长的一天和上课最多的一天": ("longest_day_h", "heaviest_day_h"),
    "周五不用到校": ("friday_free",),
    "换楼次数": ("building_changes",),
    "只为一节课到校": ("single_class_days",),
    "线上课比例": ("online_share",),
}


def evaluate(model, test, sets, personas) -> dict:
    top = top3_metrics(model, test, sets, personas)
    return {"accuracy": pairwise_accuracy(model, test, sets)[0],
            "accuracy_qwen_pairs": pairwise_accuracy(model, [r for r in test if r["source"] == "model"], sets)[0],
            "accuracy_rule_pairs": pairwise_accuracy(model, [r for r in test if r["source"] == "program_dominance"],
                                                     sets)[0],
            "top3_hit": top["top3_hit"], "best_in_top3": top["best_in_top3"]}


def fit(rows, C, features=NAMES, interactions=True):
    spec = {**spec_from(rows), "features": list(features)}
    return PairwiseLR(interactions, C=C).fit(decided(rows), spec)


def mean_sd(runs: list[dict]) -> dict:
    return {key: {"mean": float(np.mean([r[key] for r in runs])), "sd": float(np.std([r[key] for r in runs]))}
            for key in runs[0]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--labels", required=True)
    args = parser.parse_args()
    spec = runtime.load()
    C = spec["C"] if spec else 1.0
    rows = load_rows(Path(args.labels))
    personas = {p["id"]: p for p in load_personas()}
    sets = json.loads((OUT / "candidate_sets.json").read_text(encoding="utf-8"))["sets"]
    teacher = [r for r in rows if r["split"] == "train"]
    test = [r for r in rows if r["split"] == "test"]
    free = decided(program_pairs(rows, sets, personas, strict_focus=True))
    train_ids = sorted({r["persona"] for r in teacher})

    round_one = sorted(pid for pid in train_ids if personas[pid].get("round", 1) == 1)
    curve = {"with_program_pairs": [], "teacher_labels_only": []}
    sizes = [count for count in COUNTS if count < len(train_ids)] + [len(train_ids), "round 1"]
    for size in sizes:
        count = len(round_one) if size == "round 1" else size
        draws = 1 if size in (len(train_ids), "round 1") else DRAWS
        for variant in curve:
            runs = []
            for draw in range(draws):
                chosen = (set(round_one) if size == "round 1" else
                          set(random.Random(f"{SEED}:{count}:{draw}").sample(train_ids, count)))
                subset = [r for r in teacher if r["persona"] in chosen]
                if variant == "with_program_pairs":
                    subset += [r for r in free if r["persona"] in chosen]
                result = evaluate(fit(subset, C), test, sets, personas)
                runs.append({**result, "train_pairs": len(decided(subset)),
                             "teacher_pairs": len(decided([r for r in subset if r["source"] != "program_extra"]))})
            summary = {"personas": count, "sample": "round 1 only" if size == "round 1" else "random",
                       "draws": draws, **mean_sd(runs)}
            curve[variant].append(summary)
            print(f"{variant:20s} {summary['sample']:12s} personas={count:3d} "
                  f"teacher pairs={summary['teacher_pairs']['mean']:5.0f} "
                  f"acc={summary['accuracy']['mean']:.3f}±{summary['accuracy']['sd']:.3f} "
                  f"qwen={summary['accuracy_qwen_pairs']['mean']:.3f} rule={summary['accuracy_rule_pairs']['mean']:.3f} "
                  f"top3={summary['top3_hit']['mean']:.3f}±{summary['top3_hit']['sd']:.3f}", flush=True)

    train = teacher + free
    full = evaluate(fit(train, C), test, sets, personas)
    ablation = [{"dropped": "（不去掉，完整模型）", **full}]
    for name, group in GROUPS.items():
        ablation.append({"dropped": name, **evaluate(fit(train, C, [n for n in NAMES if n not in group]),
                                                     test, sets, personas)})
    ablation.append({"dropped": "学生交叉项（只用课表特征）", **evaluate(fit(train, C, interactions=False),
                                                                     test, sets, personas)})
    for row in ablation:
        row["delta_accuracy"] = row["accuracy"] - full["accuracy"]
        row["delta_top3"] = row["top3_hit"] - full["top3_hit"]
        print(f"{row['dropped']:24s} acc={row['accuracy']:.3f} ({row['delta_accuracy']:+.3f}) "
              f"qwen={row['accuracy_qwen_pairs']:.3f} rule={row['accuracy_rule_pairs']:.3f} "
              f"top3={row['top3_hit']:.3f} ({row['delta_top3']:+.3f})", flush=True)

    note = "合成数据：标签来自大模型扮演的合成画像；测试是 20 个没进训练的画像。没有调参，用上线模型的设置。"
    (OUT / "learning_curve.json").write_text(json.dumps({"note": note, "C": C, "curve": curve},
                                                        ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "ablation.json").write_text(json.dumps({"note": note, "C": C, "ablation": ablation},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
