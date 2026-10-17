"""Tiny Ollama client shared by every block.

Which server answers, in this order:
1. the UNIPLAN_OLLAMA_URL environment variable;
2. the file ~/.config/uniplan/ollama_url (one line, e.g. http://192.168.1.20:11434),
   written by the coordinator so every worktree uses the Windows GPU machine;
3. this machine (http://127.0.0.1:11434).
If the configured server does not answer, calls fall back to this machine with a warning. That also
happens mid-run: a call that cannot reach the configured server is retried here at once. While on
this machine, the configured server is checked again every minute and used again once it is back.

    python3 -m llm.ollama          # which server is in use and which models it has
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
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


RECHECK_SECONDS = 60.0
_state: dict = {"url": None, "checked": 0.0}


def _use_local(configured: str) -> str:
    if _state["url"] != LOCAL:
        print(f"[llm.ollama] {configured} is not answering; using this machine instead", file=sys.stderr)
    _state.update(url=LOCAL, checked=time.monotonic())
    return LOCAL


def base_url() -> str:
    """The server in use: the configured one while it answers, otherwise this machine."""
    configured = _configured()
    url = _state["url"]
    stale = url == LOCAL and configured != LOCAL and time.monotonic() - _state["checked"] >= RECHECK_SECONDS
    if url is None or stale:
        if configured != LOCAL and _models(configured) is None:
            return _use_local(configured)
        if stale:
            print(f"[llm.ollama] {configured} is answering again; using it", file=sys.stderr)
        _state.update(url=configured, checked=time.monotonic())
    return _state["url"]


def _reset() -> None:
    """Forget the choice (tests, or after changing UNIPLAN_OLLAMA_URL in a running process)."""
    _state.update(url=None, checked=0.0)


base_url.cache_clear = _reset  # the old lru_cache name, kept for callers


def _unreachable(error: BaseException) -> bool:
    """A connection problem (refused, no route, timed out), not an answer from the server."""
    if isinstance(error, urllib.error.HTTPError):
        return False
    return isinstance(error, (urllib.error.URLError, ConnectionError, socket.timeout, TimeoutError))


def _post(path: str, body: dict, timeout: float) -> bytes:
    """POST to the server in use; if the configured server cannot be reached, retry on this machine."""
    url = base_url()
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{url}{path}", data, headers), timeout=timeout) as response:
            return response.read()
    except OSError as error:
        if url == LOCAL or not _unreachable(error):
            raise
        _use_local(url)
        with urllib.request.urlopen(urllib.request.Request(f"{LOCAL}{path}", data, headers), timeout=timeout) as response:
            return response.read()


def chat(model: str, messages: list[dict], *, schema: dict | None = None,
         options: dict | None = None, timeout: float = 300) -> str:
    """One non-streaming chat call; returns the reply text (JSON text when a schema is given)."""
    body = {"model": model, "stream": False, "messages": messages,
            "options": {"temperature": 0, **(options or {})}}
    if schema is not None:
        body["format"] = schema
    return json.loads(_post("/api/chat", body, timeout))["message"]["content"]


def unload(model: str) -> None:
    """Free a model's GPU memory before a batch switches to another model (7B and 14B
    together nearly fill the Windows GPU's 16 GB and slow both down)."""
    _post("/api/generate", {"model": model, "keep_alive": 0}, 60)


def available(model: str | None = None) -> bool:
    """Whether the server in use answers (and has the model, if one is named)."""
    names = _models(base_url())
    return names is not None and (model is None or model in names)


if __name__ == "__main__":
    configured, used = _configured(), base_url()
    print(f"configured: {configured}\nin use:     {used}")
    print("models:    ", ", ".join(sorted(_models(used) or [])) or "(server not answering)")
