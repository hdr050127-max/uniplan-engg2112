"""95% bootstrap intervals for the parsing final exam, from the saved predictions only.

Run from the repository root: python3 report/scripts/parse_exam_ci.py
Writes report/data/parse_exam_ci.json. No model is called: every label comes from
llm/parse/output/exam/predictions/, and a missing prediction stops the script.

Sentences are resampled (clauses in one sentence are not independent), 10,000 times, seed 2112.
The differences are paired: each resample scores both methods on the same sentences.
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llm.parse import parse  # noqa: E402
from llm.parse.gold import load  # noqa: E402

EXAM = ROOT / "llm/parse/exam/exam.csv"
PREDICTIONS = ROOT / "llm/parse/output/exam/predictions"
METHODS = {
    "keyword rules": "keywords.json",
    "TF-IDF + logistic regression (linear-r1)": "linear-r1.json",
    "Qwen 7B zero-shot, prompt v1": "ollama_qwen2.5_7b.json",
    "Qwen 7B zero-shot, prompt v2": "ollama-v2_qwen2.5_7b.json",
    "Qwen 7B QLoRA round 1": "ollama-short_uniplan-parse-7b.json",
    "Qwen 7B QLoRA round 2": "ollama-short_uniplan-parse-7b-r2.json",
}
PAIRS = [("Qwen 7B QLoRA round 2", "Qwen 7B QLoRA round 1"),
         ("Qwen 7B QLoRA round 2", "Qwen 7B zero-shot, prompt v2"),
         ("Qwen 7B QLoRA round 2", "keyword rules")]
REPS, SEED = 10_000, 2112


def per_sentence(gold: list[dict], file: str) -> list[tuple[int, int, int]]:
    """(clauses right, clauses, whole sentence right) for each exam sentence."""
    preds = json.loads((PREDICTIONS / file).read_text())["predictions"]

    def label_of(text: str) -> str:
        if text not in preds:
            raise SystemExit(f"{file}: no saved prediction for {text!r}; not calling the model")
        return preds[text]["label"]

    rows = []
    for sentence in gold:
        right = sum(label_of(c["text"]) == c["label"] for c in sentence["clauses"])
        exact = parse(sentence["sentence"], label_of, guard=False)["conditions"] == sentence["conditions"]
        rows.append((right, len(sentence["clauses"]), int(exact)))
    return rows


def rates(rows, picks):
    right = sum(rows[i][0] for i in picks)
    total = sum(rows[i][1] for i in picks)
    return right / total, sum(rows[i][2] for i in picks) / len(picks)


def interval(values: list[float]) -> list[float]:
    values = sorted(values)
    return [round(values[int(0.025 * len(values))], 4), round(values[int(0.975 * len(values)) - 1], 4)]


def main() -> None:
    gold = load(EXAM)
    rows = {name: per_sentence(gold, file) for name, file in METHODS.items()}
    rng = random.Random(SEED)
    every = range(len(gold))
    samples = [[rng.randrange(len(gold)) for _ in every] for _ in range(REPS)]
    out = {"exam": str(EXAM.relative_to(ROOT)), "sentences": len(gold),
           "clauses": sum(len(s["clauses"]) for s in gold), "reps": REPS, "seed": SEED,
           "methods": {}, "differences": {}}
    for name, method_rows in rows.items():
        clause, sentence = rates(method_rows, every)
        boot = [rates(method_rows, picks) for picks in samples]
        out["methods"][name] = {
            "clause_accuracy": round(clause, 4), "clause_ci": interval([b[0] for b in boot]),
            "sentence_all_right": round(sentence, 4), "sentence_ci": interval([b[1] for b in boot])}
    for a, b in PAIRS:
        diff = [(rates(rows[a], p)[0] - rates(rows[b], p)[0], rates(rows[a], p)[1] - rates(rows[b], p)[1])
                for p in samples]
        out["differences"][f"{a} minus {b}"] = {
            "clause": round(rates(rows[a], every)[0] - rates(rows[b], every)[0], 4),
            "clause_ci": interval([d[0] for d in diff]),
            "sentence": round(rates(rows[a], every)[1] - rates(rows[b], every)[1], 4),
            "sentence_ci": interval([d[1] for d in diff])}
    path = ROOT / "report/data/parse_exam_ci.json"
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
