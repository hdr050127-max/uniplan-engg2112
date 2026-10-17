"""Scores for the clause classifier and the whole parser (standard library only)."""
from __future__ import annotations

from llm.contracts import HARD_FIELDS, SOFT_FIELDS
from llm.parse.labels import LABELS

LABEL_ORDER = list(LABELS)
FIELDS = HARD_FIELDS + SOFT_FIELDS


def classification(gold: list[str], pred: list[str]) -> dict:
    """Accuracy, per-label precision/recall/F1, macro F1 and the confusion matrix (gold rows, predicted columns)."""
    matrix = {g: {p: 0 for p in LABEL_ORDER} for g in LABEL_ORDER}
    for g, p in zip(gold, pred):
        matrix[g][p] += 1
    per_label = {}
    for label in LABEL_ORDER:
        tp = matrix[label][label]
        predicted = sum(matrix[g][label] for g in LABEL_ORDER)
        actual = sum(matrix[label].values())
        precision = tp / predicted if predicted else 0.0
        recall = tp / actual if actual else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {"precision": precision, "recall": recall, "f1": f1, "support": actual}
    present = [label for label in LABEL_ORDER if per_label[label]["support"]]
    return {"n": len(gold), "accuracy": sum(g == p for g, p in zip(gold, pred)) / len(gold) if gold else 0.0,
            "macro_f1": sum(per_label[label]["f1"] for label in present) / len(present) if present else 0.0,
            "per_label": per_label, "confusion": matrix}


def field_accuracy(gold: list[dict], pred: list[dict]) -> dict[str, float]:
    """Share of sentences where each condition field is exactly right (both empty counts as right)."""
    def value(conditions: dict, field: str):
        found = conditions.get(field)
        return None if found in (None, False, []) else found
    return {field: sum(value(g, field) == value(p, field) for g, p in zip(gold, pred)) / len(gold)
            for field in FIELDS} if gold else {}


def confusion_markdown(matrix: dict) -> str:
    short = {label: label.replace("prefer_", "p_").replace("max_daily_hours", "max_hours")
             .replace("in_person_only", "in_person").replace("blocked_time", "blocked") for label in LABEL_ORDER}
    lines = ["| gold \\ predicted | " + " | ".join(short[label] for label in LABEL_ORDER) + " |",
             "| --- |" + " ---: |" * len(LABEL_ORDER)]
    for g in LABEL_ORDER:
        lines.append(f"| {short[g]} | " + " | ".join(str(matrix[g][p]) for p in LABEL_ORDER) + " |")
    return "\n".join(lines)
