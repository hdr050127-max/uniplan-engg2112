"""Block 2: one sentence -> conditions. Owned by the parsing window.

    sentence --split (rules)--> clauses --classify (model)--> one of 9 labels per clause
             --extract (rules)--> fields per clause --merge--> conditions

Only the classifier is learnt; splitting and number reading are rules (llm/parse/split.py,
llm/parse/extract.py). The label set and its boundary rules are in llm/parse/labels.py.

The run-time classifier is RUNTIME: the round-2 QLoRA fine-tune of Qwen 7B served by Ollama, chosen
in llm/parse/output/test_v2/DECISION.md. If the server does not answer (or takes longer than 15 s,
classify.ollama_classifier), clauses fall back to the plain-Python linear model in output/linear_model.json (the
round-1 model, chosen on the validation set), and to keyword rules if that file is missing.
UNIPLAN_PARSE_RUNTIME overrides RUNTIME, e.g. "linear" for offline runs. Standard library only.

The result also restates what was understood and asks a few questions back (llm/parse/clarify.py);
parse(text, overrides={index: label}) reads it again after the student answers.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Callable

from llm.contracts import Clause, ParseResult
from llm.parse.clarify import clarify as _clarify
from llm.parse.extract import fields, merge
from llm.parse.keywords import keyword_label
from llm.parse.labels import HEDGES
from llm.parse.split import split_clauses
from llm.parse.text import find_times, named_days, normalize

RUNTIME = os.environ.get("UNIPLAN_PARSE_RUNTIME", "ollama-short:uniplan-parse-7b-r2")
GUARD = False                      # apply rule 5 after the model (see guarded); off: chosen on the validation set
_RETRY_AFTER = 60                  # seconds to wait before trying a server that failed again
_down_since: float | None = None


def _fallback(text: str) -> str:
    from llm.parse import linear
    try:
        return linear.load()(text)
    except (OSError, ValueError, KeyError):
        return keyword_label(text)


def _runtime_labelled(text: str) -> tuple[str, bool]:
    """The run-time label, and whether it came from RUNTIME itself (False: from the fallback)."""
    global _down_since
    from llm.parse.classify import by_name
    if not RUNTIME.startswith("ollama"):
        return by_name(RUNTIME)(text), RUNTIME != "linear"
    if _down_since is not None and time.monotonic() - _down_since < _RETRY_AFTER:
        return _fallback(text), False
    try:
        label = by_name(RUNTIME)(text)
        _down_since = None
        return label, True
    except OSError as error:            # server down, timed out, or model missing
        print(f"[llm.parse] {RUNTIME} unavailable ({error}); using the fallback classifier", file=sys.stderr)
        _down_since = time.monotonic()
        return _fallback(text), False


def _runtime(text: str) -> str:
    return _runtime_labelled(text)[0]


def guarded(label: str, text: str) -> str:
    """Rule 5 of labels.RULES checked after the model: a clock time or a named weekday without a
    hedge word is a hard condition, so prefer_no_early_late becomes blocked_time."""
    if label != "prefer_no_early_late":
        return label
    norm = normalize(text)
    if (find_times(norm) or named_days(norm)) and not any(word in norm for word in HEDGES):
        return "blocked_time"
    return label


def parse(text: str, classify: Callable[[str], str] | None = None, guard: bool | None = None,
          overrides: dict[int, str] | None = None) -> ParseResult:
    """overrides: {clause index: label} the student chose by answering a question; those clauses are
    read again under the chosen label and not asked about again."""
    guard = GUARD if guard is None else guard
    overrides = overrides or {}
    clauses: list[Clause] = []
    from_model: list[bool] = []
    for index, piece in enumerate(split_clauses(text)):
        label, by_model = (classify(piece), True) if classify else _runtime_labelled(piece)
        if guard:
            label = guarded(label, piece)
        if index in overrides:
            label = overrides[index]
        clauses.append({"text": piece, "label": label, "fields": fields(label, piece)})
        from_model.append(by_model)
    result: ParseResult = {"clauses": clauses, "conditions": merge(clauses),
                           "unrecognised": [clause["text"] for clause in clauses if clause["label"] == "other"]}
    return _clarify(result, from_model, confirmed=set(overrides))
