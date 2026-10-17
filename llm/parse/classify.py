"""The clause classifiers parse() can use. Each one is a function: clause text -> label.

All of them run with the standard library: keyword rules, the exported linear model,
or a Qwen model served by Ollama (plain or fine-tuned and imported).
"""
from __future__ import annotations

import json
from typing import Callable

from llm import ollama
from llm.parse import linear
from llm.parse.keywords import keyword_label
from llm.parse.labels import LABELS, messages, parse_label, short_messages

Classifier = Callable[[str], str]
LABEL_SCHEMA = {"type": "object", "properties": {"label": {"type": "string", "enum": list(LABELS)}},
                "required": ["label"]}


def ollama_classifier(model: str, *, constrained: bool = True, timeout: float = 30,
                      prompt: Callable[[str], list[dict]] = messages) -> Classifier:
    """Ask a model served by Ollama. With constrained=True the reply can only be one of the 9 labels."""
    def classify(text: str) -> str:
        if constrained:
            reply = ollama.chat(model, prompt(text), schema=LABEL_SCHEMA,
                                options={"num_predict": 24}, timeout=timeout)
            try:
                return parse_label(json.loads(reply)["label"])
            except (ValueError, KeyError, TypeError):
                return parse_label(reply)
        return parse_label(ollama.chat(model, prompt(text), options={"num_predict": 12}, timeout=timeout))
    return classify


def linear_classifier() -> Classifier:
    return linear.load()


def by_name(name: str) -> Classifier:
    if name == "keywords":
        return keyword_label
    if name == "linear":
        return linear_classifier()
    if name.startswith("ollama:"):                # full prompt v1, as measured in round 1
        return ollama_classifier(name.removeprefix("ollama:"), prompt=lambda text: messages(text, "v1"))
    if name.startswith("ollama-v2:"):             # full prompt v2 (fixed example, part-of-day rule)
        return ollama_classifier(name.removeprefix("ollama-v2:"), prompt=lambda text: messages(text, "v2"))
    if name.startswith("ollama-short:"):          # fine-tuned models were trained with the short prompt
        return ollama_classifier(name.removeprefix("ollama-short:"), prompt=short_messages)
    if name.startswith("ollama-free:"):
        return ollama_classifier(name.removeprefix("ollama-free:"), constrained=False,
                                 prompt=lambda text: messages(text, "v1"))
    raise ValueError(f"unknown classifier {name!r}")
