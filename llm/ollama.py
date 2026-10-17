"""Tiny Ollama client shared by every block.

Which server answers is decided once per process, in this order:
1. the UNIPLAN_OLLAMA_URL environment variable;
2. the file ~/.config/uniplan/ollama_url (one line, e.g. http://192.168.1.20:11434),
   written by the coordinator so every worktree uses the Windows GPU machine;
3. this machine (http://127.0.0.1:11434).
If the configured server does not answer, calls fall back to this machine with a warning.

    python3 -m llm.ollama          # which server is in use and which models it has
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path

LOCAL = "http://127.0.0.1:11434"
CONFIG = Path.home() / ".config" / "uniplan" / "ollama_url"


def _configured() -> str:
    url = os.environ.get("UNIPLAN_OLLAMA_URL")
    if not url and CONFIG.exists():
        url = CONFIG.read_text().strip()
    return (url or LOCAL).rstrip("/")


def _models(url: str) -> set[str] | None:
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=3) as response:
            return {item["name"] for item in json.loads(response.read())["models"]}
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None


@lru_cache(maxsize=1)
def base_url() -> str:
    url = _configured()
    if url != LOCAL and _models(url) is None:
        print(f"[llm.ollama] {url} is not answering; using this machine instead", file=sys.stderr)
        return LOCAL
    return url


def chat(model: str, messages: list[dict], *, schema: dict | None = None,
         options: dict | None = None, timeout: float = 300) -> str:
    """One non-streaming chat call; returns the reply text (JSON text when a schema is given)."""
    body = {"model": model, "stream": False, "messages": messages,
            "options": {"temperature": 0, **(options or {})}}
    if schema is not None:
        body["format"] = schema
    request = urllib.request.Request(f"{base_url()}/api/chat", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())["message"]["content"]


def available(model: str | None = None) -> bool:
    """Whether the server in use answers (and has the model, if one is named)."""
    names = _models(base_url())
    return names is not None and (model is None or model in names)


if __name__ == "__main__":
    configured, used = _configured(), base_url()
    print(f"configured: {configured}\nin use:     {used}")
    print("models:    ", ", ".join(sorted(_models(used) or [])) or "(server not answering)")
