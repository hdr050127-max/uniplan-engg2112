"""Tiny Ollama client shared by every block.

The server address comes from UNIPLAN_OLLAMA_URL (default: this machine), so heavy
jobs can run against another computer on the network, e.g.
UNIPLAN_OLLAMA_URL=http://192.168.1.20:11434 python3 -m llm.rank.pilot
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

URL = os.environ.get("UNIPLAN_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def chat(model: str, messages: list[dict], *, schema: dict | None = None,
         options: dict | None = None, timeout: float = 300) -> str:
    """One non-streaming chat call; returns the reply text (JSON text when a schema is given)."""
    body = {"model": model, "stream": False, "messages": messages,
            "options": {"temperature": 0, **(options or {})}}
    if schema is not None:
        body["format"] = schema
    request = urllib.request.Request(f"{URL}/api/chat", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())["message"]["content"]


def available(model: str | None = None) -> bool:
    """Whether the server answers (and has the model, if one is named)."""
    try:
        with urllib.request.urlopen(f"{URL}/api/tags", timeout=3) as response:
            names = {item["name"] for item in json.loads(response.read())["models"]}
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return False
    return model is None or model in names
