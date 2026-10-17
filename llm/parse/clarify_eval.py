"""How well the clarifying questions work: ask rarely, catch the clauses that are wrong.

    python3 -m llm.parse.clarify_eval            # writes output/clarify/clarify_results.md and .json

Sets (the only ones used to design the rules): the validation split (synthetic clauses, plus
sentences joined from them), test v1 and test v2 (Claude-written sentences). No model is called:
labels come from cached predictions in output/clarify/predictions.
- model run time:  labels from uniplan-parse-7b-r2; second opinion from the round-1 linear model;
- linear run time: labels from the round-1 linear model alone (offline), with the margin rule.
On the validation split the linear model is the one fitted on the training split only
(output/round1/linear_model_train_only.json), so it has not seen those clauses; on v1 and v2 it
is the run-time file (output/linear_model.json).

Clause metrics use the annotators' clauses: asked share (how often the page interrupts), caught
share (of the wrong clauses, how many get a question), precision (of the asked clauses, how many
are wrong), fixable share (of the wrong clauses, how many get a question whose options include the
right label). Sentence metrics run the whole pipeline, with the cap of clarify.MAX_QUESTIONS.
"""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from llm.parse import clarify, linear
from llm.parse.evaluate import HERE, OUTPUT, data_sets
from llm.parse.extract import fields, merge
from llm.parse.gold import load
from llm.parse.split import split_clauses

CACHE = OUTPUT / "clarify" / "predictions"
MODEL = "ollama-short_uniplan-parse-7b-r2"
TESTS = {"v1": HERE / "data" / "test_claude.csv", "v2": HERE / "data" / "test_claude_v2.csv"}


def _core(clauses: list[dict]) -> dict:
    return {"clauses": clauses, "conditions": merge(clauses),
            "unrecognised": [c["text"] for c in clauses if c["label"] == "other"]}


def _clause(text: str, label: str) -> dict:
    return {"text": text, "label": label, "fields": fields(label, text)}


def clause_scores(items: list[tuple[str, str]], label_of, from_model: bool, opinion) -> dict:
    """items: (clause text, right label)."""
    rows = []
    for text, gold in items:
        label = label_of(text)
        asked = [q for q in clarify.questions(_core([_clause(text, label)]), [from_model], opinion)
                 if q["clause_index"] == 0]
        options = {o["label"] for q in asked for o in q["options"]}
        rows.append({"wrong": label != gold, "asked": bool(asked), "fixable": gold in options,
                     "kind": asked[0]["kind"] if asked else None})
    wrong = [r for r in rows if r["wrong"]]
    asked = [r for r in rows if r["asked"]]
    share = lambda part, whole: len(part) / len(whole) if whole else 0.0     # noqa: E731
    return {"clauses": len(rows), "wrong": len(wrong), "asked": len(asked),
            "asked_share": share(asked, rows),
            "caught_share": share([r for r in wrong if r["asked"]], wrong),
            "precision": share([r for r in asked if r["wrong"]], asked),
            "fixable_share": share([r for r in wrong if r["asked"] and r["fixable"]], wrong),
            "by_kind": {kind: sum(r["kind"] == kind for r in rows)
                        for kind in ("low_confidence", "hard_or_soft", "missing_value")}}


def sentence_scores(sentences: list[str], label_of, from_model: bool, opinion) -> dict:
    counts, clarifying, offers = [], [], []
    for sentence in sentences:
        pieces = split_clauses(sentence)
        result = _core([_clause(piece, label_of(piece)) for piece in pieces])
        found = clarify.questions(result, [from_model] * len(pieces), opinion)
        counts.append(len(found))
        clarifying.append(sum(q["kind"] != "offer" for q in found))
        offers.append(sum(q["kind"] == "offer" for q in found))
    return {"sentences": len(sentences), "questions_per_sentence": statistics.mean(counts),
            "clarifying_per_sentence": statistics.mean(clarifying), "offers_per_sentence": statistics.mean(offers),
            "sentences_with_a_question": sum(c > 0 for c in counts) / len(counts)}


