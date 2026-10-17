"""Compare clause classifiers on the same data and write one markdown table.

    python3 -m llm.parse.evaluate --models keywords linear ollama:qwen2.5:7b
    python3 -m llm.parse.evaluate --report-only          # rebuild the table from saved predictions
    python3 -m llm.parse.evaluate --models ... --test    # ONLY once the team's test set is final

Data sets:
- val: the held-out SYNTHETIC clauses (llm/parse/output/synthetic_clauses.jsonl, split == "val"),
  plus sentences made by joining 2-3 of them, to measure splitting + classifying together;
- examples: the 10 example sentences in data/test_template.csv (written by Claude, NOT a test set);
- test: data/test.csv written by team members, read only with --test.

Every model predicts every text it needs once; predictions are saved in output/predictions/<model>.json
with the time each took, so models trained elsewhere (scikit-learn, LoRA) can be scored the same way.
"""
from __future__ import annotations

import argparse
import json
import platform
import random
import statistics
import sys
import time
from pathlib import Path

from llm.parse import parse
from llm.parse.gold import clause_key, load
from llm.parse.metrics import LABEL_ORDER, classification, confusion_markdown, field_accuracy
from llm.parse.split import split_clauses

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "output"
PREDICTIONS = OUTPUT / "predictions"
SYNTHETIC = OUTPUT / "synthetic_clauses.jsonl"
TEMPLATE = HERE / "data" / "test_template.csv"
TEST = HERE / "data" / "test.csv"
SEED = 2112


def synthetic(split: str) -> list[dict]:
    with open(SYNTHETIC, encoding="utf-8") as handle:
        return [row for row in map(json.loads, handle) if row["split"] == split]


def joined_sentences(rows: list[dict], count: int = 120) -> list[dict]:
    """2-3 synthetic clauses of one language joined into a sentence, with the labels they carry."""
    rng = random.Random(SEED)
    sentences = []
    by_language: dict[str, list[dict]] = {}
    for row in rows:
        by_language.setdefault(row["language"], []).append(row)
    for language, pool in sorted(by_language.items()):
        pool = pool[:]
        rng.shuffle(pool)
        for _ in range(count // len(by_language)):
            size = rng.choice((2, 3))
            if len(pool) < size:
                break
            parts = [pool.pop() for _ in range(size)]
            clauses = [{"text": p["text"].rstrip("。.!！ "), "label": p["label"]} for p in parts]
            glue = ", " if language == "en" else "，"
            sentences.append({"sentence": glue.join(c["text"] for c in clauses), "clauses": clauses})
    return sentences


def data_sets(with_test: bool) -> dict:
    sets = {"val": {"clauses": [{"text": r["text"], "label": r["label"]} for r in synthetic("val")]}}
    sets["val"]["sentences"] = joined_sentences(synthetic("val"))
    sets["examples"] = {"gold": load(TEMPLATE)}
    if with_test:
        sets["test"] = {"gold": load(TEST)}
    return sets


def texts_needed(sets: dict) -> list[str]:
    texts: list[str] = []
    for data in sets.values():
        texts += [c["text"] for c in data.get("clauses", [])]
        for sentence in data.get("sentences", []) + data.get("gold", []):
            texts += split_clauses(sentence["sentence"]) + [c["text"] for c in sentence["clauses"]]
    return list(dict.fromkeys(texts))


def predict(name: str, classify, texts: list[str], meta: dict) -> dict:
    """Run one classifier over the texts it has not seen yet and save everything."""
    path = PREDICTIONS / f"{name.replace(':', '_').replace('/', '_')}.json"
    saved = json.loads(path.read_text()) if path.exists() else {"model": name, "predictions": {}}
    todo = [text for text in texts if text not in saved["predictions"]]
    if todo:
        classify(todo[0])                                     # warm up (model load) outside the timing
    for number, text in enumerate(todo, 1):
        started = time.perf_counter()
        label = classify(text)
        saved["predictions"][text] = {"label": label, "ms": round((time.perf_counter() - started) * 1000, 2)}
        if number % 50 == 0:
            print(f"  {name}: {number}/{len(todo)}", file=sys.stderr)
    saved.update({key: value for key, value in meta.items() if value is not None})
    PREDICTIONS.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(saved, ensure_ascii=False, indent=1))
    return saved


