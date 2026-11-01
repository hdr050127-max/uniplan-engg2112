"""Of the exam sentences whose recommendation broke a stated condition, how many had already been offered the
fix: a clarifying question on the misread clause whose options include the annotator's label.

Run from the repository root: python3 report/scripts/violations_fixable.py
Writes report/data/violations_fixable.json. Same method as llm/parse/clarify_eval.py on the exam: clause labels
from the cached uniplan-parse-7b-r2 predictions, second opinion from the run-time linear model; no model is called.
The sentences are AI-written (synthetic), not real students.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llm.parse import clarify, linear  # noqa: E402
from llm.parse.clarify_eval import _clause, _core  # noqa: E402
from llm.parse.evaluate import OUTPUT  # noqa: E402
from llm.parse.gold import load  # noqa: E402

PIPELINE = ROOT / "output/pipeline/pipeline_eval_uniplan-parse-7b-r2_model_exam.json"
PREDICTIONS = OUTPUT / "exam/predictions/ollama-short_uniplan-parse-7b-r2.json"


def main() -> None:
    records = json.loads(PIPELINE.read_text())["records"]
    violating = [r["sentence_id"] for r in records
                 if r["status_parsed"] == "ready" and r.get("violations") is not None and any(r["violations"])]
    gold = {s["id"]: s for s in load(ROOT / "llm/parse/exam/exam.csv")}
    preds = json.loads(PREDICTIONS.read_text())["predictions"]
    second = linear.load(OUTPUT / "linear_model.json")
    rows = []
    for sid in violating:
        clauses = []
        for c in gold[sid]["clauses"]:
            text, right = c["text"], c["label"]
            label = preds[text]["label"]
            asked = [q for q in clarify.questions(_core([_clause(text, label)]), [True], second.probabilities)
                     if q["clause_index"] == 0]
            options = {o["label"] for q in asked for o in q["options"]}
            clauses.append({"text": text, "right": right, "read": label, "wrong": label != right,
                            "asked": bool(asked), "fixable": label != right and right in options})
        rows.append({"sentence_id": sid, "sentence": gold[sid]["sentence"], "clauses": clauses,
                     "fixable": any(c["fixable"] for c in clauses)})
    out = {"note": "Exam sentences whose recommendation broke a stated condition, and whether a clarifying "
                   "question had offered the right reading; AI-written sentences, by report/scripts/violations_fixable.py",
           "violating": len(rows), "fixable": sum(r["fixable"] for r in rows), "sentences": rows}
    (ROOT / "report/data/violations_fixable.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"{out['fixable']} of {out['violating']} violating sentences had the fix offered:",
          [r["sentence_id"] for r in rows if r["fixable"]])


if __name__ == "__main__":
    main()