def run() -> dict:
    sets = data_sets(False)
    data = {"val": ([(c["text"], c["label"]) for c in sets["val"]["clauses"]],
                    [s["sentence"] for s in sets["val"]["sentences"]])}
    for name, path in TESTS.items():
        gold = load(path)
        data[name] = ([(c["text"], c["label"]) for s in gold for c in s["clauses"]], [s["sentence"] for s in gold])
    model_preds = json.loads((CACHE / f"{MODEL}.json").read_text())["predictions"]
    train_only = linear.load(OUTPUT / "round1" / "linear_model_train_only.json")
    run_time = linear.load(OUTPUT / "linear_model.json")
    results = {}
    for name, (items, sentences) in data.items():
        second = train_only if name == "val" else run_time
        results[name] = {
            "model run time": {"clauses": clause_scores(items, lambda t: model_preds[t]["label"], True,
                                                        second.probabilities),
                               "sentences": sentence_scores(sentences, lambda t: model_preds[t]["label"], True,
                                                            second.probabilities)},
            "linear run time": {"clauses": clause_scores(items, second, False, second.probabilities),
                                "sentences": sentence_scores(sentences, second, False, second.probabilities)},
        }
    return results


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def markdown(results: dict) -> str:
    lines = ["# 反问的效果", "", f"生成于 {time.strftime('%Y-%m-%d %H:%M')}，脚本 `python3 -m llm.parse.clarify_eval`。"
             "只用验证集、测试集 v1、v2 设计和调规则；期末考卷不在这里。", "",
             f"- 规则：`llm/parse/clarify.py`；线性模型单独运行时的概率差阈值 MARGIN = {clarify.MARGIN}；"
             f"每句最多 {clarify.MAX_QUESTIONS} 个问题，其中推荐最多 {clarify.MAX_OFFERS} 个。",
             "- 运行时是模型：标签来自 uniplan-parse-7b-r2，第二意见是第 1 轮的线性模型（验证集上用只在训练集上拟合的那份）。",
             "- 运行时是线性模型（离线后备）：标签和概率差都来自第 1 轮的线性模型。",
             "- 短句指标用标注者切好的短句；整句指标跑完整条流程（含每句最多 3 个的上限，推荐也算问题）。",
             "- **样本内**：反问的规则提示和触发条件是看过验证集、v1、v2 的错例之后定的，阈值在验证集上选，"
             "所以这三份上的数字都是样本内的，偏乐观。样本外的数字只有期末考卷（`llm/parse/exam/`，由总控运行）。", ""]
    for mode in ("model run time", "linear run time"):
        title = "运行时是 uniplan-parse-7b-r2" if mode == "model run time" else "运行时是线性模型（离线）"
        lines += [f"## {title}", "",
                  "| 数据 | 短句 | 错的短句 | 打扰率（问到的短句） | 抓错率（错句被问到） | 问到的里真错的 | 能改对的错句 | "
                  "每句问题数 | 其中澄清 | 其中推荐 | 有问题的句子 | 按类型（低置信/软硬/缺值） |",
                  "| --- |" + " ---: |" * 11]
        for name, scores in results.items():
            c, s = scores[mode]["clauses"], scores[mode]["sentences"]
            kinds = "/".join(str(c["by_kind"][k]) for k in ("low_confidence", "hard_or_soft", "missing_value"))
            lines.append(f"| {name} | {c['clauses']} | {c['wrong']} | {_pct(c['asked_share'])} | {_pct(c['caught_share'])} | "
                         f"{_pct(c['precision'])} | {_pct(c['fixable_share'])} | {s['questions_per_sentence']:.2f} | "
                         f"{s['clarifying_per_sentence']:.2f} | {s['offers_per_sentence']:.2f} | "
                         f"{_pct(s['sentences_with_a_question'])} | {kinds} |")
        lines.append("")
    lines.append("验证集的句子是把 2–3 个合成短句拼起来的，v1、v2 是整句。")
    return "\n".join(lines) + "\n"


def main() -> int:
    results = run()
    out = OUTPUT / "clarify"
    out.mkdir(parents=True, exist_ok=True)
    (out / "clarify_results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False))
    (out / "clarify_results.md").write_text(markdown(results), encoding="utf-8")
    print(markdown(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