def score(saved: dict, sets: dict) -> dict:
    preds = saved["predictions"]
    label_of = lambda text: preds[text]["label"]     # noqa: E731
    result = {"model": saved["model"], "size_mb": saved.get("size_mb"), "machine": saved.get("machine"),
              "note": saved.get("note", "")}
    ms = [preds[c["text"]]["ms"] for c in sets["val"]["clauses"] if c["text"] in preds]
    result["ms_per_clause"] = statistics.median(ms) if ms else None
    for name, data in sets.items():
        if "clauses" in data and all(c["text"] in preds for c in data["clauses"]):
            result[name] = classification([c["label"] for c in data["clauses"]],
                                          [label_of(c["text"]) for c in data["clauses"]])
            sentences = data["sentences"]
            if all(t in preds for s in sentences for t in split_clauses(s["sentence"])):
                right = 0
                for s in sentences:
                    pieces = split_clauses(s["sentence"])
                    right += ([clause_key(p) for p in pieces] == [clause_key(c["text"]) for c in s["clauses"]]
                              and [label_of(p) for p in pieces] == [c["label"] for c in s["clauses"]])
                result[name]["sentence_all_right"] = right / len(sentences)
        if "gold" in data:
            gold = data["gold"]
            needed = {t for s in gold for t in split_clauses(s["sentence"]) + [c["text"] for c in s["clauses"]]}
            if not needed <= set(preds):
                continue
            clauses = [c for s in gold for c in s["clauses"]]
            scored = classification([c["label"] for c in clauses], [label_of(c["text"]) for c in clauses])
            parsed = [parse(s["sentence"], label_of) for s in gold]
            scored["split_right"] = sum([clause_key(c["text"]) for c in p["clauses"]] ==
                                        [clause_key(c["text"]) for c in s["clauses"]]
                                        for p, s in zip(parsed, gold)) / len(gold)
            scored["sentence_all_right"] = sum(p["conditions"] == s["conditions"]
                                               for p, s in zip(parsed, gold)) / len(gold)
            scored["fields"] = field_accuracy([s["conditions"] for s in gold], [p["conditions"] for p in parsed])
            result[name] = scored
    return result


def _pct(value) -> str:
    return "–" if value is None else f"{value * 100:.1f}%"


