"""Block 2: one sentence -> conditions. Owned by the parsing window.

    sentence --split (rules)--> clauses --classify (model)--> one of 9 labels per clause
             --extract (rules)--> fields per clause --merge--> conditions

Only the classifier is learnt; splitting and number reading are rules (llm/parse/split.py,
llm/parse/extract.py). The label set and its boundary rules are in llm/parse/labels.py.
"""
from __future__ import annotations

from typing import Callable

from llm.contracts import Clause, ParseResult
from llm.parse.extract import fields, merge
from llm.parse.keywords import keyword_label
from llm.parse.split import split_clauses


def parse(text: str, classify: Callable[[str], str] | None = None) -> ParseResult:
    label_of = classify or keyword_label
    clauses: list[Clause] = []
    for piece in split_clauses(text):
        label = label_of(piece)
        clauses.append({"text": piece, "label": label, "fields": fields(label, piece)})
    return {"clauses": clauses, "conditions": merge(clauses),
            "unrecognised": [clause["text"] for clause in clauses if clause["label"] == "other"]}
