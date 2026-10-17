"""Reference: let Qwen rank directly, with no trained model in between.

Two ways, both on the 20 test personas only:
- pairwise: one call per test pair, red = A, no swap check (what a cheap LLM judge would do);
- listwise: one call per test persona with all 8 candidates, "pick the best 3" (what an LLM
  ranker in the web page would do; one call per student).
The answers are scored against the teacher labels by llm/rank/train.py (--direct). Run it
after llm.rank.label run, wrapped in the GPU lock:

    python3 -m llm.gpu_lock -- python3 -m llm.rank.direct --model qwen2.5:7b --labels <labels.jsonl>
    python3 -m llm.gpu_lock -- python3 -m llm.rank.direct --model qwen2.5:14b --kinds listwise --labels ...
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llm import ollama  # noqa: E402
from llm.rank.features import hours_of  # noqa: E402
from llm.rank.label import OUT, ROWS, ask, free_other_models, row_labels  # noqa: E402
from llm.rank.personas import load  # noqa: E402
from llm.rank.metrics import membership, teacher_order  # noqa: E402

NAMES = "ABCDEFGH"
LIST_SYSTEM = ("你要扮演一位大学生，根据他自己的情况，从几份课表里选出最适合他的 3 份，按从好到差排列。"
               "数字越小越好的项：到校天数、空等、早晚课、最长的一天、只为一节课到校。"
               "表格里的早晚课已经按这位学生自己方便的时段算好，直接用表里的数字。")


def listwise(model: str, persona: dict, candidates: list[dict]) -> tuple[list[str], float]:
    labels = row_labels(hours_of(persona["conditions"]))
    names = NAMES[:len(candidates)]
    head = "| 项目 | " + " | ".join(names) + " |\n| --- |" + " --- |" * len(names)
    body = "\n".join(f"| {labels[row]} | " + " | ".join(c["table"][row] for c in candidates) + " |" for row in ROWS)
    texts = "\n\n".join(f"课表 {n}（每周固定的课）：\n{c['text']}" for n, c in zip(names, candidates))
    schema = {"type": "object", "properties": {
        "reason": {"type": "string"},
        "top3": {"type": "array", "items": {"type": "string", "enum": list(names)}, "minItems": 3, "maxItems": 3}},
        "required": ["reason", "top3"]}
    started = time.time()
    reply = json.loads(ollama.chat(model, [{"role": "system", "content": LIST_SYSTEM},
                                           {"role": "user", "content": f"学生情况：{persona['text']}\n\n{head}\n{body}\n\n{texts}"}],
                                   schema=schema, options={"num_predict": 400, "num_ctx": 8192}))
    picked = list(dict.fromkeys(reply["top3"]))
    return [candidates[names.index(n)]["candidate_id"] for n in picked], time.time() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--labels", required=True, help="the teacher labels (labels_v3_*.jsonl)")
    parser.add_argument("--kinds", nargs="+", choices=("listwise", "pairwise"), default=["listwise", "pairwise"])
    args = parser.parse_args()
    personas = {p["id"]: p for p in load()}
    sets = json.loads((OUT / "candidate_sets.json").read_text(encoding="utf-8"))["sets"]
    teacher = [json.loads(line) for line in Path(args.labels).read_text(encoding="utf-8").splitlines()]
    teacher = [row for row in teacher if row["split"] == "test"]
    path = OUT / f"direct_{args.model.replace(':', '_')}.jsonl"
    done = {(r["kind"], r["persona"], r.get("a_id"), r.get("b_id"))
            for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())} if path.exists() else set()
    free_other_models(args.model)
    print(f"model {args.model} at {ollama.base_url()}", flush=True)
    with path.open("a", encoding="utf-8") as handle:
        for pid in sorted({row["persona"] for row in teacher}):
            persona, candidates = personas[pid], sets[pid]
            by_id = {c["candidate_id"]: c for c in candidates}
            if "listwise" in args.kinds and ("listwise", pid, None, None) not in done:
                ids = [c["candidate_id"] for c in candidates]
                picked, seconds = listwise(args.model, persona, candidates)
                rows = [r for r in teacher if r["persona"] == pid]
                points = teacher_order(rows, ids)
                share = membership(points)
                winners = [i for i, v in points.items() if v == max(points.values())]
                handle.write(json.dumps({"kind": "listwise", "persona": pid, "model": args.model, "picked": picked,
                                         "top3_hit": sum(share[i] for i in picked) / 3,
                                         "best_in_top3": sum(i in picked for i in winners) / len(winners),
                                         "seconds": round(seconds, 2), "synthetic": True}, ensure_ascii=False) + "\n")
                handle.flush()
            for row in teacher if "pairwise" in args.kinds else ():
                if row["persona"] != pid or row["label"] not in ("A", "B") or \
                        ("pairwise", pid, row["a_id"], row["b_id"]) in done:
                    continue
                started = time.time()
                answer = ask(args.model, persona, by_id[row["a_id"]], by_id[row["b_id"]])
                handle.write(json.dumps({"kind": "pairwise", "persona": pid, "model": args.model,
                                         "a_id": row["a_id"], "b_id": row["b_id"],
                                         "choice": {"红": "A", "蓝": "B"}[answer["choice"]],
                                         "seconds": round(time.time() - started, 2), "synthetic": True},
                                        ensure_ascii=False) + "\n")
                handle.flush()
            print(f"  {pid} done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