def markdown(results: list[dict], sets: dict) -> str:
    val = sets["val"]
    lines = [
        "# 需求解析：模型对比",
        "",
        f"生成于 {time.strftime('%Y-%m-%d %H:%M')}，脚本 `python3 -m llm.parse.evaluate`。",
        "",
        f"- **验证集（val）**：{len(val['clauses'])} 个**合成**短句（千问 7B 按类别生成，不是真实学生数据），"
        f"按生成请求划分，与训练集不重叠；另把 2–3 个短句拼成 {len(val['sentences'])} 句，测"
        "「切句 + 分类」整句全对率。",
        "- **示例（examples）**：`data/test_template.csv` 的 10 句格式示例，由 Claude 编写，**不是测试集**，"
        "只用来检查整条流程能跑通；数字仅供参考。",
    ]
    if "test" in sets:
        lines.append(f"- **测试集（test）**：组员手写的 {len(sets['test']['gold'])} 句。")
    else:
        lines.append("- **测试集（test）**：组员手写，尚未到位，还没有用过。")
    lines += ["", "## 短句分类（验证集）", "",
              "| 模型 | 准确率 | 宏平均 F1 | 整句全对率 | 每句耗时 (ms) | 模型大小 (MB) | 运行机器 | 备注 |",
              "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |"]
    for r in results:
        v = r.get("val") or {}
        size = "–" if r["size_mb"] is None else f"{r['size_mb']:g}"
        ms = "–" if r["ms_per_clause"] is None else f"{r['ms_per_clause']:.1f}"
        lines.append(f"| {r['model']} | {_pct(v.get('accuracy'))} | {_pct(v.get('macro_f1'))} | "
                     f"{_pct(v.get('sentence_all_right'))} | {ms} | {size} | {r['machine'] or '–'} | {r['note']} |")
    lines += ["", "## 各类 F1（验证集）", "",
              "| 模型 | " + " | ".join(LABEL_ORDER) + " |", "| --- |" + " ---: |" * len(LABEL_ORDER)]
    for r in results:
        if r.get("val"):
            lines.append(f"| {r['model']} | " + " | ".join(f"{r['val']['per_label'][label]['f1']:.2f}"
                                                         for label in LABEL_ORDER) + " |")
    for set_name, title in (("examples", "10 句示例（不是测试集）"), ("test", "测试集")):
        rows = [r for r in results if r.get(set_name)]
        if not rows:
            continue
        lines += ["", f"## 整条流程：{title}", "",
                  "| 模型 | 短句分类准确率 | 切句全对 | 条件全对（整句） | 不可上课时段 | 天数上限 | 每天上课 | 每天在校 | 午饭 | 只要线下 | 舒服时段 | 在意项 |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for r in rows:
            s = r[set_name]
            f = s["fields"]
            lines.append(f"| {r['model']} | {_pct(s['accuracy'])} | {_pct(s['split_right'])} | "
                         f"{_pct(s['sentence_all_right'])} | " + " | ".join(_pct(f[k]) for k in (
                             "unavailable_windows", "max_days_per_week", "max_daily_minutes", "max_daily_span",
                             "lunch", "in_person_only", "preferred_hours", "cares")) + " |")
    best = max((r for r in results if r.get("val")), key=lambda r: r["val"]["accuracy"], default=None)
    if best:
        lines += ["", f"## 混淆矩阵（验证集，{best['model']}）", "",
                  "行是正确类别，列是预测类别。", "", confusion_markdown(best["val"]["confusion"])]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    from llm.parse.classify import by_name
    parser = argparse.ArgumentParser(description="Compare clause classifiers.")
    parser.add_argument("--models", nargs="*", default=[])
    parser.add_argument("--test", action="store_true", help="also score the team's test set (final runs only)")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--machine", default=None, help="where the model ran, for the table")
    parser.add_argument("--size-mb", type=float, default=None)
    parser.add_argument("--note", default=None)
    args = parser.parse_args(argv)
    if args.test and not TEST.exists():
        print(f"{TEST} does not exist yet", file=sys.stderr)
        return 1
    sets = data_sets(args.test)
    texts = texts_needed(sets)
    if not args.report_only:
        for name in args.models:
            machine = args.machine or (None if name.startswith("ollama") else f"{platform.machine()} Mac CPU")
            if name.startswith("ollama") and not args.machine:
                from llm import ollama
                machine = ollama.base_url()
            predict(name, by_name(name), texts, {"machine": machine, "size_mb": args.size_mb, "note": args.note})
    results = [score(json.loads(path.read_text()), sets) for path in sorted(PREDICTIONS.glob("*.json"))]
    order = {name: index for index, name in enumerate(["keywords", "linear"])}
    results.sort(key=lambda r: (order.get(r["model"], 2), r["model"]))
    (OUTPUT / "parse_results.md").write_text(markdown(results, sets), encoding="utf-8")
    (OUTPUT / "parse_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    for r in results:
        v = r.get("val") or {}
        print(f"{r['model']:<28} val acc {_pct(v.get('accuracy')):>6}  macro-F1 {_pct(v.get('macro_f1')):>6}  "
              f"sentences {_pct(v.get('sentence_all_right')):>6}  ms {r['ms_per_clause']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
