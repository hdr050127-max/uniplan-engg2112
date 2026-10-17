"""Block 2: one sentence -> conditions. Owned by the parsing window.

    sentence --split (rules)--> clauses --classify (model)--> one of 9 labels per clause
             --extract (rules)--> fields per clause --merge--> conditions

Only the classifier is learnt; splitting and number reading are rules (llm/parse/split.py,
llm/parse/extract.py). The label set and its boundary rules are in llm/parse/labels.py.

The run-time classifier is RUNTIME (picked from llm/parse/output/parse_results.md). If it is a
model served by Ollama and the server does not answer, clauses fall back to the plain-Python
linear model, and to keyword rules if that file is missing. Everything here is standard library.
"""
from __future__ import annotations

import sys
import time
from typing import Callable

from llm.contracts import Clause, ParseResult
from llm.parse.extract import fields, merge
from llm.parse.keywords import keyword_label
from llm.parse.labels import HEDGES
from llm.parse.split import split_clauses
from llm.parse.text import find_times, named_days, normalize

RUNTIME = "linear"                 # or "ollama-short:<model>" for a fine-tuned model in Ollama
GUARD = False                      # apply rule 5 after the model (see guarded); off by default
_RETRY_AFTER = 60                  # seconds to wait before trying a server that failed again
_down_since: float | None = None


def _fallback(text: str) -> str:
    from llm.parse import linear
    try:
        return linear.load()(text)
    except (OSError, ValueError, KeyError):
        return keyword_label(text)


def _runtime(text: str) -> str:
    global _down_since
    if not RUNTIME.startswith("ollama"):
        return _fallback(text)
    if _down_since is not None and time.monotonic() - _down_since < _RETRY_AFTER:
        return _fallback(text)
    from llm.parse.classify import by_name
    try:
        label = by_name(RUNTIME)(text)
        _down_since = None
        return label
    except OSError as error:            # server down, timed out, or model missing
        print(f"[llm.parse] {RUNTIME} unavailable ({error}); using the fallback classifier", file=sys.stderr)
        _down_since = time.monotonic()
        return _fallback(text)


def guarded(label: str, text: str) -> str:
    """Rule 5 of labels.RULES checked after the model: a clock time or a named weekday without a
    hedge word is a hard condition, so prefer_no_early_late becomes blocked_time."""
    if label != "prefer_no_early_late":
        return label
    norm = normalize(text)
    if (find_times(norm) or named_days(norm)) and not any(word in norm for word in HEDGES):
        return "blocked_time"
    return label


def parse(text: str, classify: Callable[[str], str] | None = None, guard: bool | None = None) -> ParseResult:
    label_of = classify or _runtime
    guard = GUARD if guard is None else guard
    clauses: list[Clause] = []
    for piece in split_clauses(text):
        label = label_of(piece)
        if guard:
            label = guarded(label, piece)
        clauses.append({"text": piece, "label": label, "fields": fields(label, piece)})
    return {"clauses": clauses, "conditions": merge(clauses),
            "unrecognised": [clause["text"] for clause in clauses if clause["label"] == "other"]}
